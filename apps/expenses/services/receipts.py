from django.core.exceptions import ValidationError

from .money import allocate_equal, paise_to_rupees, rupees_to_paise
from ..models import ExpenseItem, ExpenseItemPayee


def item_data(expense):
    return [{"kind": row.kind, "name": row.name, "amount": paise_to_rupees(row.price_paise),
             "payees": list(row.payees.order_by("user_id").values_list("user_id", flat=True))}
            for row in expense.items.all()]


def prepare_items(items, participants, total, mode):
    if not isinstance(items, list) or not 1 <= len(items) <= 100:
        raise ValidationError("A receipt needs between 1 and 100 lines.")
    rows, shares, recipients = [], {}, set()
    for position, row in enumerate(items):
        if not isinstance(row, dict) or set(row) - {"kind", "name", "amount", "payees"}:
            raise ValidationError("Each receipt line needs kind, name, amount and optional payees.")
        kind, name = row.get("kind"), row.get("name")
        if not isinstance(kind, str) or kind not in {"item", "tax", "service", "tip", "discount"} or not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
            raise ValidationError("Choose a valid line kind and a name of 1–120 characters.")
        try:
            price = rupees_to_paise(row.get("amount"))
        except ValueError as error:
            raise ValidationError(str(error)) from None
        if (kind == "discount" and price >= 0) or (kind != "discount" and price <= 0):
            raise ValidationError("Line amounts must be positive; discounts must be negative.")
        payees = row.get("payees", [])
        if not isinstance(payees, list) or any(type(pk) is not int for pk in payees) or len(set(payees)) != len(payees) or not set(payees) <= set(participants):
            raise ValidationError("Item payees must be unique selected participants.")
        if kind != "item" and payees:
            raise ValidationError("Only item lines can have payees.")
        rows.append(dict(kind=kind, name=name.strip(), price_paise=price, position=position, payees=payees))
        if kind == "item":
            users = payees or participants
            recipients.update(users)
            for pk, share in allocate_equal(price, users).items():
                shares[pk] = shares.get(pk, 0) + share
    if not recipients:
        raise ValidationError("Include at least one item.")
    if sum(row["price_paise"] for row in rows) != total:
        raise ValidationError("Receipt lines must add up exactly to the expense total. Correct missing lines or the total.")
    if mode == "itemised":
        charges = sum(row["price_paise"] for row in rows if row["kind"] != "item")
        for pk, share in allocate_equal(charges, sorted(recipients)).items():
            shares[pk] += share
        if any(value <= 0 for value in shares.values()):
            raise ValidationError("Every item recipient must owe at least one paisa after discounts.")
    else:
        shares = allocate_equal(total, participants)
    return rows, shares


def save_items(expense, rows):
    expense.items.all().delete()
    for values in rows:
        values = values.copy()
        payees = values.pop("payees")
        item = ExpenseItem.objects.create(expense=expense, **values)
        ExpenseItemPayee.objects.bulk_create([ExpenseItemPayee(item=item, user_id=pk) for pk in payees])
