from django.db import migrations


def materialize(apps, schema_editor):
    alias = schema_editor.connection.alias
    Expense = apps.get_model("expenses", "Expense")
    Split = apps.get_model("expenses", "ExpenseSplit")
    Category = apps.get_model("expenses", "Category")
    Membership = apps.get_model("groups", "Membership")
    Activity = apps.get_model("activity", "Activity")
    Group = apps.get_model("groups", "Group")
    # Serialize the transition with every service that writes the ledger.
    list(Group.objects.using(alias).select_for_update().order_by("pk"))
    for name in ["Food", "Travel", "Stay", "Shopping", "Entertainment", "Utilities", "Other"]:
        Category.objects.using(alias).create(name=name)
    for expense in Expense.objects.using(alias).all().iterator():
        users = list(Membership.objects.using(alias).filter(group_id=expense.group_id, joined_at__lte=expense.created_at).order_by("user_id").values_list("user_id", flat=True))
        if not users:
            raise RuntimeError("Cannot materialize an expense without historical participants.")
        base, remainder = divmod(expense.amount_paise, len(users))
        shares = [{"user_id": pk, "share_paise": base + (index < remainder)} for index, pk in enumerate(users)]
        if any(row["share_paise"] <= 0 for row in shares):
            raise RuntimeError("Cannot materialize nonpositive historical shares.")
        Split.objects.using(alias).bulk_create([Split(expense_id=expense.pk, **row) for row in shares])
        event = Activity.objects.using(alias).create(
            group_id=expense.group_id, actor_id=expense.created_by_id,
            action="expense.created", entity_type="expense", entity_id=expense.pk,
            after={"paid_by": expense.paid_by_id, "amount_paise": expense.amount_paise,
                   "description": expense.description, "expense_date": expense.expense_date.isoformat(),
                   "split_mode": "equal", "category": None, "tag": None,
                   "splits": shares, "deleted_at": expense.deleted_at.isoformat() if expense.deleted_at else None},
        )
        Activity.objects.using(alias).filter(pk=event.pk).update(created_at=expense.created_at)


class Migration(migrations.Migration):
    dependencies = [("expenses", "0002_category_expensesplit_and_more"), ("activity", "0001_initial")]
    operations = [migrations.RunPython(materialize)]
