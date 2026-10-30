from django.http import JsonResponse
from django.shortcuts import redirect, render
from django import forms

from apps.accounts.http import endpoint, payload, positive_id, wants_html
from apps.accounts.models import User
from apps.groups.services import require_member
from .models import Settlement
from .services import balances_for, create_settlement, resolve_settlement, rupee_value


@endpoint(["GET"])
def balances(request, group_id=None):
    data = balances_for(request.user, group_id=group_id)
    if wants_html(request):
        return render(request, "settlements/balances.html", {"balances": data, "group_id": group_id})
    return JsonResponse(data)


class SettlementForm(forms.Form):
    receiver = forms.ModelChoiceField(queryset=User.objects.none())
    amount = forms.RegexField(regex=r"^[0-9]+(?:\.[0-9]{1,2})?$", label="Amount (INR)", max_length=22)
    note = forms.CharField(max_length=200, required=False)

    def __init__(self, *args, group, actor, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["receiver"].queryset = User.objects.filter(memberships__group=group, memberships__left_at__isnull=True).exclude(pk=actor.pk).order_by("id")


def settlement_data(row):
    return {"id": row.id, "group_id": row.group_id, "payer": row.payer_id,
            "receiver": row.receiver_id, "payer_username": row.payer.username,
            "receiver_username": row.receiver.username, "amount": rupee_value(row.amount_paise),
            "status": row.status, "note": row.note, "created_at": row.created_at.isoformat(),
            "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None}


@endpoint(["POST"])
def settlements(request):
    data = payload(request, ["group_id", "receiver", "amount", "note"])
    row = create_settlement(actor=request.user, group_id=positive_id(data.get("group_id")),
                            receiver=positive_id(data.get("receiver")), amount=data.get("amount"), note=data.get("note"))
    return redirect("group-settlements", group_id=row.group_id) if wants_html(request) else JsonResponse(settlement_data(row), status=201)


@endpoint(["GET"])
def group_settlements(request, group_id):
    group = require_member(group_id, request.user)
    rows = Settlement.objects.filter(group=group).select_related("payer", "receiver").order_by("-created_at", "-id")
    if wants_html(request):
        rows = list(rows)
        for row in rows:
            row.amount_display = rupee_value(row.amount_paise)
        return render(request, "settlements/list.html", {"group": group, "settlements": rows,
                      "form": SettlementForm(group=group, actor=request.user)})
    return JsonResponse([settlement_data(row) for row in rows], safe=False)


@endpoint(["POST"])
def settlement_action(request, settlement_id, action):
    payload(request, [])
    row = resolve_settlement(actor=request.user, settlement_id=settlement_id, action=action)
    return redirect("group-settlements", group_id=row.group_id) if wants_html(request) else JsonResponse(settlement_data(row))
