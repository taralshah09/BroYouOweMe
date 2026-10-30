from datetime import date

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.activity.services import record
from apps.groups.models import Membership
from apps.groups.services import require_member
from .money import allocate_equal, rupees_to_paise
from ..models import Category, Expense, ExpenseSplit
from .receipts import item_data, prepare_items, save_items


def money(amount):
    try:
        return rupees_to_paise(amount)
    except ValueError as error:
        raise ValidationError(str(error)) from None


def equal_shares(expense):
    # Kept as the public share accessor for Phase 1 callers.
    return dict(expense.splits.order_by("user_id").values_list("user_id", "share_paise"))


def snapshot(expense):
    return {
        "paid_by": expense.paid_by_id, "amount_paise": expense.amount_paise,
        "description": expense.description, "expense_date": expense.expense_date.isoformat(),
        "split_mode": expense.split_mode, "category": expense.category_id, "tag": expense.tag,
        "source": expense.source, "items": item_data(expense),
        "splits": [{"user_id": pk, "share_paise": share} for pk, share in equal_shares(expense).items()],
        "deleted_at": expense.deleted_at.isoformat() if expense.deleted_at else None,
    }


def apply_expense(expense, direction=1):
    from apps.settlements.services import apply_debt

    for user_id, share in equal_shares(expense).items():
        if user_id != expense.paid_by_id:
            apply_debt(expense.group_id, user_id, expense.paid_by_id, direction * share)


def prepare(expense, *, paid_by=None, amount=None, description=None, expense_date=None,
            participants=None, splits=None, split_mode=None, category=None, tag=None,
            source="manual", items=None):
    members = set(Membership.objects.filter(group_id=expense.group_id, left_at__isnull=True).values_list("user_id", flat=True))
    if type(paid_by) is not int or paid_by not in members:
        raise ValidationError("The payer must be an active group member.")
    amount_paise = money(amount)
    if amount_paise <= 0:
        raise ValidationError("Amount must be greater than zero.")
    mode = split_mode if split_mode is not None else ("unequal" if splits is not None else "equal")
    if not isinstance(mode, str) or mode not in {"equal", "unequal", "itemised"}:
        raise ValidationError("Split mode must be equal, unequal or itemised.")
    if not isinstance(source, str) or source not in {"manual", "ocr", "voice"}:
        raise ValidationError("Choose a supported expense source.")
    if source == "ocr" and paid_by != expense.created_by_id:
        raise ValidationError("The receipt uploader must be the payer.")
    if source == "ocr" and (items is None or mode == "unequal"):
        raise ValidationError("Receipts require items and equal or itemised splits.")
    if source != "ocr" and (items is not None or mode == "itemised"):
        raise ValidationError("Receipt items require source ocr.")
    if participants is not None:
        if not isinstance(participants, list) or not participants or any(type(pk) is not int for pk in participants) or len(set(participants)) != len(participants) or not set(participants) <= members:
            raise ValidationError("Participants must be unique active group member IDs.")
    expense._receipt_rows = None
    if source == "ocr":
        if splits is not None:
            raise ValidationError("Receipt shares are computed from the reviewed items.")
        expense._receipt_rows, shares = prepare_items(items, participants if participants is not None else sorted(members), amount_paise, mode)
    elif mode == "unequal":
        if not isinstance(splits, list) or not splits:
            raise ValidationError("Unequal splits require a list of user_id and amount objects.")
        shares = {}
        for row in splits:
            if not isinstance(row, dict) or set(row) != {"user_id", "amount"}:
                raise ValidationError("Each split requires user_id and amount.")
            pk = row["user_id"]
            if type(pk) is not int or pk not in members or pk in shares:
                raise ValidationError("Split users must be unique active group members.")
            shares[pk] = money(row["amount"])
        if participants is not None and set(participants) != shares.keys():
            raise ValidationError("Participants must match the split users.")
        if sum(shares.values()) != amount_paise:
            raise ValidationError("Split amounts must add up exactly to the expense total.")
    else:
        if splits is not None:
            raise ValidationError("Equal splits accept participants, not explicit amounts.")
        shares = allocate_equal(amount_paise, participants if participants is not None else sorted(members))
    if any(share <= 0 for share in shares.values()):
        raise ValidationError("Every participant must have a share of at least one paisa.")
    if isinstance(expense_date, str):
        try:
            expense_date = parse_date(expense_date)
        except ValueError:
            expense_date = None
        if expense_date is None:
            raise ValidationError("Use an expense date in YYYY-MM-DD format.")
    if expense_date is not None and type(expense_date) is not date:
        raise ValidationError("Use an expense date in YYYY-MM-DD format.")
    if category is not None and (type(category) is not int or not Category.objects.filter(Q(group_id=expense.group_id) | Q(group__isnull=True), pk=category).exists()):
        raise ValidationError("Choose a default category or one belonging to this group.")
    if tag is not None and not isinstance(tag, str):
        raise ValidationError("Tag must be text.")
    expense.paid_by_id = paid_by
    expense.amount_paise = amount_paise
    expense.description = description.strip() if isinstance(description, str) else ""
    expense.expense_date = expense_date or timezone.localdate()
    expense.split_mode = mode
    expense.source = source
    expense.category_id = category
    expense.tag = tag.strip() or None if tag is not None else None
    expense.full_clean()
    return shares


def save_splits(expense, shares):
    ExpenseSplit.objects.bulk_create([ExpenseSplit(expense=expense, user_id=pk, share_paise=share) for pk, share in sorted(shares.items())])


@transaction.atomic
def create_expense(*, actor, group_id, **values):
    group = require_member(group_id, actor, lock=True)
    expense = Expense(group=group, created_by=actor)
    shares = prepare(expense, **values)
    expense.save()
    save_splits(expense, shares)
    if expense._receipt_rows is not None:
        save_items(expense, expense._receipt_rows)
    apply_expense(expense)
    record(group_id=group.id, actor=actor, action="expense.created", entity=expense, after=snapshot(expense))
    return expense


def locked_expense(expense_id, actor):
    try:
        group_id = Expense.objects.values_list("group_id", flat=True).get(pk=expense_id)
    except Expense.DoesNotExist:
        raise Http404 from None
    require_member(group_id, actor, lock=True)
    try:
        expense = Expense.objects.get(pk=expense_id)
    except Expense.DoesNotExist:
        raise Http404 from None
    if expense.created_by_id != actor.id:
        raise PermissionDenied("Only the expense creator can edit or delete it.")
    return expense


@transaction.atomic
def update_expense(*, actor, expense_id, **changes):
    expense = locked_expense(expense_id, actor)
    before = snapshot(expense)
    values = dict(paid_by=expense.paid_by_id,
                  amount=f"{expense.amount_paise // 100}.{expense.amount_paise % 100:02d}",
                  description=expense.description, expense_date=expense.expense_date,
                  category=expense.category_id, tag=expense.tag, split_mode=expense.split_mode,
                  source=expense.source)
    if expense.source == "ocr":
        if "source" in changes and changes["source"] != "ocr":
            raise ValidationError("A receipt expense must retain its receipt items.")
        values["items"] = item_data(expense)
    if not ({"participants", "splits", "split_mode"} & changes.keys()):
        if expense.split_mode in {"equal", "itemised"}:
            values["participants"] = list(equal_shares(expense))
        else:
            values["splits"] = [{"user_id": pk, "amount": f"{share // 100}.{share % 100:02d}"} for pk, share in equal_shares(expense).items()]
    elif "split_mode" not in changes:
        values["split_mode"] = expense.split_mode if expense.source == "ocr" else ("unequal" if "splits" in changes else "equal")
    values.update(changes)
    # Reverse the saved allocation before replacing its rows. All writes roll back on failure.
    apply_expense(expense, -1)
    shares = prepare(expense, **values)
    expense.save()
    expense.splits.all().delete()
    save_splits(expense, shares)
    if expense._receipt_rows is not None:
        save_items(expense, expense._receipt_rows)
    apply_expense(expense)
    record(group_id=expense.group_id, actor=actor, action="expense.updated", entity=expense, before=before, after=snapshot(expense))
    return expense


@transaction.atomic
def delete_expense(*, actor, expense_id):
    expense = locked_expense(expense_id, actor)
    before = snapshot(expense)
    apply_expense(expense, -1)
    expense.deleted_at = timezone.now()
    expense.save(update_fields=["deleted_at", "updated_at"])
    record(group_id=expense.group_id, actor=actor, action="expense.deleted", entity=expense, before=before, after=snapshot(expense))
    return expense


@transaction.atomic
def manage_category(*, actor, group_id, name=None, category_id=None, delete=False):
    require_member(group_id, actor, lock=True)
    if category_id is None:
        category = Category(group_id=group_id, created_by=actor)
        action = "category.created"
        before = None
    else:
        try:
            category = Category.objects.get(pk=category_id, group_id=group_id)
        except Category.DoesNotExist:
            raise ValidationError("Only this group's custom categories can be changed.") from None
        before = {"name": category.name}
        action = "category.deleted" if delete else "category.updated"
    if delete:
        if Expense.all_objects.filter(category=category).exists():
            raise ValidationError("A category used by an expense cannot be deleted.")
        record(group_id=group_id, actor=actor, action=action, entity=category, before=before)
        category.delete()
        return None
    category.name = name.strip() if isinstance(name, str) else ""
    if Category.objects.filter(Q(group_id=group_id) | Q(group__isnull=True), name__iexact=category.name).exclude(pk=category.pk).exists():
        raise ValidationError("A category with this name already exists.")
    category.full_clean()
    category.save()
    record(group_id=group_id, actor=actor, action=action, entity=category, before=before, after={"name": category.name})
    return category
