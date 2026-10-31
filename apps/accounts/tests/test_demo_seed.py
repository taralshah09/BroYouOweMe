import os
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.accounts.models import User
from apps.expenses.models import Expense
from apps.groups.models import Group
from apps.settlements.services import balance_mismatches, balances_for


@override_settings(SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=["testserver"])
class ReviewerSeedTests(TestCase):
    password = "Public-demo-test-2026!"

    def seed(self):
        with patch.dict(os.environ, {"DEMO_PASSWORD": self.password}):
            call_command("seed_demo", reviewer=True, stdout=StringIO())

    def test_reviewers_can_login_and_start_with_video_balances(self):
        self.seed()
        mohit = User.objects.get(username="reviewer_mohit")
        group = Group.objects.get(name="Goa Trip (Demo)")
        for username in ["reviewer_mohit", "reviewer_rahul", "reviewer_ankit"]:
            response = self.client.post("/login", {"username": username, "password": self.password},
                                        content_type="application/json")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(self.client.get(f"/groups/{group.pk}").status_code, 200)
        self.assertEqual(balances_for(mohit, group_id=group.pk), {
            "reviewer_rahul": {"owes": {"reviewer_mohit": 400}},
            "reviewer_ankit": {"owes": {"reviewer_mohit": 400}},
        })
        self.assertFalse(balance_mismatches())

    def test_repeat_seed_preserves_existing_payment(self):
        from apps.settlements.services import create_settlement, resolve_settlement

        self.seed()
        mohit = User.objects.get(username="reviewer_mohit")
        rahul = User.objects.get(username="reviewer_rahul")
        group = Group.objects.get(name="Goa Trip (Demo)")
        claim = create_settlement(actor=rahul, group_id=group.pk, receiver=mohit.pk, amount="400.00")
        resolve_settlement(actor=mohit, settlement_id=claim.pk, action="confirm")
        self.seed()
        self.assertEqual(User.objects.count(), 3)
        self.assertEqual(Group.objects.count(), 1)
        self.assertEqual(Expense.objects.count(), 1)
        self.assertEqual(balances_for(mohit, group_id=group.pk), {
            "reviewer_ankit": {"owes": {"reviewer_mohit": 400}},
        })
        self.assertFalse(balance_mismatches())

    def test_collision_rolls_back_new_accounts(self):
        User.objects.create_user(username="reviewer_rahul", email="someone@example.invalid", password="existing")
        with self.assertRaises(CommandError):
            self.seed()
        self.assertEqual(User.objects.count(), 1)
        self.assertFalse(Group.objects.exists())

    def test_missing_password_creates_nothing(self):
        with patch.dict(os.environ, {"DEMO_PASSWORD": ""}), self.assertRaises(CommandError):
            call_command("seed_demo", reviewer=True, stdout=StringIO())
        self.assertFalse(User.objects.exists())

    def test_changed_password_does_not_overwrite_accounts(self):
        self.seed()
        with patch.dict(os.environ, {"DEMO_PASSWORD": "Different-password-2026!"}), self.assertRaises(CommandError):
            call_command("seed_demo", reviewer=True, stdout=StringIO())
        self.assertTrue(User.objects.get(username="reviewer_mohit").check_password(self.password))

    def test_default_seed_keeps_dummy_accounts_unusable(self):
        call_command("seed_demo", stdout=StringIO())
        self.assertEqual(User.objects.count(), 5)
        self.assertTrue(all(not user.has_usable_password() for user in User.objects.all()))
