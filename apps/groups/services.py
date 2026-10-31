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
    try:
        Group.objects.select_for_update().get(pk=invite.group_id)
    except Group.DoesNotExist:
        raise Http404("Invite is unavailable.") from None
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
        if membership.left_at is None:
            raise ValidationError("This user is already a member.")
        from django.utils import timezone

        membership.left_at = None
        membership.joined_at = timezone.now()
        membership.role = Membership.Role.MEMBER
        membership.save(update_fields=["left_at", "joined_at", "role"])
    return membership


def active_membership(group, user_id):
    try:
        return Membership.objects.get(group=group, user_id=user_id, left_at__isnull=True)
    except Membership.DoesNotExist:
        raise Http404("Active member not found.") from None


def require_another_admin(group, member):
    if member.role == Membership.Role.ADMIN and not group.memberships.filter(
        left_at__isnull=True, role=Membership.Role.ADMIN,
    ).exclude(pk=member.pk).exists():
        raise ValidationError("Promote another member to admin first.")


def require_departed_balances_zero(group_id):
    from django.db.models import Q
    from apps.settlements.models import Balance

    active = Membership.objects.filter(group_id=group_id, left_at__isnull=True).values("user_id")
    if Balance.objects.filter(group_id=group_id).exclude(net_paise=0).filter(
        ~Q(user_a_id__in=active) | ~Q(user_b_id__in=active),
    ).exists():
        raise ValidationError("This change would recreate a balance for someone who has left. Invite them to rejoin first.")


@transaction.atomic
def change_role(*, group_id, actor, user_id, role):
    from apps.activity.services import record

    group = require_member(group_id, actor, admin=True, lock=True)
    if role not in Membership.Role.values:
        raise ValidationError("Choose admin or member.")
    member = active_membership(group, user_id)
    if member.role != role:
        if role == Membership.Role.MEMBER:
            require_another_admin(group, member)
        before = {"user_id": member.user_id, "role": member.role}
        member.role = role
        member.save(update_fields=["role"])
        record(group_id=group.id, actor=actor, action="member.role_changed", entity=member,
               before=before, after={"user_id": member.user_id, "role": role})
    return member


@transaction.atomic
def remove_member(*, group_id, actor, user_id):
    from django.db.models import Q
    from django.utils import timezone
    from apps.activity.services import record
    from apps.settlements.models import Balance

    leaving = user_id == actor.pk
    group = require_member(group_id, actor, admin=not leaving, lock=True)
    member = active_membership(group, user_id)
    require_another_admin(group, member)
    if Balance.objects.filter(group=group).filter(
        Q(user_a_id=user_id) | Q(user_b_id=user_id),
    ).exclude(net_paise=0).exists():
        raise ValidationError("Settle every balance with this member before they leave or are removed.")
    member.left_at = timezone.now()
    member.save(update_fields=["left_at"])
    record(group_id=group.id, actor=actor, action="member.left" if leaving else "member.removed",
           entity=member, before={"user_id": member.user_id, "role": member.role},
           after={"user_id": member.user_id, "left_at": member.left_at.isoformat()})
    return member


@transaction.atomic
def delete_group(*, group_id, actor):
    from django.utils import timezone
    from apps.activity.services import record

    group = require_member(group_id, actor, admin=True, lock=True)
    if group.balances.exclude(net_paise=0).exists():
        raise ValidationError("Settle every balance before deleting this group.")
    group.deleted_at = timezone.now()
    group.save(update_fields=["deleted_at"])
    record(group_id=group.id, actor=actor, action="group.deleted", entity=group,
           before={"name": group.name}, after={"deleted_at": group.deleted_at.isoformat()})
    return group
