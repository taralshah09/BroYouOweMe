from django import forms
from django.utils import timezone

from apps.accounts.models import User
from django.db.models import Q
from .models import Category


class ExpenseForm(forms.Form):
    paid_by = forms.ModelChoiceField(queryset=User.objects.none())
    amount = forms.RegexField(regex=r"^[0-9]+(?:\.[0-9]{1,2})?$", label="Amount (INR)", max_length=22)
    description = forms.CharField(max_length=200)
    expense_date = forms.DateField(required=False, initial=timezone.localdate, widget=forms.DateInput(attrs={"type": "date"}))

    split_mode = forms.ChoiceField(required=False, choices=[("equal", "Equal"), ("unequal", "Exact amounts")])
    participants = forms.ModelMultipleChoiceField(queryset=User.objects.none(), required=False, help_text="Equal splits: choose participants, or leave blank for all members.")
    category = forms.ModelChoiceField(queryset=Category.objects.none(), required=False)
    tag = forms.CharField(max_length=40, required=False)

    def __init__(self, *args, group, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["paid_by"].queryset = User.objects.filter(memberships__group=group, memberships__left_at__isnull=True, is_active=True).order_by("id")
        self.fields["participants"].queryset = self.fields["paid_by"].queryset
        self.fields["category"].queryset = Category.objects.filter(Q(group=group) | Q(group__isnull=True)).order_by("name")
        for user in self.fields["paid_by"].queryset:
            self.fields[f"share_{user.id}"] = forms.RegexField(
                regex=r"^[0-9]+(?:\.[0-9]{1,2})?$", required=False, max_length=22,
                label=f"{user.username}'s exact share (INR)",
                help_text="Exact amounts only. Leave blank for nonparticipants.",
            )

    def clean_split_mode(self):
        return self.cleaned_data["split_mode"] or "equal"

    def service_values(self):
        data = self.cleaned_data
        values = {key: data[key] for key in ["amount", "description", "expense_date", "split_mode", "tag"]}
        values["paid_by"] = data["paid_by"].id
        values["category"] = data["category"].id if data["category"] else None
        if data["split_mode"] == "unequal":
            values["splits"] = [{"user_id": int(key[6:]), "amount": value} for key, value in data.items() if key.startswith("share_") and value]
        elif data["participants"]:
            values["participants"] = [user.id for user in data["participants"]]
        return values
