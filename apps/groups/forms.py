from django import forms

from .models import Group


class GroupForm(forms.ModelForm):
    class Meta:
        model = Group
        fields = ["name"]


class MemberForm(forms.Form):
    username = forms.CharField(label="Friend's exact username", max_length=32)
