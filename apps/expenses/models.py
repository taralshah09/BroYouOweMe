from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.groups.models import ActiveManager


class Expense(models.Model):
    group = models.ForeignKey("groups.Group", on_delete=models.PROTECT, related_name="expenses")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_expenses")
    paid_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="paid_expenses")
    amount_paise = models.BigIntegerField()
    description = models.CharField(max_length=200)
    expense_date = models.DateField(default=timezone.localdate)
    split_mode = models.CharField(max_length=10, default="equal", choices=[("equal", "Equal")])
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
            models.CheckConstraint(condition=models.Q(split_mode="equal"), name="phase1_equal_only"),
            models.CheckConstraint(condition=models.Q(source="manual"), name="phase1_manual_only"),
        ]
        indexes = [models.Index(fields=["group", "-expense_date"], condition=models.Q(deleted_at__isnull=True), name="active_expense_date_idx")]
