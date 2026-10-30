from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import User


class SignupForm(UserCreationForm):
    email = forms.EmailField(max_length=254)

    class Meta:
        model = User
        fields = ("username", "email")

    def clean_username(self):
        value = self.cleaned_data["username"].strip()
        if "@" in value:
            raise forms.ValidationError("Use a username without @ so email login is unambiguous.")
        if User.objects.filter(username__iexact=value).exists():
            raise forms.ValidationError("This username is already taken.")
        return value

    def clean_email(self):
        value = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise forms.ValidationError("This email is already registered.")
        return value


class LoginForm(AuthenticationForm):
    username = forms.CharField(label="Email or username", max_length=254)
