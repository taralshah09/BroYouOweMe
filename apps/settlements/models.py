from django.conf import settings
from django.db import models


class Settlement(models.Model):
    group = models.ForeignKey("groups.Group", on_delete=models.PROTECT, related_name="settlements")
    payer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="sent_settlements")
    receiver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="received_settlements")
    amount_paise = models.BigIntegerField()
    status = models.CharField(max_length=10, default="pending", choices=[(value, value.title()) for value in ["pending", "confirmed", "rejected", "cancelled"]])
    note = models.CharField(max_length=200, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "settlements"
        constraints = [
            models.CheckConstraint(condition=models.Q(amount_paise__gt=0), name="settlement_amount_positive"),
            models.CheckConstraint(condition=~models.Q(payer=models.F("receiver")), name="settlement_distinct_users"),
            models.CheckConstraint(condition=models.Q(status__in=["pending", "confirmed", "rejected", "cancelled"]), name="settlement_status_valid"),
        ]
        indexes = [models.Index(fields=["group", "status"], name="settlement_status_idx")]


class Balance(models.Model):
    pk = models.CompositePrimaryKey("group_id", "user_a_id", "user_b_id")
    group = models.ForeignKey("groups.Group", on_delete=models.PROTECT, related_name="balances")
    user_a = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="balances_as_a")
    user_b = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="balances_as_b")
    net_paise = models.BigIntegerField()

    class Meta:
        db_table = "balances"
        constraints = [models.CheckConstraint(condition=models.Q(user_a__lt=models.F("user_b")), name="balance_pair_order")]
