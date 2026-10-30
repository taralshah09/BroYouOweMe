from django.urls import path
from django.views.generic import TemplateView

from apps.accounts.views import health

urlpatterns = [
    path("", TemplateView.as_view(template_name="home.html"), name="home"),
    path("health", health, name="health"),
]
