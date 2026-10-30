from django.contrib.auth import login as session_login, logout as session_logout
from django.db import DatabaseError
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET

from .forms import LoginForm, SignupForm
from .http import endpoint, payload, wants_html

from .services import check_database, register_user


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


def user_data(user):
    return {"id": user.id, "username": user.username}


def complete_invite(request, user):
    from django.http import Http404
    from django.contrib import messages
    from apps.groups.services import join_invite

    token = request.session.pop("pending_invite", None)
    if token:
        try:
            return join_invite(token=token, actor=user).group_id
        except Http404:
            messages.info(request, "Your invite is no longer available. Ask the group admin for a new link.")
    return None


def home(request):
    return render(request, "home.html")


@endpoint(["GET", "POST"], public=True)
def signup(request):
    if request.method == "GET":
        return render(request, "accounts/auth.html", {"form": SignupForm(), "heading": "Create your account"})
    data = payload(request, ["username", "email", "password", "password1", "password2"])
    if "password" in data:
        data["password1"] = data.pop("password")
        data.setdefault("password2", data["password1"])
    form = SignupForm(data)
    if form.is_valid():
        user = register_user(form)
        session_login(request, user, backend="apps.accounts.backends.IdentityBackend")
        group_id = complete_invite(request, user)
        if wants_html(request):
            return redirect("group-detail", group_id=group_id) if group_id else redirect("groups")
        return JsonResponse({**user_data(user), **({"group_id": group_id} if group_id else {})}, status=201)
    if wants_html(request):
        return render(request, "accounts/auth.html", {"form": form, "heading": "Create your account"}, status=400)
    return JsonResponse({"errors": form.errors}, status=400)


@endpoint(["GET", "POST"], public=True)
def login(request):
    data = payload(request, ["username", "password"]) if request.method == "POST" else None
    form = LoginForm(request, data=data)
    if request.method == "POST" and form.is_valid():
        session_login(request, form.get_user())
        group_id = complete_invite(request, form.get_user())
        if wants_html(request):
            return redirect("group-detail", group_id=group_id) if group_id else redirect("groups")
        return JsonResponse({**user_data(form.get_user()), **({"group_id": group_id} if group_id else {})})
    if request.method == "GET" or wants_html(request):
        return render(request, "accounts/auth.html", {"form": form, "heading": "Welcome back"}, status=400 if data is not None else 200)
    return JsonResponse({"errors": form.errors}, status=400)


@endpoint(["POST"])
def logout(request):
    session_logout(request)
    return redirect("home") if wants_html(request) else JsonResponse({"status": "ok"})
