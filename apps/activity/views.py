from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import render

from apps.accounts.http import endpoint, wants_html
from apps.groups.services import require_member
from apps.accounts.models import User
from apps.settlements.services import rupee_value
from .models import Activity


@endpoint(["GET"])
def activity(request, group_id):
    group = require_member(group_id, request.user)
    page = Paginator(Activity.objects.filter(group=group).select_related("actor").order_by("-created_at", "-id"), 25).get_page(request.GET.get("page", 1))
    if wants_html(request):
        names = dict(User.objects.filter(memberships__group=group).values_list("id", "username"))
        for event in page:
            event.label = event.action.replace(".", " ").replace("claimed", "payment claimed")
            event.details = []
            for label, state in [("Before", event.before), ("After", event.after)]:
                if not state:
                    continue
                rows = []
                for key, title in [("description", "Description"), ("name", "Category"), ("expense_date", "Date"), ("tag", "Tag"), ("status", "Status"), ("note", "Note")]:
                    if state.get(key):
                        rows.append((title, state[key]))
                if "amount_paise" in state:
                    rows.append(("Amount", f"INR {rupee_value(state['amount_paise'])}"))
                for key, title in [("paid_by", "Paid by"), ("payer", "From"), ("receiver", "To")]:
                    if key in state:
                        rows.append((title, names.get(state[key], "Unknown user")))
                for split in state.get("splits", []):
                    rows.append((names.get(split["user_id"], "Unknown user") + "'s share", f"INR {rupee_value(split['share_paise'])}"))
                if state.get("deleted_at"):
                    rows.append(("Status", "Deleted"))
                event.details.append((label, rows))
        return render(request, "activity/list.html", {"group": group, "page": page})
    return JsonResponse({"page": page.number, "pages": page.paginator.num_pages,
                         "results": [{"id": row.id, "actor": row.actor.username, "action": row.action,
                                      "entity_type": row.entity_type, "entity_id": row.entity_id,
                                      "before": row.before, "after": row.after,
                                      "created_at": row.created_at.isoformat()} for row in page]})
