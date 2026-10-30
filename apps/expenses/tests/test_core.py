from io import StringIO
from unittest.mock import patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.http import Http404
from django.test import TestCase, TransactionTestCase, override_settings

from apps.accounts.models import User
from apps.expenses.models import Expense
from apps.expenses.services import create_expense, equal_shares
from apps.groups.models import Group, Membership
from apps.groups.services import add_member, create_group
from apps.settlements.models import Balance
from apps.settlements.services import balance_mismatches, balances_for


class ExpenseTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.mohit = User.objects.create_user(username="Mohit", email="mohit@example.com", password="test-password")
        cls.rahul = User.objects.create_user(username="Rahul", email="rahul@example.com", password="test-password")
        cls.ankit = User.objects.create_user(username="Ankit", email="ankit@example.com", password="test-password")
        cls.outsider = User.objects.create_user(username="Outsider", email="outsider@example.com", password="test-password")
        cls.group = create_group(actor=cls.mohit, name="Goa Trip")
        for user in [cls.rahul, cls.ankit]:
            add_member(group_id=cls.group.id, actor=cls.mohit, user_id=user.id)

    def expense(self, **kwargs):
        data = dict(actor=self.mohit, group_id=self.group.id, paid_by=self.mohit.id, amount=1200, description="Dinner")
        data.update(kwargs)
        return create_expense(**data)

    def test_exact_assignment_scenario(self):
        expense = self.expense()
        self.assertEqual(expense.amount_paise, 120000)
        self.assertEqual(balances_for(self.mohit, group_id=self.group.id), {
            "Rahul": {"owes": {"Mohit": 400}}, "Ankit": {"owes": {"Mohit": 400}},
        })
        self.assertEqual(Balance.objects.count(), 2)
        self.assertEqual(balance_mismatches(), [])

    def test_remainder_follows_ascending_ids_and_sums_exactly(self):
        expense = self.expense(amount="100.00")
        self.assertEqual(list(equal_shares(expense).values()), [3334, 3333, 3333])
        self.assertEqual(sum(equal_shares(expense).values()), 10000)
        self.assertEqual(balances_for(self.mohit, group_id=self.group.id)["Rahul"]["owes"]["Mohit"], "33.33")
        self.assertEqual(balance_mismatches(), [])

    def test_opposite_debts_net_and_can_reverse_direction(self):
        self.expense()
        self.expense(paid_by=self.rahul.id, amount=1500)
        balances = balances_for(self.mohit, group_id=self.group.id)
        self.assertEqual(balances["Mohit"]["owes"]["Rahul"], 100)
        self.assertEqual(balance_mismatches(), [])

    def test_zero_pairs_do_not_appear(self):
        self.expense()
        self.expense(paid_by=self.rahul.id)
        self.expense(paid_by=self.ankit.id)
        self.assertEqual(balances_for(self.mohit, group_id=self.group.id), {})
        self.assertEqual(balance_mismatches(), [])

    def test_later_member_does_not_change_old_expense(self):
        expense = self.expense()
        shares = equal_shares(expense)
        add_member(group_id=self.group.id, actor=self.mohit, user_id=self.outsider.id)
        self.assertEqual(equal_shares(expense), shares)
        self.expense(amount=400)
        self.assertEqual(balance_mismatches(), [])
        self.assertEqual(balances_for(self.mohit, group_id=self.group.id)["Outsider"]["owes"]["Mohit"], 100)

    def test_invalid_amounts_leave_no_partial_writes(self):
        for amount in [0, -1, "0.01", "0.001", 1.25, True, "NaN", "1e2", str(2**63)]:
            with self.subTest(amount=amount), self.assertRaises(ValidationError):
                self.expense(amount=amount)
        self.assertFalse(Expense.objects.exists())
        self.assertFalse(Balance.objects.exists())

    def test_balance_overflow_is_validation_error_and_rolls_back(self):
        from apps.expenses.services.money import MAX_PAISE
        Balance.objects.create(group=self.group, user_a=self.mohit, user_b=self.rahul, net_paise=MAX_PAISE)
        with self.assertRaises(ValidationError):
            self.expense()
        self.assertFalse(Expense.objects.exists())
        self.assertEqual(Balance.objects.get(group=self.group).net_paise, MAX_PAISE)

    def test_invalid_group_actor_and_payer(self):
        with self.assertRaises(Http404):
            self.expense(group_id=999999)
        with self.assertRaises(PermissionDenied):
            self.expense(actor=self.outsider)
        with self.assertRaises(ValidationError):
            self.expense(paid_by=self.outsider.id)
        with self.assertRaises(ValidationError):
            self.expense(description=" ")
        with self.assertRaises(ValidationError):
            self.expense(expense_date="2026-02-30")
        with self.assertRaises(ValidationError):
            self.expense(expense_date=False)
        self.assertFalse(Expense.objects.exists())

    def test_failure_midway_rolls_back_expense_and_balances(self):
        from apps.settlements.services import apply_debt
        def fail_second(group_id, debtor_id, creditor_id, amount):
            if debtor_id == self.ankit.id:
                raise RuntimeError("failure")
            apply_debt(group_id, debtor_id, creditor_id, amount)

        with patch("apps.settlements.services.apply_debt", side_effect=fail_second):
            with self.assertRaises(RuntimeError):
                self.expense()
        self.assertFalse(Expense.objects.exists())
        self.assertFalse(Balance.objects.exists())

    def test_backdated_expense_uses_members_at_creation(self):
        expense = self.expense(expense_date="2020-01-01")
        self.assertEqual(expense.expense_date.isoformat(), "2020-01-01")
        self.assertEqual(len(equal_shares(expense)), 3)
        self.assertEqual(balance_mismatches(), [])

    def test_single_member_never_owes_self(self):
        group = create_group(actor=self.mohit, name="Solo")
        self.expense(group_id=group.id, amount="0.01")
        self.assertFalse(Balance.objects.filter(group=group).exists())
        self.assertEqual(balance_mismatches(), [])

    def test_member_permissions_and_duplicate_join(self):
        with self.assertRaises(PermissionDenied):
            add_member(group_id=self.group.id, actor=self.rahul, user_id=self.outsider.id)
        with self.assertRaises(ValidationError):
            add_member(group_id=self.group.id, actor=self.mohit, user_id=self.rahul.id)
        with self.assertRaises(ValidationError):
            add_member(group_id=self.group.id, actor=self.mohit, user_id=999999)
        self.assertEqual(Membership.objects.filter(group=self.group, role="admin").count(), 1)

    def test_overall_balances_include_only_callers_pairs_and_net_across_groups(self):
        self.expense()
        second = create_group(actor=self.rahul, name="Second")
        add_member(group_id=second.id, actor=self.rahul, user_id=self.mohit.id)
        self.expense(group_id=second.id, actor=self.rahul, paid_by=self.rahul.id, amount=1000)
        self.assertEqual(balances_for(self.rahul), {"Mohit": {"owes": {"Rahul": 100}}})

    def test_soft_deleted_group_is_inaccessible(self):
        from django.utils import timezone
        self.group.deleted_at = timezone.now()
        self.group.save()
        with self.assertRaises(Http404):
            self.expense()

    def test_integrity_command_detects_drift(self):
        self.expense()
        call_command("check_balances", stdout=StringIO())
        Balance.objects.filter(group=self.group, user_b=self.rahul).update(net_paise=1)
        self.assertEqual(len(balance_mismatches()), 1)
        with self.assertRaises(CommandError):
            call_command("check_balances", stdout=StringIO())

    def test_database_constraints(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Balance.objects.create(group=self.group, user_a=self.mohit, user_b=self.mohit, net_paise=1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Expense.objects.create(group=self.group, created_by=self.mohit, paid_by=self.mohit, amount_paise=0, description="Invalid")


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ConcurrentExpenseTests(TransactionTestCase):
    def test_concurrent_expenses_serialize_without_losing_balances(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from django.db import close_old_connections, connections

        payer = User.objects.create_user(username="payer", email="payer@example.com")
        member = User.objects.create_user(username="member", email="member@example.com")
        group = create_group(actor=payer, name="Concurrent")
        add_member(group_id=group.id, actor=payer, user_id=member.id)
        ready = Barrier(2)

        def save_expense(index):
            close_old_connections()
            try:
                actor = User.objects.get(pk=payer.id)
                ready.wait(timeout=10)
                return create_expense(actor=actor, group_id=group.id, paid_by=payer.id, amount=100, description=f"Expense {index}").id
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            ids = list(pool.map(save_expense, range(2)))
        self.assertEqual(len(set(ids)), 2)
        self.assertEqual(Balance.objects.get(group=group).net_paise, 10000)
        self.assertEqual(balance_mismatches(), [])
