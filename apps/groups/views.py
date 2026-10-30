from django.http import JsonResponse
from django.shortcuts import redirect, render

from apps.accounts.http import endpoint, payload, positive_id, wants_html
from apps.expenses.forms import ExpenseForm
from apps.expenses.models import Expense
from apps.expenses.views import expense_data
from apps.settlements.services import balances_for
from .forms import GroupForm, MemberForm
from .models import Group
from .services import add_member, create_group, require_member


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
        return render(request, "groups/list.html", {"groups": rows, "form": form}, status=400 if request.method == "POST" else 200)
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
    })


@endpoint(["GET", "POST"])
def members(request, group_id):
    group = require_member(group_id, request.user)
    if request.method == "POST":
        data = payload(request, ["user_id"])
        member = add_member(group_id=group_id, actor=request.user, user_id=positive_id(data.get("user_id")))
        if wants_html(request):
            return redirect("group-detail", group_id=group.id)
        return JsonResponse({"user_id": member.user_id, "username": member.user.username, "role": member.role}, status=201)
    rows = group.memberships.filter(left_at__isnull=True).select_related("user").order_by("user_id")
    if wants_html(request):
        return render(request, "groups/members.html", {"group": group, "members": rows})
    return JsonResponse([{"user_id": row.user_id, "username": row.user.username, "role": row.role} for row in rows], safe=False)
