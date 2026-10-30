from django import forms

from apps.accounts.models import User
from .models import Group


class GroupForm(forms.ModelForm):
    class Meta:
        model = Group
        fields = ["name"]


class MemberForm(forms.Form):
    user_id = forms.ModelChoiceField(label="User", queryset=User.objects.filter(is_active=True).order_by("username"))
