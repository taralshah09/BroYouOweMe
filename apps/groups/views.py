from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render

from apps.accounts.http import endpoint, payload, positive_id, wants_html
from apps.expenses.forms import ExpenseForm
from apps.expenses.models import Expense
from apps.expenses.views import expense_data
from apps.settlements.services import balances_for, overview_for
from .forms import GroupForm, MemberForm
from .models import Group
from .services import add_member, add_member_by_username, create_group, require_member


def group_data(group):
    return {"id": group.id, "name": group.name, "created_by": group.created_by_id}


@endpoint(["GET", "POST"])
def groups(request):
    form = GroupForm(payload(request, ["name"]) if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        group = create_group(actor=request.user, name=form.cleaned_data["name"])
        return redirect("group-detail", group_id=group.id) if wants_html(request) else JsonResponse(group_data(group), status=201)
    rows = Group.objects.filter(memberships__user=request.user, memberships__left_at__isnull=True).order_by("id")
    if wants_html(request):
        return render(request, "groups/list.html", {"groups": rows, "form": form, "overview": overview_for(request.user)}, status=400 if request.method == "POST" else 200)
    if request.method == "POST":
        return JsonResponse({"errors": form.errors}, status=400)
    return JsonResponse([group_data(group) for group in rows], safe=False)


@endpoint(["GET"])
def group_detail(request, group_id):
    group = require_member(group_id, request.user)
    if not wants_html(request):
        return JsonResponse(group_data(group))
    members = group.memberships.filter(left_at__isnull=True).select_related("user").order_by("user_id")
    return render(request, "groups/detail.html", {
        "group": group, "members": members,
        "is_admin": members.filter(user=request.user, role="admin").exists(),
        "member_form": MemberForm(), "expense_form": ExpenseForm(group=group, initial={"paid_by": request.user.id}),
        "expenses": [expense_data(expense) for expense in Expense.objects.filter(group=group).select_related("paid_by").order_by("-created_at", "-id")],
        "balances": balances_for(request.user, group_id=group.id),
        "overview": overview_for(request.user, group_id=group.id),
    })


@endpoint(["GET", "POST"])
def members(request, group_id):
    group = require_member(group_id, request.user)
    if request.method == "POST":
        data = payload(request, ["user_id", "username"])
        if "username" in data:
            member = add_member_by_username(group_id=group_id, actor=request.user, username=data["username"])
        else:
            member = add_member(group_id=group_id, actor=request.user, user_id=positive_id(data.get("user_id")))
        if wants_html(request):
            return redirect("group-detail", group_id=group.id)
        return JsonResponse({"user_id": member.user_id, "username": member.user.username, "role": member.role}, status=201)
    rows = group.memberships.filter(left_at__isnull=True).select_related("user").order_by("user_id")
    if wants_html(request):
        return render(request, "groups/members.html", {
            "group": group, "members": rows,
            "is_admin": rows.filter(user=request.user, role="admin").exists(),
        })
    return JsonResponse([{"user_id": row.user_id, "username": row.user.username, "role": row.role} for row in rows], safe=False)


@endpoint(["POST"])
def member_role(request, group_id, user_id):
    from .services import change_role

    data = payload(request, ["role"])
    member = change_role(group_id=group_id, actor=request.user, user_id=user_id, role=data.get("role"))
    if wants_html(request):
        return redirect("members", group_id=group_id)
    return JsonResponse({"user_id": member.user_id, "role": member.role})


@endpoint(["POST"])
def member_remove(request, group_id, user_id):
    from .services import remove_member

    payload(request, [])
    # Self-service departure has its own explicit endpoint.
    require_member(group_id, request.user, admin=True)
    remove_member(group_id=group_id, actor=request.user, user_id=user_id)
    if wants_html(request):
        if user_id == request.user.pk:
            return redirect("groups")
        return redirect("members", group_id=group_id)
    return JsonResponse({"user_id": user_id, "active": False})


@endpoint(["POST"])
def group_leave(request, group_id):
    from .services import remove_member

    payload(request, [])
    remove_member(group_id=group_id, actor=request.user, user_id=request.user.pk)
    return redirect("groups") if wants_html(request) else JsonResponse({"user_id": request.user.pk, "active": False})


@endpoint(["POST"])
def group_delete(request, group_id):
    from .services import delete_group

    payload(request, [])
    delete_group(group_id=group_id, actor=request.user)
    return redirect("groups") if wants_html(request) else JsonResponse({"id": group_id, "deleted": True})


def invite_data(request, invite):
    from django.urls import reverse
    from django.utils import timezone

    return {"id": invite.id, "url": request.build_absolute_uri(reverse("invite-preview", args=[invite.token])),
            "qr_url": reverse("invite-qr", args=[invite.group_id, invite.pk]),
            "active": invite.revoked_at is None and invite.expires_at > timezone.now(),
            "expires_at": invite.expires_at.isoformat(),
            "revoked_at": invite.revoked_at.isoformat() if invite.revoked_at else None}


@endpoint(["GET", "POST"])
def invites(request, group_id):
    from .services import create_invite

    group = require_member(group_id, request.user, admin=True)
    if request.method == "POST":
        payload(request, [])
        invite = create_invite(group_id=group_id, actor=request.user)
        if not wants_html(request):
            return JsonResponse(invite_data(request, invite), status=201)
        return redirect("invites", group_id=group_id)
    rows = [invite_data(request, row) for row in group.invites.order_by("-id")]
    if wants_html(request):
        return render(request, "groups/invites.html", {"group": group, "invites": rows})
    return JsonResponse(rows, safe=False)


@endpoint(["POST", "DELETE"])
def invite_revoke(request, group_id, invite_id):
    from .services import revoke_invite

    payload(request, [])
    row = revoke_invite(group_id=group_id, invite_id=invite_id, actor=request.user)
    return redirect("invites", group_id=group_id) if wants_html(request) else JsonResponse(invite_data(request, row))


@endpoint(["GET"])
def invite_qr(request, group_id, invite_id):
    from django.shortcuts import get_object_or_404
    import qrcode
    from qrcode.image.svg import SvgPathFillImage
    from .services import valid_invite

    group = require_member(group_id, request.user, admin=True)
    row = get_object_or_404(group.invites, pk=invite_id)
    valid_invite(row.token)
    svg = qrcode.make(invite_data(request, row)["url"], image_factory=SvgPathFillImage).to_string()
    response = HttpResponse(svg, content_type="image/svg+xml")
    response["Cache-Control"] = "no-store"
    return response


@endpoint(["GET"], public=True)
def invite_preview(request, token):
    from .services import valid_invite

    row = valid_invite(token)
    data = {"group_name": row.group.name, "member_count": row.group.memberships.filter(left_at__isnull=True).count()}
    response = render(request, "groups/invite.html", {**data, "token": token}) if wants_html(request) else JsonResponse(data)
    response["Referrer-Policy"] = "no-referrer"
    response["Cache-Control"] = "no-store"
    return response


@endpoint(["POST"], public=True)
def invite_join(request, token):
    from .services import join_invite, valid_invite

    payload(request, [])
    valid_invite(token)
    if not request.user.is_authenticated:
        request.session["pending_invite"] = token
        return redirect("signup") if wants_html(request) else JsonResponse({"signup_required": True}, status=401)
    membership = join_invite(token=token, actor=request.user)
    return redirect("group-detail", group_id=membership.group_id) if wants_html(request) else JsonResponse({"group_id": membership.group_id})
