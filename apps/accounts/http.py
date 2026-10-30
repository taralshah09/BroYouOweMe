import json
from decimal import Decimal
from functools import wraps

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render


def wants_html(request):
    return "text/html" in request.headers.get("Accept", "")


def decimal_number(value):
    if "e" in value.lower():
        raise ValueError("Exponent notation is not supported.")
    return Decimal(value)


def payload(request, allowed):
    if request.content_type == "application/json":
        try:
            data = json.loads(request.body, parse_float=decimal_number, parse_constant=lambda value: None)
        except (ValueError, UnicodeDecodeError):
            raise ValidationError("Provide valid JSON.") from None
        if not isinstance(data, dict):
            raise ValidationError("Provide a JSON object.")
    else:
        data = request.POST.dict()
        data.pop("csrfmiddlewaretoken", None)
    unexpected = data.keys() - set(allowed)
    if unexpected:
        raise ValidationError("Unsupported fields: " + ", ".join(sorted(unexpected)))
    return data


def positive_id(value):
    if isinstance(value, bool) or not isinstance(value, (str, int)) or not str(value).isascii() or not str(value).isdigit() or not 0 < int(value) <= 2**63 - 1:
        raise ValidationError("IDs must be positive integers.")
    return int(value)


def endpoint(methods, *, public=False):
    def decorate(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.method not in methods:
                response = JsonResponse({"error": "Method not allowed."}, status=405)
                response["Allow"] = ", ".join(methods)
                return response
            if not public and not request.user.is_authenticated:
                if wants_html(request):
                    return redirect("/login")
                return JsonResponse({"error": "Login required."}, status=401)
            try:
                for name, value in kwargs.items():
                    if name.endswith("_id"):
                        positive_id(value)
                return view(request, *args, **kwargs)
            except ValidationError as error:
                errors = error.message_dict if hasattr(error, "message_dict") else error.messages
                if wants_html(request):
                    return render(request, "error.html", {"errors": error.messages}, status=400)
                return JsonResponse({"errors": errors}, status=400)
            except PermissionDenied as error:
                return JsonResponse({"error": str(error)}, status=403)
            except Http404:
                return JsonResponse({"error": "Not found."}, status=404)
        return wrapped
    return decorate
