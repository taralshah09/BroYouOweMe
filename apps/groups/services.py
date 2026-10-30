from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import Http404

from apps.accounts.models import User
from .models import Group, Membership


def add_member_by_username(*, group_id, actor, username):
    require_member(group_id, actor, admin=True)
    if not isinstance(username, str):
        raise ValidationError("Provide an exact username.")
    user = User.objects.filter(username__iexact=username.strip(), is_active=True).first()
    if user is None:
        raise ValidationError("Unable to add this username. Share an invite link instead.")
    return add_member(group_id=group_id, actor=actor, user_id=user.pk)


def valid_invite(token):
    from django.utils import timezone
    from .models import Invite

    try:
        return Invite.objects.select_related("group").get(
            token=token, revoked_at__isnull=True, expires_at__gt=timezone.now(),
            group__deleted_at__isnull=True,
        )
    except Invite.DoesNotExist:
        raise Http404("Invite is unavailable.") from None


@transaction.atomic
def create_invite(*, group_id, actor):
    import secrets
    from datetime import timedelta
    from django.utils import timezone
    from apps.activity.services import record
    from .models import Invite

    group = require_member(group_id, actor, admin=True, lock=True)
    invite = Invite.objects.create(group=group, created_by=actor,
                                   token=secrets.token_urlsafe(32),
                                   expires_at=timezone.now() + timedelta(days=7))
    record(group_id=group.id, actor=actor, action="invite.created", entity=invite,
           after={"expires_at": invite.expires_at.isoformat()})
    return invite


@transaction.atomic
def revoke_invite(*, group_id, invite_id, actor):
    from django.utils import timezone
    from apps.activity.services import record
    from .models import Invite

    require_member(group_id, actor, admin=True, lock=True)
    try:
        invite = Invite.objects.get(pk=invite_id, group_id=group_id)
    except Invite.DoesNotExist:
        raise Http404 from None
    if invite.revoked_at is None:
        invite.revoked_at = timezone.now()
        invite.save(update_fields=["revoked_at"])
        record(group_id=group_id, actor=actor, action="invite.revoked", entity=invite)
    return invite


@transaction.atomic
def join_invite(*, token, actor):
    from django.utils import timezone
    from apps.activity.services import record

    invite = valid_invite(token)
    Group.objects.select_for_update().get(pk=invite.group_id)
    # Revocation and joining serialize on the group lock. Recheck after waiting.
    invite = valid_invite(token)
    membership, created = Membership.objects.get_or_create(group=invite.group, user=actor)
    if not created and membership.left_at is not None:
        membership.left_at = None
        membership.joined_at = timezone.now()
        membership.role = Membership.Role.MEMBER
        membership.save(update_fields=["left_at", "joined_at", "role"])
        created = True
    if created:
        record(group_id=invite.group_id, actor=actor, action="member.joined", entity=membership,
               after={"user_id": actor.pk, "role": membership.role})
    return membership


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
