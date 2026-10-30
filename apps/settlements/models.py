from django.conf import settings
from django.db import models


class Balance(models.Model):
    pk = models.CompositePrimaryKey("group_id", "user_a_id", "user_b_id")
    group = models.ForeignKey("groups.Group", on_delete=models.PROTECT, related_name="balances")
    user_a = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="balances_as_a")
    user_b = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="balances_as_b")
    net_paise = models.BigIntegerField()

    class Meta:
        db_table = "balances"
        constraints = [models.CheckConstraint(condition=models.Q(user_a__lt=models.F("user_b")), name="balance_pair_order")]
