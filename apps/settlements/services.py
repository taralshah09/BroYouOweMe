from collections import defaultdict

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, transaction
from django.db.models import Q, Sum
from django.http import Http404
from django.utils import timezone

from apps.expenses.services.money import validate_paise
from .models import Balance, Settlement


def minimum_transfers(net_balances):
    """Exact memoized search over debtor/creditor matches, in integer paise."""
    from functools import lru_cache

    if any(type(value) is not int for value in net_balances.values()) or sum(net_balances.values()):
        raise ValueError("Net balances must be integer paise and sum to zero.")
    users = sorted(user for user, value in net_balances.items() if value)

    @lru_cache(maxsize=None)
    def solve(state):
        if not any(state):
            return ()
        best = None
        lower_bound = max(sum(value < 0 for value in state), sum(value > 0 for value in state))
        seen = set()
        for debtor, debt in enumerate(state):
            if debt >= 0:
                continue
            for creditor, credit in enumerate(state):
                if credit <= 0 or (debt, credit) in seen:
                    continue
                seen.add((debt, credit))
                amount = min(-debt, credit)
                remaining = list(state)
                remaining[debtor] += amount
                remaining[creditor] -= amount
                candidate = ((users[debtor], users[creditor], amount),) + solve(tuple(remaining))
                if best is None or len(candidate) < len(best):
                    best = candidate
                if len(best) == lower_bound:
                    return best
        return best

    return list(solve(tuple(net_balances[user] for user in users)))


def suggested_settlements(actor, *, group_id):
    from apps.groups.services import require_member

    require_member(group_id, actor)
    nets = defaultdict(int)
    names = {}
    for row in Balance.objects.filter(group_id=group_id).select_related("user_a", "user_b").order_by("user_a_id", "user_b_id"):
        nets[row.user_a_id] += row.net_paise
        nets[row.user_b_id] -= row.net_paise
        names[row.user_a_id] = row.user_a.username
        names[row.user_b_id] = row.user_b.username
    return [{"payer": debtor, "payer_username": names[debtor], "receiver": creditor,
             "receiver_username": names[creditor], "amount": rupee_value(amount)}
            for debtor, creditor, amount in minimum_transfers(nets)]


def apply_debt(group_id, debtor_id, creditor_id, amount_paise):
    """Internal write primitive: caller must hold the group row lock."""
    if not connection.in_atomic_block:
        raise RuntimeError("Balance writes require a transaction and group lock.")
    if debtor_id == creditor_id:
        raise ValueError("A payer cannot owe themselves.")
    user_a, user_b = sorted((debtor_id, creditor_id))
    delta = amount_paise if creditor_id == user_a else -amount_paise
    current = Balance.objects.filter(group_id=group_id, user_a_id=user_a, user_b_id=user_b).values_list("net_paise", flat=True).first() or 0
    try:
        validate_paise(current + delta)
    except ValueError:
        raise ValidationError("This expense would exceed the supported balance range.") from None
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO balances (group_id, user_a_id, user_b_id, net_paise) "
            "VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (group_id, user_a_id, user_b_id) DO UPDATE "
            "SET net_paise = balances.net_paise + EXCLUDED.net_paise",
            [group_id, user_a, user_b, delta],
        )


def rupee_value(paise):
    # Whole rupees match the assignment JSON. Fractions remain exact strings.
    whole, fraction = divmod(paise, 100)
    return whole if fraction == 0 else f"{whole}.{fraction:02d}"


def balances_for(actor, *, group_id=None):
    from apps.groups.services import require_member

    rows = Balance.objects.filter(group__deleted_at__isnull=True)
    if group_id is not None:
        require_member(group_id, actor)
        rows = rows.filter(group_id=group_id)
    else:
        rows = rows.filter(
            group__memberships__user=actor, group__memberships__left_at__isnull=True,
        ).filter(Q(user_a=actor) | Q(user_b=actor))
    totals = defaultdict(int)
    names = {}
    for row in rows.select_related("user_a", "user_b"):
        totals[(row.user_a_id, row.user_b_id)] += row.net_paise
        names[row.user_a_id] = row.user_a.username
        names[row.user_b_id] = row.user_b.username
    result = {}
    for (user_a, user_b), net in sorted(totals.items()):
        if net:
            debtor, creditor = (user_b, user_a) if net > 0 else (user_a, user_b)
            result.setdefault(names[debtor], {"owes": {}})["owes"][names[creditor]] = rupee_value(abs(net))
    return result


@transaction.atomic
def balance_mismatches(group_id=None):
    """Compare ledger with maintained balances under the same group locks."""
    from apps.expenses.models import Expense
    from apps.expenses.services import equal_shares
    from apps.groups.models import Group

    groups = Group.all_objects.order_by("id")
    if group_id is not None:
        groups = groups.filter(pk=group_id)
    mismatches = []
    for group in groups.select_for_update():
        expected = defaultdict(int)
        for expense in Expense.objects.filter(group=group):
            shares = equal_shares(expense)
            if expense.source == "ocr":
                from apps.expenses.services.receipts import item_data, prepare_items
                from django.core.exceptions import ValidationError
                try:
                    _, receipt_shares = prepare_items(item_data(expense), list(shares), expense.amount_paise, expense.split_mode)
                    if receipt_shares != shares:
                        raise ValidationError("Receipt allocations differ from splits.")
                except ValidationError:
                    mismatches.append({"group_id": group.id, "expense_id": expense.id, "error": "Invalid receipt items or shares."})
            if sum(shares.values()) != expense.amount_paise or any(share <= 0 for share in shares.values()):
                mismatches.append({"group_id": group.id, "expense_id": expense.id, "error": "Invalid split total or shares."})
            for user_id, share in shares.items():
                if user_id == expense.paid_by_id:
                    continue
                user_a, user_b = sorted((user_id, expense.paid_by_id))
                expected[(user_a, user_b)] += share if expense.paid_by_id == user_a else -share
        for settlement in Settlement.objects.filter(group=group, status="confirmed"):
            user_a, user_b = sorted((settlement.payer_id, settlement.receiver_id))
            expected[(user_a, user_b)] -= settlement.amount_paise if settlement.receiver_id == user_a else -settlement.amount_paise
        actual = {(row.user_a_id, row.user_b_id): row.net_paise for row in Balance.objects.filter(group=group)}
        for pair in sorted(expected.keys() | actual.keys()):
            if expected.get(pair, 0) != actual.get(pair, 0):
                mismatches.append({"group_id": group.id, "pair": pair, "expected": expected.get(pair, 0), "actual": actual.get(pair, 0)})
    return mismatches


def settlement_snapshot(settlement):
    return {"payer": settlement.payer_id, "receiver": settlement.receiver_id,
            "amount_paise": settlement.amount_paise, "status": settlement.status,
            "note": settlement.note,
            "resolved_at": settlement.resolved_at.isoformat() if settlement.resolved_at else None}


def check_available(settlement):
    user_a, user_b = sorted((settlement.payer_id, settlement.receiver_id))
    net = Balance.objects.filter(group_id=settlement.group_id, user_a_id=user_a, user_b_id=user_b).values_list("net_paise", flat=True).first() or 0
    owed = net if settlement.receiver_id == user_a else -net
    reserved = Settlement.objects.filter(group_id=settlement.group_id, payer_id=settlement.payer_id, receiver_id=settlement.receiver_id, status="pending").exclude(pk=settlement.pk).aggregate(total=Sum("amount_paise"))["total"] or 0
    if settlement.amount_paise + reserved > owed:
        raise ValidationError("The amount plus other pending payments exceeds the current pairwise debt.")


@transaction.atomic
def create_settlement(*, actor, group_id, receiver, amount, note=None):
    from apps.activity.services import record
    from apps.expenses.services import money
    from apps.groups.services import require_member
    from apps.groups.models import Membership

    group = require_member(group_id, actor, lock=True)
    if type(receiver) is not int or not Membership.objects.filter(group=group, user_id=receiver, left_at__isnull=True).exists():
        raise ValidationError("The receiver must be an active group member.")
    settlement = Settlement(group=group, payer=actor, receiver_id=receiver,
                            amount_paise=money(amount), note=note)
    settlement.full_clean()
    check_available(settlement)
    settlement.save()
    record(group_id=group.id, actor=actor, action="settlement.claimed", entity=settlement, after=settlement_snapshot(settlement))
    return settlement


@transaction.atomic
def resolve_settlement(*, actor, settlement_id, action):
    from apps.activity.services import record
    from apps.groups.services import require_member

    try:
        group_id = Settlement.objects.values_list("group_id", flat=True).get(pk=settlement_id)
    except Settlement.DoesNotExist:
        raise Http404 from None
    require_member(group_id, actor, lock=True)
    settlement = Settlement.objects.get(pk=settlement_id)
    if action not in {"confirm", "reject", "cancel"}:
        raise ValidationError("Unknown settlement action.")
    expected_actor = settlement.payer_id if action == "cancel" else settlement.receiver_id
    if actor.pk != expected_actor:
        raise PermissionDenied("Only the payer can cancel; only the receiver can confirm or reject.")
    if settlement.status != "pending":
        raise ValidationError("This settlement has already been resolved.")
    before = settlement_snapshot(settlement)
    if action == "confirm":
        check_available(settlement)
        apply_debt(group_id, settlement.payer_id, settlement.receiver_id, -settlement.amount_paise)
    settlement.status = {"confirm": "confirmed", "reject": "rejected", "cancel": "cancelled"}[action]
    settlement.resolved_at = timezone.now()
    settlement.save(update_fields=["status", "resolved_at"])
    record(group_id=group_id, actor=actor, action="settlement." + settlement.status, entity=settlement,
           before=before, after=settlement_snapshot(settlement))
    return settlement
