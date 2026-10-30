from .models import Activity


def record(*, group_id, actor, action, entity, before=None, after=None):
    return Activity.objects.create(
        group_id=group_id, actor=actor, action=action,
        entity_type=entity._meta.model_name, entity_id=entity.pk,
        before=before, after=after,
    )
