import importlib
import json
from datetime import timedelta
from unittest.mock import patch

from django.apps import apps
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.activity.models import Activity
from apps.expenses.models import Category, Expense, ExpenseSplit
from apps.expenses.services import create_expense, delete_expense, equal_shares, manage_category, snapshot, update_expense
from apps.groups.models import Membership
from apps.groups.services import add_member, create_group
from apps.settlements.models import Balance, Settlement
from apps.settlements.services import balance_mismatches, balances_for, create_settlement, resolve_settlement


@override_settings(SECURE_SSL_REDIRECT=False, PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"], STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class LedgerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a, cls.b, cls.c, cls.outsider = [User.objects.create_user(username=name, email=f"{name}@example.com") for name in ["alice", "bob", "chris", "outsider"]]
        cls.group = create_group(actor=cls.a, name="Trip")
        for user in [cls.b, cls.c]:
            add_member(actor=cls.a, group_id=cls.group.id, user_id=user.id)

    def expense(self, **changes):
        values = dict(actor=self.a, group_id=self.group.id, paid_by=self.a.id, amount="12.00", description="Dinner")
        values.update(changes)
        return create_expense(**values)

    def claim(self, **changes):
        values = dict(actor=self.b, group_id=self.group.id, receiver=self.a.id, amount="1.00")
        values.update(changes)
        return create_settlement(**values)

    def post(self, path, data=None):
        return self.client.post(path, json.dumps(data or {}), content_type="application/json")

    def test_explicit_equal_subset_and_payer_outside_participants(self):
        e = self.expense(amount="1.01", participants=[self.c.id, self.b.id])
        self.assertEqual(equal_shares(e), {self.b.id: 51, self.c.id: 50})
        self.assertEqual(balances_for(self.a, group_id=self.group.id), {"bob": {"owes": {"alice": "0.51"}}, "chris": {"owes": {"alice": "0.50"}}})
        add_member(actor=self.a, group_id=self.group.id, user_id=self.outsider.id)
        self.assertEqual(equal_shares(e), {self.b.id: 51, self.c.id: 50})
        self.assertEqual(balance_mismatches(), [])

    def test_unequal_splits_and_invalid_allocations_are_atomic(self):
        e = self.expense(splits=[{"user_id": self.a.id, "amount": 2}, {"user_id": self.b.id, "amount": 10}])
        self.assertEqual(e.split_mode, "unequal")
        self.assertEqual(balances_for(self.a, group_id=self.group.id), {"bob": {"owes": {"alice": 10}}})
        for changes in [
            {"participants": []}, {"participants": [self.b.id, self.b.id]}, {"participants": [True]},
            {"participants": [self.outsider.id]}, {"split_mode": "itemised"},
            {"splits": []}, {"splits": [{"user_id": self.b.id, "amount": 0}]},
            {"splits": [{"user_id": self.b.id, "amount": 12.0}]},
            {"splits": [{"user_id": self.b.id, "amount": 12}, {"user_id": self.b.id, "amount": 1}]},
            {"splits": [{"user_id": self.outsider.id, "amount": 12}]},
            {"splits": [{"user_id": self.b.id, "amount": 11}]},
            {"splits": [{"user_id": self.b.id, "amount": 12}], "participants": [self.c.id]},
            {"splits": [{"user_id": self.b.id, "amount": 12}], "split_mode": "equal"},
        ]:
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.expense(**changes)
        self.assertEqual(Expense.objects.count(), 1)
        self.assertEqual(balance_mismatches(), [])

    def test_edit_reverses_old_payer_and_allocation_and_logs_before_after(self):
        e = self.expense()
        before = snapshot(e)
        e = update_expense(actor=self.a, expense_id=e.id, paid_by=self.b.id, amount=9, splits=[{"user_id": self.c.id, "amount": 9}])
        self.assertEqual(equal_shares(e), {self.c.id: 900})
        self.assertEqual(balances_for(self.a, group_id=self.group.id), {"chris": {"owes": {"bob": 9}}})
        event = Activity.objects.get(action="expense.updated")
        self.assertEqual(event.before, before)
        self.assertEqual(event.after, snapshot(e))
        e = update_expense(actor=self.a, expense_id=e.id, tag=" trip ")
        self.assertEqual(equal_shares(e), {self.c.id: 900})
        self.assertEqual(e.tag, "trip")
        self.assertEqual(balance_mismatches(), [])

    def test_equal_edit_preserves_original_participants_after_later_join(self):
        e = self.expense()
        add_member(actor=self.a, group_id=self.group.id, user_id=self.outsider.id)
        e = update_expense(actor=self.a, expense_id=e.id, amount=15)
        self.assertEqual(equal_shares(e), {self.a.id: 500, self.b.id: 500, self.c.id: 500})
        self.assertEqual(balance_mismatches(), [])

    def test_creator_permissions_and_soft_delete(self):
        e = self.expense(actor=self.b)
        for actor in [self.a, self.outsider]:
            with self.assertRaises(PermissionDenied):
                update_expense(actor=actor, expense_id=e.id, description="No")
            with self.assertRaises(PermissionDenied):
                delete_expense(actor=actor, expense_id=e.id)
        delete_expense(actor=self.b, expense_id=e.id)
        self.assertFalse(Expense.objects.exists())
        self.assertIsNotNone(Expense.all_objects.get(pk=e.id).deleted_at)
        self.assertEqual(e.splits.count(), 3)
        self.assertEqual(balances_for(self.a, group_id=self.group.id), {})
        self.assertEqual(balance_mismatches(), [])

    def test_edit_and_delete_roll_back_when_audit_write_fails(self):
        e = self.expense()
        before = snapshot(e)
        for operation in [lambda: update_expense(actor=self.a, expense_id=e.id, amount=30), lambda: delete_expense(actor=self.a, expense_id=e.id)]:
            with patch("apps.expenses.services.record", side_effect=RuntimeError("audit unavailable")):
                with self.assertRaises(RuntimeError):
                    operation()
            e.refresh_from_db()
            self.assertEqual(snapshot(e), before)
            self.assertEqual(balance_mismatches(), [])

    def test_invalid_edit_restores_ledger(self):
        e = self.expense()
        with self.assertRaises(ValidationError):
            update_expense(actor=self.a, expense_id=e.id, amount=0)
        e.refresh_from_db()
        self.assertEqual(e.amount_paise, 1200)
        self.assertEqual(balance_mismatches(), [])

    def test_partial_settlement_confirmation_changes_only_on_confirmation(self):
        self.expense()
        row = self.claim(amount="1.01")
        self.assertEqual(balances_for(self.a, group_id=self.group.id)["bob"]["owes"]["alice"], 4)
        for actor in [self.b, self.c, self.outsider]:
            with self.assertRaises(PermissionDenied):
                resolve_settlement(actor=actor, settlement_id=row.id, action="confirm")
        row = resolve_settlement(actor=self.a, settlement_id=row.id, action="confirm")
        self.assertEqual(row.status, "confirmed")
        self.assertIsNotNone(row.resolved_at)
        self.assertEqual(balances_for(self.a, group_id=self.group.id)["bob"]["owes"]["alice"], "2.99")
        with self.assertRaises(ValidationError):
            resolve_settlement(actor=self.a, settlement_id=row.id, action="confirm")
        self.assertEqual(balance_mismatches(), [])

    def test_pending_reservations_and_confirmation_rechecks_changed_debt(self):
        e = self.expense()
        first, second = self.claim(amount=3), self.claim(amount=1)
        with self.assertRaises(ValidationError):
            self.claim(amount="0.01")
        update_expense(actor=self.a, expense_id=e.id, amount=9)
        with self.assertRaises(ValidationError):
            resolve_settlement(actor=self.a, settlement_id=first.id, action="confirm")
        resolve_settlement(actor=self.b, settlement_id=second.id, action="cancel")
        resolve_settlement(actor=self.a, settlement_id=first.id, action="confirm")
        self.assertNotIn("bob", balances_for(self.a, group_id=self.group.id))
        self.assertEqual(balance_mismatches(), [])

    def test_reject_cancel_and_invalid_claims(self):
        self.expense()
        for changes in [{"amount": 0}, {"amount": -1}, {"amount": "4.01"}, {"receiver": self.b.id}, {"receiver": self.outsider.id}, {"actor": self.c, "receiver": self.b.id}]:
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.claim(**changes)
        row = self.claim()
        with self.assertRaises(PermissionDenied):
            resolve_settlement(actor=self.a, settlement_id=row.id, action="cancel")
        resolve_settlement(actor=self.a, settlement_id=row.id, action="reject")
        row = self.claim()
        resolve_settlement(actor=self.b, settlement_id=row.id, action="cancel")
        self.assertEqual(balances_for(self.a, group_id=self.group.id)["bob"]["owes"]["alice"], 4)
        self.assertEqual(balance_mismatches(), [])

    def test_delete_after_confirmed_payment_can_reverse_debt(self):
        e = self.expense()
        row = self.claim(amount=4)
        resolve_settlement(actor=self.a, settlement_id=row.id, action="confirm")
        delete_expense(actor=self.a, expense_id=e.id)
        self.assertEqual(balances_for(self.a, group_id=self.group.id), {"alice": {"owes": {"bob": 4}}})
        self.assertEqual(balance_mismatches(), [])

    def test_confirmation_rolls_back_when_audit_fails(self):
        self.expense()
        row = self.claim()
        with patch("apps.activity.services.record", side_effect=RuntimeError("failure")):
            with self.assertRaises(RuntimeError):
                resolve_settlement(actor=self.a, settlement_id=row.id, action="confirm")
        row.refresh_from_db()
        self.assertEqual(row.status, "pending")
        self.assertIsNone(row.resolved_at)
        self.assertEqual(balance_mismatches(), [])

    def test_categories_scope_defaults_and_protected_use(self):
        default = Category.objects.get(name="Food", group__isnull=True)
        with self.assertRaises(ValidationError):
            manage_category(actor=self.a, group_id=self.group.id, name=" fOoD ")
        category = manage_category(actor=self.b, group_id=self.group.id, name="Booze")
        with self.assertRaises(ValidationError):
            manage_category(actor=self.c, group_id=self.group.id, name="booze")
        other_group = create_group(actor=self.outsider, name="Private")
        private = manage_category(actor=self.outsider, group_id=other_group.id, name="Private")
        with self.assertRaises(ValidationError):
            self.expense(category=private.id)
        with self.assertRaises(PermissionDenied):
            manage_category(actor=self.outsider, group_id=self.group.id, name="No")
        for delete in [False, True]:
            with self.assertRaises(ValidationError):
                manage_category(actor=self.a, group_id=self.group.id, category_id=default.id, name="No", delete=delete)
        e = self.expense(category=category.id, tag="party")
        manage_category(actor=self.c, group_id=self.group.id, category_id=category.id, name="Drinks")
        delete_expense(actor=self.a, expense_id=e.id)
        with self.assertRaises(ValidationError):
            manage_category(actor=self.a, group_id=self.group.id, category_id=category.id, delete=True)
        unused = manage_category(actor=self.a, group_id=self.group.id, name="Unused")
        manage_category(actor=self.b, group_id=self.group.id, category_id=unused.id, delete=True)
        self.assertFalse(Category.objects.filter(pk=unused.id).exists())

    def test_integrity_detects_missing_payer_share_even_without_balance_drift(self):
        e = self.expense()
        ExpenseSplit.objects.filter(expense=e, user=self.a).delete()
        self.assertEqual(balance_mismatches()[0]["expense_id"], e.id)

    def test_database_constraints(self):
        e = self.expense()
        for operation in [
            lambda: ExpenseSplit.objects.create(expense=e, user=self.a, share_paise=1),
            lambda: ExpenseSplit.objects.create(expense=e, user=self.outsider, share_paise=0),
            lambda: Settlement.objects.create(group=self.group, payer=self.a, receiver=self.a, amount_paise=1),
            lambda: Settlement.objects.create(group=self.group, payer=self.a, receiver=self.b, amount_paise=0),
            lambda: Settlement.objects.create(group=self.group, payer=self.a, receiver=self.b, amount_paise=1, status="unknown"),
        ]:
            with self.assertRaises(IntegrityError), transaction.atomic():
                operation()

    def test_phase1_materialization_preserves_historical_shares_and_balances(self):
        e = self.expense(amount="1.01", expense_date="2020-01-01")
        before = equal_shares(e)
        add_member(actor=self.a, group_id=self.group.id, user_id=self.outsider.id)
        Membership.objects.filter(group=self.group, user=self.outsider).update(joined_at=e.created_at + timedelta(seconds=1))
        e.splits.all().delete()
        Activity.objects.all().delete()
        Category.objects.all().delete()
        migration = importlib.import_module("apps.expenses.migrations.0003_materialize_ledger")
        with connection.schema_editor() as editor:
            migration.materialize(apps, editor)
        self.assertEqual(equal_shares(e), before)
        self.assertEqual(Activity.objects.get().created_at, e.created_at)
        self.assertEqual(Category.objects.filter(group__isnull=True).count(), 7)
        self.assertEqual(balance_mismatches(), [])

    def test_api_and_html_full_ledger_workflow(self):
        self.client.force_login(self.a)
        response = self.post("/expenses", {"group_id": self.group.id, "paid_by": self.a.id, "amount": "3.01", "description": "Tea", "participants": [self.b.id]})
        self.assertEqual(response.status_code, 201, response.content)
        pk = response.json()["id"]
        response = self.client.patch(f"/expenses/{pk}", json.dumps({"amount": "4.01", "tag": "cafe"}), content_type="application/json")
        self.assertEqual(response.status_code, 200, response.content)
        self.client.force_login(self.b)
        row = self.post("/settlements", {"group_id": self.group.id, "receiver": self.a.id, "amount": "1.01"})
        self.assertEqual(row.status_code, 201, row.content)
        self.assertEqual(self.post(f"/settlements/{row.json()['id']}/confirm").status_code, 403)
        self.client.force_login(self.a)
        self.assertEqual(self.post(f"/settlements/{row.json()['id']}/confirm").status_code, 200)
        category = self.post(f"/groups/{self.group.id}/categories", {"name": "Cafe"})
        self.assertEqual(category.status_code, 201)
        self.assertEqual(self.client.patch(f"/groups/{self.group.id}/categories/{category.json()['id']}", json.dumps({"name": "Coffee"}), content_type="application/json").status_code, 200)
        for path in [f"/expenses/{pk}", f"/groups/{self.group.id}", f"/groups/{self.group.id}/categories", f"/groups/{self.group.id}/settlements", f"/groups/{self.group.id}/activity"]:
            self.assertEqual(self.client.get(path, HTTP_ACCEPT="text/html").status_code, 200, path)
        feed = self.client.get(f"/groups/{self.group.id}/activity").json()
        self.assertIn("settlement.confirmed", [event["action"] for event in feed["results"]])
        for index in range(26):
            update_expense(actor=self.a, expense_id=pk, description=f"Tea {index}")
        page = self.client.get(f"/groups/{self.group.id}/activity?page=2").json()
        self.assertEqual(page["page"], 2)
        self.assertTrue(page["results"])
        self.assertEqual(self.client.delete(f"/expenses/{pk}").status_code, 200)
        self.assertEqual(self.client.get(f"/expenses/{pk}").status_code, 404)
        self.assertEqual(balance_mismatches(), [])

    def test_form_unequal_edit_and_deletion(self):
        self.client.force_login(self.a)
        form = {"group_id": self.group.id, "paid_by": self.a.id, "amount": "5.01", "description": "Lunch", "split_mode": "unequal", f"share_{self.b.id}": "5.01"}
        response = self.client.post("/expenses", form, HTTP_ACCEPT="text/html")
        self.assertEqual(response.status_code, 302, response.content)
        e = Expense.objects.get()
        form.pop("group_id")
        form["amount"], form[f"share_{self.b.id}"] = "6.01", "6.01"
        self.assertEqual(self.client.post(f"/expenses/{e.id}", form, HTTP_ACCEPT="text/html").status_code, 302)
        self.assertEqual(equal_shares(e), {self.b.id: 601})
        self.assertEqual(self.client.post(f"/expenses/{e.id}/delete", HTTP_ACCEPT="text/html").status_code, 302)
        self.assertEqual(balance_mismatches(), [])

    def test_malformed_expense_fields_return_validation_errors(self):
        self.client.force_login(self.a)
        for extra in [{}, {"paid_by": self.a.id}, {"split_mode": []}, {"split_mode": {}}, {"participants": [[1]]}]:
            values = {"group_id": self.group.id}
            if "split_mode" in extra or "participants" in extra:
                values.update(paid_by=self.a.id, amount=12, description="Dinner")
            values.update(extra)
            with self.subTest(values=values):
                self.assertEqual(self.post("/expenses", values).status_code, 400)
        self.assertFalse(Expense.objects.exists())

    def test_filters_access_and_csrf_on_new_routes(self):
        self.expense(expense_date="2020-01-01", tag="travel")
        self.client.force_login(self.a)
        base = f"/groups/{self.group.id}"
        self.assertEqual(len(self.client.get(base + "/expenses?search=travel&date_to=2020-01-01").json()), 1)
        self.assertEqual(self.client.get(base + "/expenses?date_from=2021-01-01").json(), [])
        self.assertEqual(self.client.get(base + "/expenses?date_from=bad").status_code, 400)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.a)
        self.assertEqual(client.patch("/expenses/1", "{}", content_type="application/json").status_code, 403)
        self.assertEqual(client.delete(base + "/categories/1").status_code, 403)
        self.assertEqual(client.post("/settlements/1/confirm").status_code, 403)
        self.client.force_login(self.outsider)
        for suffix in ["/activity", "/categories", "/settlements"]:
            self.assertEqual(self.client.get(base + suffix).status_code, 403)
