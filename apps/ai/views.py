from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from apps.accounts.http import endpoint, positive_id
from apps.expenses.models import Expense
from apps.expenses.views import expense_data
from apps.expenses.services import equal_shares
from apps.expenses.services.receipts import item_data
from apps.groups.models import Membership
from apps.groups.services import require_member
from .services import parse_receipt


@endpoint(["POST"])
def receipt_parse(request, group_id):
    require_member(group_id, request.user)
    return JsonResponse(parse_receipt(request.FILES.get("image")))


@endpoint(["GET"])
def receipt_review(request, group_id):
    group = require_member(group_id, request.user)
    initial = {"paid_by": request.user.id, "expense_date": timezone.localdate().isoformat(),
               "description": "Receipt", "split_mode": "itemised", "items": [], "source": "ocr"}
    if request.GET.get("expense"):
        expense = get_object_or_404(Expense, pk=positive_id(request.GET["expense"]), group=group, source="ocr")
        if expense.created_by_id != request.user.id:
            raise PermissionDenied("Only the expense creator can edit it.")
        initial.update(expense_data(expense), items=item_data(expense), participants=list(equal_shares(expense)))
    members = list(Membership.objects.filter(group=group, left_at__isnull=True).order_by("user_id").values("user_id", "user__username"))
    return render(request, "expenses/receipt.html", {"group": group, "initial": initial, "members": members})
