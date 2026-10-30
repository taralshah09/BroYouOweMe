from django.conf import settings
from django.db import models


class Activity(models.Model):
    group = models.ForeignKey("groups.Group", on_delete=models.PROTECT, related_name="activity")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    action = models.CharField(max_length=40)
    entity_type = models.CharField(max_length=30)
    entity_id = models.PositiveBigIntegerField()
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "activity_log"
        indexes = [models.Index(fields=["group", "-created_at"], name="activity_group_date_idx")]
