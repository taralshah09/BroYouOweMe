import csv
import io

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings

from apps.accounts.models import User
from apps.expenses.models import Category
from apps.expenses.services import create_expense, delete_expense, update_expense
from apps.groups.models import Membership
from apps.groups.services import add_member, create_group
from apps.insights.services import csv_text, expense_export, report_month, settlement_nudges, spending_report
from apps.settlements.services import balance_mismatches, create_settlement, resolve_settlement


@override_settings(SECURE_SSL_REDIRECT=False, STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class InsightsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a, cls.b, cls.outsider = [User.objects.create_user(username=name, email=f"{name}@example.invalid") for name in ["alice", "bob", "outsider"]]
        cls.group = create_group(actor=cls.a, name="Trip")
        add_member(actor=cls.a, group_id=cls.group.id, user_id=cls.b.id)
        cls.food = Category.objects.get(name="Food", group__isnull=True)

    def expense(self, **changes):
        values = dict(actor=self.a, group_id=self.group.id, paid_by=self.a.id, amount="10.01", description="Dinner", expense_date="2026-01-10", category=self.food.id)
        values.update(changes)
        return create_expense(**values)

    def test_report_dates_categories_and_personal_shares(self):
        self.expense()
        self.expense(amount="2.01", paid_by=self.b.id, category=None)
        self.expense(expense_date="2025-12-31", amount="5.00")
        self.expense(expense_date="2026-02-01", amount="100.00")
        deleted = self.expense(amount="60.00")
        delete_expense(actor=self.a, expense_id=deleted.id)
        report = spending_report(self.a, group_id=self.group.id, month="2026-01")
        self.assertEqual(report["summary"], {"total": "12.02", "expense_count": 2, "your_paid": "10.01", "your_share": "6.02"})
        self.assertEqual(report["categories"], [{"id": self.food.id, "name": "Food", "amount": "10.01"}, {"id": None, "name": "Uncategorised", "amount": "2.01"}])
        self.assertEqual(len(report["months"]), 12)
        self.assertEqual(report["months"][0], {"month": "2025-02", "amount": "0.00"})
        self.assertEqual(report["months"][-2:], [{"month": "2025-12", "amount": "5.00"}, {"month": "2026-01", "amount": "12.02"}])
        self.assertEqual(balance_mismatches(), [])

    def test_edit_moves_month_category_and_settlement_does_not_reduce_spending(self):
        expense = self.expense(amount="10.00")
        claim = create_settlement(actor=self.b, group_id=self.group.id, receiver=self.a.id, amount="5.00")
        resolve_settlement(actor=self.a, settlement_id=claim.id, action="confirm")
        self.assertEqual(spending_report(self.a, group_id=self.group.id, month="2026-01")["summary"]["total"], "10.00")
        update_expense(actor=self.a, expense_id=expense.id, expense_date="2026-02-01", category=None)
        report = spending_report(self.a, group_id=self.group.id, month="2026-01")
        self.assertEqual(report["summary"]["total"], "0.00")
        self.assertEqual(report["categories"], [])
        self.assertEqual(balance_mismatches(), [])

    def test_month_validation_and_empty_report(self):
        for month in ["", "2026-13", "2026-00", "2026-1", "0000-01", "0001-01", "9999-12", "2026-01-01", "x", "２０２６-01"]:
            with self.subTest(month=month), self.assertRaises(ValidationError):
                report_month(month)
        for month in ["0002-01", "9998-12", "2024-02"]:
            report = spending_report(self.a, group_id=self.group.id, month=month)
            self.assertEqual(report["summary"]["total"], "0.00")
            self.assertEqual(report["month"], month)
        self.assertEqual(report_month().day, 1)

    def test_export_quoting_formula_protection_splits_and_month_filter(self):
        expense = self.expense(description='=SUM(1,2)\n"Dinner"', tag="@formula")
        self.expense(expense_date="2026-02-01")
        deleted = self.expense()
        delete_expense(actor=self.a, expense_id=deleted.id)
        self.client.force_login(self.a)
        response = self.client.get(f"/groups/{self.group.id}/expenses/export.csv?month=2026-01")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertIn("attachment", response["Content-Disposition"])
        rows = list(csv.DictReader(io.StringIO(b"".join(response.streaming_content).decode())))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["expense_id"], str(expense.id))
        self.assertEqual(rows[0]["description"], '\'=SUM(1,2)\n"Dinner"')
        self.assertEqual(rows[0]["tag"], "'@formula")
        self.assertEqual(rows[0]["amount_inr"], "10.01")
        self.assertEqual(rows[0]["your_share_inr"], "5.01")
        self.assertEqual(rows[0]["splits_inr"], "alice: 5.01; bob: 5.00")
        self.assertEqual(len(list(expense_export(self.a, group_id=self.group.id))), 3)
        for value in ["=X", " +X", "-X", "@X", "\tX", "\rX", "\nX"]:
            self.assertTrue(csv_text(value).startswith("'"))

    def test_nudges_actual_pairwise_debts_both_directions_and_pending(self):
        self.expense(amount="10.00")
        self.assertEqual(settlement_nudges(self.b, group_id=self.group.id), [])
        pending = create_settlement(actor=self.b, group_id=self.group.id, receiver=self.a.id, amount="2.00")
        reminder = settlement_nudges(self.a, group_id=self.group.id)[0]
        self.assertEqual((reminder["username"], reminder["amount"], reminder["pending_amount"]), ("bob", "3.00", "2.00"))
        self.assertIn("excludes INR 2.00", reminder["text"])
        resolve_settlement(actor=self.a, settlement_id=pending.id, action="reject")
        pending = create_settlement(actor=self.b, group_id=self.group.id, receiver=self.a.id, amount="5.00")
        self.assertEqual(settlement_nudges(self.a, group_id=self.group.id), [])
        resolve_settlement(actor=self.a, settlement_id=pending.id, action="confirm")
        self.expense(paid_by=self.b.id, amount="4.02")
        self.assertEqual(settlement_nudges(self.b, group_id=self.group.id)[0]["amount"], "2.01")
        self.assertEqual(balance_mismatches(), [])

    def test_endpoints_auth_membership_methods_invalid_months_and_html(self):
        paths = [f"/groups/{self.group.id}/{suffix}" for suffix in ["insights", "expenses/export.csv", "nudges"]]
        for path in paths:
            self.assertEqual(self.client.get(path).status_code, 401)
        self.client.force_login(self.outsider)
        for path in paths:
            self.assertEqual(self.client.get(path).status_code, 403)
        self.client.force_login(self.a)
        for path in paths:
            self.assertEqual(self.client.post(path).status_code, 405)
        for path in paths[:2]:
            self.assertEqual(self.client.get(path, {"month": "invalid"}).status_code, 400)
        for path, text in [(paths[0], "Spending insights"), (paths[2], "No reminders needed")]:
            response = self.client.get(path, HTTP_ACCEPT="text/html")
            self.assertContains(response, text)
            self.assertEqual(response["Cache-Control"], "no-store")
        self.expense()
        self.assertContains(self.client.get(paths[2], HTTP_ACCEPT="text/html"), "Copy reminder")
        Membership.objects.filter(group=self.group, user=self.b).update(left_at="2026-02-01T00:00:00Z")
        for service in [spending_report, expense_export, settlement_nudges]:
            with self.assertRaises(PermissionDenied):
                service(self.b, group_id=self.group.id)

    def test_other_group_is_excluded_and_payer_can_have_no_share(self):
        group = create_group(actor=self.a, name="Other")
        create_expense(actor=self.a, group_id=group.id, paid_by=self.a.id, amount="999.00", description="Private", expense_date="2026-01-01")
        self.expense(participants=[self.b.id], amount="1.01")
        report = spending_report(self.a, group_id=self.group.id, month="2026-01")
        self.assertEqual(report["summary"], {"total": "1.01", "expense_count": 1, "your_paid": "1.01", "your_share": "0.00"})
        self.assertEqual(settlement_nudges(self.a, group_id=self.group.id)[0]["amount"], "1.01")
