import csv

from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import render

from apps.accounts.http import endpoint, wants_html
from apps.groups.services import require_member
from .services import expense_export, settlement_nudges, spending_report


def private_response(response):
    response["Cache-Control"] = "no-store"
    response["Vary"] = "Accept, Cookie"
    return response


@endpoint(["GET"])
def insights(request, group_id):
    group = require_member(group_id, request.user)
    data = spending_report(request.user, group_id=group_id, month=request.GET.get("month"))
    response = render(request, "insights/summary.html", {"group": group, "report": data}) if wants_html(request) else JsonResponse(data)
    return private_response(response)


class CsvBuffer:
    def write(self, value):
        return value


@endpoint(["GET"])
def export_csv(request, group_id):
    rows = expense_export(request.user, group_id=group_id, month=request.GET.get("month"))
    writer = csv.writer(CsvBuffer())
    response = StreamingHttpResponse((writer.writerow(row) for row in rows), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="group-{group_id}-expenses.csv"'
    return private_response(response)


@endpoint(["GET"])
def nudges(request, group_id):
    group = require_member(group_id, request.user)
    data = settlement_nudges(request.user, group_id=group_id)
    response = render(request, "insights/nudges.html", {"group": group, "nudges": data}) if wants_html(request) else JsonResponse({"nudges": data})
    return private_response(response)
