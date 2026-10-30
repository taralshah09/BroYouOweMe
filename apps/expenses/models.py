from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.groups.models import ActiveManager


class Category(models.Model):
    group = models.ForeignKey("groups.Group", null=True, blank=True, on_delete=models.PROTECT)
    name = models.CharField(max_length=40)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "categories"
        constraints = [
            models.UniqueConstraint(models.F("group"), models.functions.Lower("name"), name="group_category_name_unique"),
            models.UniqueConstraint(models.functions.Lower("name"), condition=models.Q(group__isnull=True), name="default_category_name_unique"),
        ]

    def __str__(self):
        return self.name


class Expense(models.Model):
    group = models.ForeignKey("groups.Group", on_delete=models.PROTECT, related_name="expenses")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_expenses")
    paid_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="paid_expenses")
    amount_paise = models.BigIntegerField()
    description = models.CharField(max_length=200)
    expense_date = models.DateField(default=timezone.localdate)
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.PROTECT, related_name="expenses")
    tag = models.CharField(max_length=40, null=True, blank=True)
    split_mode = models.CharField(max_length=10, default="equal", choices=[("equal", "Equal"), ("unequal", "Unequal")])
    source = models.CharField(max_length=10, default="manual", choices=[("manual", "Manual")])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        db_table = "expenses"
        constraints = [
            models.CheckConstraint(condition=models.Q(amount_paise__gt=0), name="expense_amount_positive"),
            models.CheckConstraint(condition=models.Q(split_mode__in=["equal", "unequal"]), name="expense_split_mode_valid"),
            models.CheckConstraint(condition=models.Q(source="manual"), name="phase1_manual_only"),
        ]
        indexes = [models.Index(fields=["group", "-expense_date"], condition=models.Q(deleted_at__isnull=True), name="active_expense_date_idx"), models.Index(fields=["group", "category"], name="expense_category_idx")]


class ExpenseSplit(models.Model):
    expense = models.ForeignKey(Expense, on_delete=models.PROTECT, related_name="splits")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    share_paise = models.BigIntegerField()

    class Meta:
        db_table = "expense_splits"
        constraints = [
            models.UniqueConstraint(fields=["expense", "user"], name="expense_split_user_unique"),
            models.CheckConstraint(condition=models.Q(share_paise__gt=0), name="expense_share_positive"),
        ]
