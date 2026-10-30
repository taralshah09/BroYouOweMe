from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render

from apps.accounts.http import endpoint, payload, positive_id, wants_html
from apps.accounts.models import User
from apps.groups.services import require_member
from apps.settlements.services import rupee_value
from .models import Expense
from .services import create_expense, equal_shares


def expense_data(expense):
    return {
        "id": expense.id, "group_id": expense.group_id, "created_by": expense.created_by_id,
        "description": expense.description, "amount": rupee_value(expense.amount_paise),
        "paid_by": expense.paid_by.username, "paid_by_id": expense.paid_by_id,
        "expense_date": expense.expense_date.isoformat(),
    }


@endpoint(["POST"])
def expenses(request):
    data = payload(request, ["group_id", "paid_by", "amount", "description", "expense_date"])
    expense = create_expense(
        actor=request.user, group_id=positive_id(data.get("group_id")),
        paid_by=positive_id(data.get("paid_by")), amount=data.get("amount"),
        description=data.get("description"), expense_date=data.get("expense_date"),
    )
    return redirect("group-detail", group_id=expense.group_id) if wants_html(request) else JsonResponse(expense_data(expense), status=201)


@endpoint(["GET"])
def group_expenses(request, group_id):
    group = require_member(group_id, request.user)
    rows = Expense.objects.filter(group=group).select_related("paid_by").order_by("-created_at", "-id")
    data = [expense_data(expense) for expense in rows]
    if wants_html(request):
        return render(request, "expenses/list.html", {"group": group, "expenses": data})
    return JsonResponse(data, safe=False)


@endpoint(["GET"])
def expense_detail(request, expense_id):
    try:
        expense = Expense.objects.select_related("paid_by").get(pk=expense_id)
    except Expense.DoesNotExist:
        raise Http404 from None
    require_member(expense.group_id, request.user)
    data = expense_data(expense)
    shares = equal_shares(expense)
    usernames = dict(User.objects.filter(pk__in=shares).values_list("id", "username"))
    data["splits"] = [{"user_id": pk, "username": usernames[pk], "amount": rupee_value(share)} for pk, share in shares.items()]
    if wants_html(request):
        return render(request, "expenses/detail.html", {"expense": data})
    return JsonResponse(data)
