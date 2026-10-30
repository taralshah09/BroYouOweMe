from collections import defaultdict

from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models import Q

from apps.expenses.services.money import validate_paise
from .models import Balance


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
            for user_id, share in equal_shares(expense).items():
                if user_id == expense.paid_by_id:
                    continue
                user_a, user_b = sorted((user_id, expense.paid_by_id))
                expected[(user_a, user_b)] += share if expense.paid_by_id == user_a else -share
        actual = {(row.user_a_id, row.user_b_id): row.net_paise for row in Balance.objects.filter(group=group)}
        for pair in sorted(expected.keys() | actual.keys()):
            if expected.get(pair, 0) != actual.get(pair, 0):
                mismatches.append({"group_id": group.id, "pair": pair, "expected": expected.get(pair, 0), "actual": actual.get(pair, 0)})
    return mismatches
