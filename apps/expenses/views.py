from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.utils.dateparse import parse_date

from apps.accounts.http import endpoint, payload, positive_id, wants_html
from apps.groups.services import require_member
from apps.settlements.services import rupee_value
from .forms import ExpenseForm
from .models import Category, Expense
from .services import create_expense, delete_expense, equal_shares, manage_category, update_expense


EXPENSE_FIELDS = ["paid_by", "amount", "description", "expense_date", "participants", "splits", "split_mode", "category", "tag"]


def expense_data(expense):
    return {
        "id": expense.id, "group_id": expense.group_id, "created_by": expense.created_by_id,
        "description": expense.description, "amount": rupee_value(expense.amount_paise),
        "paid_by": expense.paid_by.username, "paid_by_id": expense.paid_by_id,
        "expense_date": expense.expense_date.isoformat(), "split_mode": expense.split_mode,
        "category": expense.category_id, "tag": expense.tag,
    }


def expense_input(request, group, *, create=False):
    if request.content_type == "application/json":
        data = payload(request, EXPENSE_FIELDS + (["group_id"] if create else []))
        data.pop("group_id", None)
        for key in ["paid_by", "category"]:
            if key in data and data[key] is not None:
                data[key] = positive_id(data[key])
        return data
    form = ExpenseForm(request.POST, group=group)
    payload(request, list(form.fields) + ["group_id"])
    if not form.is_valid():
        raise ValidationError(form.errors.as_data())
    return form.service_values()


@endpoint(["POST"])
def expenses(request):
    data = payload(request, EXPENSE_FIELDS + ["group_id"]) if request.content_type == "application/json" else request.POST
    group = require_member(positive_id(data.get("group_id")), request.user)
    expense = create_expense(actor=request.user, group_id=group.id, **expense_input(request, group, create=True))
    return redirect("group-detail", group_id=expense.group_id) if wants_html(request) else JsonResponse(expense_data(expense), status=201)


@endpoint(["GET"])
def group_expenses(request, group_id):
    group = require_member(group_id, request.user)
    rows = Expense.objects.filter(group=group).select_related("paid_by").order_by("-created_at", "-id")
    if "category" in request.GET:
        rows = rows.filter(category_id=positive_id(request.GET["category"]))
    for param, lookup in [("date_from", "expense_date__gte"), ("date_to", "expense_date__lte")]:
        if param in request.GET:
            try:
                value = parse_date(request.GET[param])
            except ValueError:
                value = None
            if value is None:
                raise ValidationError("Date filters must use YYYY-MM-DD.")
            rows = rows.filter(**{lookup: value})
    if request.GET.get("search"):
        rows = rows.filter(Q(description__icontains=request.GET["search"]) | Q(tag__icontains=request.GET["search"]))
    data = [expense_data(expense) for expense in rows]
    if wants_html(request):
        return render(request, "expenses/list.html", {"group": group, "expenses": data})
    return JsonResponse(data, safe=False)


@endpoint(["GET", "PATCH", "DELETE", "POST"])
def expense_detail(request, expense_id):
    try:
        expense = Expense.objects.select_related("paid_by").get(pk=expense_id)
    except Expense.DoesNotExist:
        raise Http404 from None
    group = require_member(expense.group_id, request.user)
    if request.method == "DELETE":
        delete_expense(actor=request.user, expense_id=expense_id)
        return JsonResponse({"deleted": True})
    if request.method in {"PATCH", "POST"}:
        expense = update_expense(actor=request.user, expense_id=expense_id, **expense_input(request, group))
        if wants_html(request):
            return redirect("expense-detail", expense_id=expense.id)
    data = expense_data(expense)
    data["splits"] = [{"user_id": row.user_id, "username": row.user.username, "amount": rupee_value(row.share_paise)} for row in expense.splits.select_related("user").order_by("user_id")]
    if wants_html(request):
        initial = dict(data, paid_by=expense.paid_by_id, participants=list(equal_shares(expense)))
        if expense.split_mode == "unequal":
            initial.update({f"share_{row['user_id']}": row["amount"] for row in data["splits"]})
        return render(request, "expenses/detail.html", {"expense": data, "can_edit": request.user.id == expense.created_by_id, "form": ExpenseForm(group=group, initial=initial)})
    return JsonResponse(data)


@endpoint(["POST"])
def expense_delete(request, expense_id):
    payload(request, [])
    expense = delete_expense(actor=request.user, expense_id=expense_id)
    return redirect("group-detail", group_id=expense.group_id) if wants_html(request) else JsonResponse({"deleted": True})


@endpoint(["GET", "POST", "PATCH", "DELETE"])
def categories(request, group_id, category_id=None):
    group = require_member(group_id, request.user)
    if category_id is None and request.method not in {"GET", "POST"} or category_id is not None and request.method == "GET":
        raise Http404
    if request.method != "GET":
        data = payload(request, ["name", "action"] if request.content_type != "application/json" else ["name"])
        delete = request.method == "DELETE" or data.pop("action", None) == "delete"
        category = manage_category(actor=request.user, group_id=group.id, category_id=category_id, name=data.get("name"), delete=delete)
        if wants_html(request):
            return redirect("categories", group_id=group.id)
        return JsonResponse({"deleted": True} if delete else {"id": category.id, "name": category.name, "group_id": category.group_id}, status=201 if category_id is None else 200)
    rows = Category.objects.filter(Q(group=group) | Q(group__isnull=True)).order_by("name")
    if wants_html(request):
        return render(request, "expenses/categories.html", {"group": group, "categories": rows})
    return JsonResponse([{"id": row.id, "name": row.name, "group_id": row.group_id} for row in rows], safe=False)
