from django.db import DatabaseError
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .services import check_database


@require_GET
def health(request):
    try:
        healthy = check_database()
    except DatabaseError:
        healthy = False
    response = JsonResponse(
        {"status": "ok" if healthy else "unavailable"},
        status=200 if healthy else 503,
    )
    response["Cache-Control"] = "no-store"
    return response
