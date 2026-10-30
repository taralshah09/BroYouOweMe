from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import Http404

from apps.accounts.models import User
from .models import Group, Membership


def require_member(group_id, actor, *, admin=False, lock=False):
    groups = Group.objects.select_for_update() if lock else Group.objects.all()
    try:
        group = groups.get(pk=group_id)
    except Group.DoesNotExist:
        raise Http404("Group not found.") from None
    membership = Membership.objects.filter(group=group, user=actor, left_at__isnull=True).first()
    if membership is None or (admin and membership.role != Membership.Role.ADMIN):
        raise PermissionDenied("Active group membership" + (" with admin role" if admin else "") + " required.")
    return group


@transaction.atomic
def create_group(*, actor, name):
    group = Group(name=name.strip() if isinstance(name, str) else "", created_by=actor)
    group.full_clean()
    group.save()
    Membership.objects.create(group=group, user=actor, role=Membership.Role.ADMIN)
    return group


@transaction.atomic
def add_member(*, group_id, actor, user_id):
    group = require_member(group_id, actor, admin=True, lock=True)
    try:
        user = User.objects.get(pk=user_id, is_active=True)
    except User.DoesNotExist:
        raise ValidationError("Choose an existing active user.") from None
    membership, created = Membership.objects.get_or_create(group=group, user=user)
    if not created:
        raise ValidationError("This user is already a member.")
    return membership
