from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.http import endpoint, payload, positive_id
from apps.expenses.models import Expense
from apps.expenses.views import expense_data
from apps.expenses.forms import ExpenseForm
from apps.expenses.services import create_expense, equal_shares
from apps.expenses.services.receipts import item_data
from apps.groups.models import Membership
from apps.groups.services import require_member
from django.views.decorators.cache import never_cache

from .services import VoiceUnavailable, parse_receipt, parse_transcript, transcribe


def voice_members(group):
    return list(Membership.objects.filter(group=group, left_at__isnull=True).order_by("user_id").values("user_id", "user__username"))


@never_cache
@endpoint(["GET"])
def voice_review(request, group_id):
    group = require_member(group_id, request.user)
    return render(request, "expenses/voice.html", {"group": group, "form": ExpenseForm(group=group)})


@never_cache
@endpoint(["POST"])
def voice_parse(request, group_id):
    group = require_member(group_id, request.user)
    try:
        text = transcribe(request.FILES.get("audio")) if request.FILES else payload(request, ["transcript"]).get("transcript")
        try:
            draft = parse_transcript(text, voice_members(group), request.user.id)
        except VoiceUnavailable as error:
            return JsonResponse({"error": str(error), "transcript": text}, status=503)
        return JsonResponse({"transcript": text, "draft": draft})
    except VoiceUnavailable as error:
        return JsonResponse({"error": str(error)}, status=503)


@never_cache
@endpoint(["POST"])
def voice_approve(request, group_id):
    group = require_member(group_id, request.user)
    form = ExpenseForm(request.POST, group=group)
    payload(request, list(form.fields) + ["approved"])
    if request.POST.get("approved") != "yes":
        raise ValidationError("Review and explicitly approve the expense before saving.")
    if not form.is_valid():
        return render(request, "expenses/voice.html", {"group": group, "form": form}, status=400)
    values = form.service_values()
    try:
        expense = create_expense(actor=request.user, group_id=group.id, source="voice", **values)
    except ValidationError as error:
        form.add_error(None, ValidationError(error.messages))
        return render(request, "expenses/voice.html", {"group": group, "form": form}, status=400)
    return redirect("expense-detail", expense_id=expense.id)


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
