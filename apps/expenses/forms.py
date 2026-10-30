from django import forms
from django.utils import timezone

from apps.accounts.models import User


class ExpenseForm(forms.Form):
    paid_by = forms.ModelChoiceField(queryset=User.objects.none())
    amount = forms.RegexField(regex=r"^[0-9]+(?:\.[0-9]{1,2})?$", label="Amount (INR)", max_length=22)
    description = forms.CharField(max_length=200)
    expense_date = forms.DateField(initial=timezone.localdate, widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, group, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["paid_by"].queryset = User.objects.filter(memberships__group=group, memberships__left_at__isnull=True, is_active=True).order_by("id")
