from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.groups.models import Membership
from apps.groups.services import require_member
from .money import allocate_equal, rupees_to_paise
from ..models import Expense


def equal_shares(expense):
    # Phase 1 membership is append-only. Phase 2 replaces this with split rows
    # before membership removal/rejoining or expense edits become available.
    user_ids = Membership.objects.filter(
        group_id=expense.group_id, joined_at__lte=expense.created_at,
    ).values_list("user_id", flat=True)
    return allocate_equal(expense.amount_paise, user_ids)


@transaction.atomic
def create_expense(*, actor, group_id, paid_by, amount, description, expense_date=None):
    from apps.settlements.services import apply_debt

    group = require_member(group_id, actor, lock=True)
    try:
        amount_paise = rupees_to_paise(amount)
    except ValueError as error:
        raise ValidationError(str(error)) from None
    members = list(Membership.objects.filter(group=group, left_at__isnull=True).order_by("user_id").values_list("user_id", flat=True))
    if type(paid_by) is not int or paid_by not in members:
        raise ValidationError("The payer must be an active group member.")
    if amount_paise <= 0:
        raise ValidationError("Amount must be greater than zero.")
    shares = allocate_equal(amount_paise, members)
    if any(share <= 0 for share in shares.values()):
        raise ValidationError("Amount must allow at least one paisa per member.")
    if isinstance(expense_date, str):
        try:
            expense_date = parse_date(expense_date)
        except ValueError:
            expense_date = None
        if expense_date is None:
            raise ValidationError("Use an expense date in YYYY-MM-DD format.")
    if expense_date is not None and type(expense_date) is not date:
        raise ValidationError("Use an expense date in YYYY-MM-DD format.")
    expense = Expense(
        group=group, created_by=actor, paid_by_id=paid_by, amount_paise=amount_paise,
        description=description.strip() if isinstance(description, str) else "",
        expense_date=expense_date or timezone.localdate(),
    )
    expense.full_clean()
    expense.save()
    for user_id, share in shares.items():
        if user_id != paid_by:
            apply_debt(group.id, user_id, paid_by, share)
    return expense
