from django.http import JsonResponse
from django.shortcuts import render

from apps.accounts.http import endpoint, wants_html
from .services import balances_for


@endpoint(["GET"])
def balances(request, group_id=None):
    data = balances_for(request.user, group_id=group_id)
    if wants_html(request):
        return render(request, "settlements/balances.html", {"balances": data, "group_id": group_id})
    return JsonResponse(data)
