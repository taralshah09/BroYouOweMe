"""Read-only spending reports, ledger exports and user-shared reminders."""

import re
from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from apps.expenses.models import Expense, ExpenseSplit
from apps.groups.services import require_member
from apps.settlements.models import Balance, Settlement


def format_paise(paise):
    # Report sums may exceed a single ledger row's bigint range.
    whole, fraction = divmod(paise, 100)
    return f"{whole}.{fraction:02d}"


def report_month(value=None):
    if value is None:
        return timezone.localdate().replace(day=1)
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}", value):
        raise ValidationError("Month must use YYYY-MM.")
    try:
        result = date.fromisoformat(value + "-01")
    except ValueError:
        raise ValidationError("Provide a valid month.") from None
    if result.year < 2 or result.year > 9998:
        raise ValidationError("Month year must be between 0002 and 9998.")
    return result


def shift_month(month, offset):
    year, index = divmod(month.year * 12 + month.month - 1 + offset, 12)
    return date(year, index + 1, 1)


def spending_report(actor, *, group_id, month=None):
    require_member(group_id, actor)
    selected = report_month(month)
    start, end = shift_month(selected, -11), shift_month(selected, 1)
    expenses = Expense.objects.filter(group_id=group_id)
    current = expenses.filter(expense_date__gte=selected, expense_date__lt=end)
    shares = ExpenseSplit.objects.filter(expense__in=current, user=actor)
    totals = current.aggregate(total=Sum("amount_paise"))
    categories = []
    for row in current.values("category_id", "category__name").annotate(total=Sum("amount_paise")).order_by("-total", "category_id"):
        categories.append({"id": row["category_id"], "name": row["category__name"] or "Uncategorised", "amount": format_paise(int(row["total"]))})
    monthly = {row["month"].isoformat()[:7]: int(row["total"]) for row in
               expenses.filter(expense_date__gte=start, expense_date__lt=end)
               .annotate(month=TruncMonth("expense_date")).values("month")
               .annotate(total=Sum("amount_paise"))}
    return {
        "group_id": group_id, "month": selected.isoformat()[:7], "currency": "INR",
        "summary": {"total": format_paise(int(totals["total"] or 0)), "expense_count": current.count(),
                    "your_paid": format_paise(int(current.filter(paid_by=actor).aggregate(total=Sum("amount_paise"))["total"] or 0)),
                    "your_share": format_paise(int(shares.aggregate(total=Sum("share_paise"))["total"] or 0))},
        "categories": categories,
        "months": [{"month": shift_month(start, offset).isoformat()[:7],
                    "amount": format_paise(monthly.get(shift_month(start, offset).isoformat()[:7], 0))}
                   for offset in range(12)],
    }


def csv_text(value):
    text = str(value or "")
    # CSV quoting alone does not prevent spreadsheet formula execution.
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")) else text


def expense_export(actor, *, group_id, month=None):
    require_member(group_id, actor)
    rows = Expense.objects.filter(group_id=group_id).select_related("paid_by", "category").prefetch_related("splits__user").order_by("expense_date", "id")
    if month is not None:
        selected = report_month(month)
        rows = rows.filter(expense_date__gte=selected, expense_date__lt=shift_month(selected, 1))
    return export_rows(rows, actor)


def export_rows(expenses, actor):
    yield ["expense_id", "expense_date", "description", "category", "tag", "source", "paid_by", "amount_inr", "your_share_inr", "splits_inr"]
    for expense in expenses.iterator(chunk_size=500):
        splits = sorted(expense.splits.all(), key=lambda row: row.user_id)
        yield [expense.id, expense.expense_date.isoformat(), csv_text(expense.description),
               csv_text(expense.category.name if expense.category else "Uncategorised"), csv_text(expense.tag),
               expense.source, csv_text(expense.paid_by.username), format_paise(expense.amount_paise),
               format_paise(sum(row.share_paise for row in splits if row.user_id == actor.id)),
               csv_text("; ".join(f"{row.user.username}: {format_paise(row.share_paise)}" for row in splits))]


@transaction.atomic
def settlement_nudges(actor, *, group_id):
    group = require_member(group_id, actor, lock=True)
    pending = dict(Settlement.objects.filter(group=group, receiver=actor, status="pending")
                   .values("payer_id").annotate(total=Sum("amount_paise")).values_list("payer_id", "total"))
    rows = Balance.objects.filter(group=group).filter(
        Q(user_a=actor, net_paise__gt=0) | Q(user_b=actor, net_paise__lt=0)
    ).select_related("user_a", "user_b").order_by("user_a_id", "user_b_id")
    result = []
    for row in rows:
        debtor = row.user_b if row.user_a_id == actor.id else row.user_a
        debt = abs(row.net_paise)
        reserved = min(debt, int(pending.get(debtor.id, 0)))
        available = debt - reserved
        if available:
            amount = format_paise(available)
            text = f"Hey {debtor.username}, a reminder: INR {amount} is still due to {actor.username} in {group.name}. Please record a payment in BroYouOweMe when paid so I can confirm it."
            if reserved:
                text += f" This excludes INR {format_paise(reserved)} already awaiting confirmation."
            result.append({"user_id": debtor.id, "username": debtor.username, "amount": amount,
                           "pending_amount": format_paise(reserved), "text": text})
    return result
