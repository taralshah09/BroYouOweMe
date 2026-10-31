import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from unittest.mock import patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.db import close_old_connections, connections, transaction
from django.test import Client, TestCase, TransactionTestCase, override_settings

from apps.accounts.models import User
from apps.activity.models import Activity
from apps.expenses.models import Expense
from apps.expenses.services import create_expense, delete_expense, update_expense
from apps.groups.models import Group, Membership
from apps.groups.services import (
    add_member, change_role, create_group, create_invite, delete_group,
    join_invite, remove_member, require_member, valid_invite,
)
from apps.settlements.models import Balance
from apps.settlements.services import balance_mismatches, create_settlement, resolve_settlement


@override_settings(SECURE_SSL_REDIRECT=False,
                   STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                             "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class LifecycleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(username="owner", email="owner@example.invalid")
        cls.friend = User.objects.create_user(username="friend", email="friend@example.invalid")
        cls.other = User.objects.create_user(username="other", email="other@example.invalid")
        cls.group = create_group(actor=cls.admin, name="Trip")
        for user in [cls.friend, cls.other]:
            add_member(group_id=cls.group.pk, actor=cls.admin, user_id=user.pk)

    def role(self, user, role, actor=None):
        return change_role(group_id=self.group.pk, actor=actor or self.admin, user_id=user.pk, role=role)

    def remove(self, user, actor=None):
        return remove_member(group_id=self.group.pk, actor=actor or self.admin, user_id=user.pk)

    def expense(self, **changes):
        values = dict(actor=self.admin, group_id=self.group.pk, paid_by=self.admin.pk,
                      amount="10.01", description="Dinner", participants=[self.admin.pk, self.friend.pk])
        values.update(changes)
        return create_expense(**values)

    def settle(self):
        claim = create_settlement(actor=self.friend, group_id=self.group.pk,
                                  receiver=self.admin.pk, amount="5.00")
        resolve_settlement(actor=self.admin, settlement_id=claim.pk, action="confirm")

    def test_role_permissions_validation_and_last_admin(self):
        with self.assertRaises(PermissionDenied):
            self.role(self.other, "admin", actor=self.friend)
        for role in [None, "owner", [], True]:
            with self.assertRaises(ValidationError):
                self.role(self.friend, role)
        with self.assertRaises(ValidationError):
            self.role(self.admin, "member")
        self.role(self.friend, "admin")
        self.role(self.admin, "member", actor=self.friend)
        self.assertEqual(Membership.objects.get(group=self.group, user=self.admin).role, "member")
        count = Activity.objects.count()
        self.role(self.friend, "admin", actor=self.friend)
        self.assertEqual(Activity.objects.count(), count)

    def test_last_admin_cannot_leave_and_another_admin_can_be_removed(self):
        with self.assertRaises(ValidationError):
            self.remove(self.admin)
        self.role(self.friend, "admin")
        self.remove(self.friend)
        with self.assertRaises(PermissionDenied):
            require_member(self.group.pk, self.friend)
        self.assertEqual(Activity.objects.latest("pk").action, "member.removed")

    def test_member_can_leave_but_cannot_remove_another_member(self):
        with self.assertRaises(PermissionDenied):
            self.remove(self.other, actor=self.friend)
        self.remove(self.friend, actor=self.friend)
        self.assertEqual(Activity.objects.latest("pk").action, "member.left")
        with self.assertRaises(Http404):
            self.role(self.friend, "admin")

    def test_pairwise_balances_block_removal_and_deletion(self):
        self.expense()
        for operation in [lambda: self.remove(self.friend), lambda: self.remove(self.friend, actor=self.friend),
                          lambda: delete_group(group_id=self.group.pk, actor=self.admin)]:
            with self.assertRaises(ValidationError):
                operation()
        # A zero net total is insufficient if separate pairwise debts remain.
        self.expense(paid_by=self.friend.pk, participants=[self.friend.pk, self.other.pk], amount="10.00")
        with self.assertRaises(ValidationError):
            self.remove(self.friend)
        self.assertFalse(balance_mismatches())

    def test_rejoin_preserves_membership_and_historical_splits(self):
        expense = self.expense()
        self.settle()
        original = Membership.objects.get(group=self.group, user=self.friend)
        splits = list(expense.splits.values_list("user_id", "share_paise"))
        invite = create_invite(group_id=self.group.pk, actor=self.admin)
        self.role(self.friend, "admin")
        self.remove(self.friend)
        restored = add_member(group_id=self.group.pk, actor=self.admin, user_id=self.friend.pk)
        self.assertEqual(restored.pk, original.pk)
        self.assertEqual(restored.role, "member")
        self.assertIsNone(restored.left_at)
        self.remove(self.friend)
        restored = join_invite(token=invite.token, actor=self.friend)
        self.assertEqual(restored.pk, original.pk)
        self.assertEqual(list(expense.splits.values_list("user_id", "share_paise")), splits)
        self.assertFalse(balance_mismatches())

    def test_delete_retains_history_and_blocks_all_group_access(self):
        expense = self.expense()
        self.settle()
        invite = create_invite(group_id=self.group.pk, actor=self.admin)
        with self.assertRaises(PermissionDenied):
            delete_group(group_id=self.group.pk, actor=self.friend)
        delete_group(group_id=self.group.pk, actor=self.admin)
        self.assertFalse(Group.objects.filter(pk=self.group.pk).exists())
        self.assertTrue(Group.all_objects.filter(pk=self.group.pk, deleted_at__isnull=False).exists())
        self.assertTrue(Expense.objects.filter(pk=expense.pk).exists())
        for operation in [lambda: require_member(self.group.pk, self.admin), lambda: valid_invite(invite.token),
                          lambda: join_invite(token=invite.token, actor=self.other), lambda: self.expense()]:
            with self.assertRaises(Http404):
                operation()
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get("/groups").json(), [])
        self.assertEqual(Activity.objects.latest("pk").action, "group.deleted")

    def test_changes_cannot_recreate_departed_members_balances(self):
        expense = self.expense()
        self.settle()
        self.remove(self.friend)
        events = Activity.objects.count()
        with self.assertRaises(ValidationError):
            delete_expense(actor=self.admin, expense_id=expense.pk)
        with self.assertRaises(ValidationError):
            update_expense(actor=self.admin, expense_id=expense.pk, participants=[self.admin.pk], amount="11.00")
        expense.refresh_from_db()
        self.assertIsNone(expense.deleted_at)
        self.assertEqual(expense.amount_paise, 1001)
        self.assertEqual(Activity.objects.count(), events)
        self.assertFalse(Balance.objects.filter(group=self.group).exclude(net_paise=0).exists())
        self.assertFalse(balance_mismatches())

    def test_activity_failure_rolls_back_role_leave_and_delete(self):
        with patch("apps.activity.services.record", side_effect=RuntimeError("audit unavailable")):
            for operation in [lambda: self.role(self.friend, "admin"), lambda: self.remove(self.friend),
                              lambda: delete_group(group_id=self.group.pk, actor=self.admin)]:
                with self.assertRaises(RuntimeError):
                    operation()
        member = Membership.objects.get(group=self.group, user=self.friend)
        self.assertEqual(member.role, "member")
        self.assertIsNone(member.left_at)
        self.assertTrue(Group.objects.filter(pk=self.group.pk).exists())

    def test_unrelated_expenses_remain_editable_after_member_leaves(self):
        self.remove(self.friend)
        expense = self.expense(participants=[self.admin.pk, self.other.pk])
        update_expense(actor=self.admin, expense_id=expense.pk, amount="12.34")
        delete_expense(actor=self.admin, expense_id=expense.pk)
        self.assertFalse(balance_mismatches())

    def test_browser_departure_removal_and_deletion_redirects(self):
        self.client.force_login(self.admin)
        prefix = f"/groups/{self.group.pk}"
        self.assertRedirects(self.client.post(f"{prefix}/members/{self.friend.pk}/remove", HTTP_ACCEPT="text/html"), prefix + "/members")
        self.client.force_login(self.other)
        self.assertRedirects(self.client.post(prefix + "/leave", HTTP_ACCEPT="text/html"), "/groups")
        self.client.force_login(self.admin)
        self.assertRedirects(self.client.post(prefix + "/delete", HTTP_ACCEPT="text/html"), "/groups")
        self.assertEqual(self.client.get(prefix).status_code, 404)

    def test_endpoints_html_permissions_methods_csrf_and_scope(self):
        self.client.force_login(self.admin)
        prefix = f"/groups/{self.group.pk}"
        response = self.client.get(prefix + "/members", HTTP_ACCEPT="text/html")
        self.assertContains(response, "Confirm deleting Trip")
        self.assertContains(response, f"{prefix}/members/{self.friend.pk}/role")
        role_path = f"{prefix}/members/{self.friend.pk}/role"
        self.assertEqual(self.client.get(role_path).status_code, 405)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.admin)
        self.assertEqual(csrf_client.post(role_path, {"role": "admin"}).status_code, 403)
        self.assertEqual(self.client.post(role_path, json.dumps({"role": "admin"}), content_type="application/json").status_code, 200)
        self.assertEqual(self.client.post(role_path, {"role": "member"}, HTTP_ACCEPT="text/html").status_code, 302)
        foreign = create_group(actor=self.admin, name="Elsewhere")
        self.assertEqual(self.client.post(f"/groups/{foreign.pk}/members/{self.friend.pk}/remove").status_code, 404)
        self.client.force_login(self.friend)
        self.assertNotContains(self.client.get(prefix + "/members", HTTP_ACCEPT="text/html"), "Confirm deleting Trip")
        self.assertEqual(self.client.post(prefix + "/delete").status_code, 403)
        self.assertEqual(self.client.post(f"{prefix}/members/{self.other.pk}/remove").status_code, 403)
        self.assertEqual(self.client.post(prefix + "/leave").status_code, 200)
        self.assertEqual(self.client.get(prefix + "/members").status_code, 403)


class LifecycleConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="owner", email="owner@example.invalid")
        self.friend = User.objects.create_user(username="friend", email="friend@example.invalid")
        self.group = create_group(actor=self.admin, name="Concurrent lifecycle")
        add_member(group_id=self.group.pk, actor=self.admin, user_id=self.friend.pk)

    def worker(self, operation):
        close_old_connections()
        try:
            return operation()
        finally:
            connections.close_all()

    def test_simultaneous_admin_departures_leave_one_admin(self):
        change_role(group_id=self.group.pk, actor=self.admin, user_id=self.friend.pk, role="admin")
        ready = Barrier(2)

        def leave(user):
            ready.wait(timeout=10)
            try:
                remove_member(group_id=self.group.pk, actor=user, user_id=user.pk)
                return "left"
            except ValidationError:
                return "blocked"

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self.worker, lambda user=user: leave(user)) for user in [self.admin, self.friend]]
            results = [future.result(timeout=15) for future in futures]
        self.assertCountEqual(results, ["left", "blocked"])
        self.assertEqual(self.group.memberships.filter(left_at__isnull=True, role="admin").count(), 1)

    def test_removal_and_expense_creation_serialize(self):
        ready = Barrier(2)

        def remove():
            ready.wait(timeout=10)
            try:
                remove_member(group_id=self.group.pk, actor=self.admin, user_id=self.friend.pk)
                return "removed"
            except ValidationError:
                return "removal blocked"

        def expense():
            ready.wait(timeout=10)
            try:
                create_expense(group_id=self.group.pk, actor=self.friend, paid_by=self.admin.pk,
                               amount="10.00", description="Concurrent dinner")
                return "created"
            except PermissionDenied:
                return "expense blocked"

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self.worker, operation) for operation in [remove, expense]]
            results = {future.result(timeout=15) for future in futures}
        self.assertIn(results, [{"removed", "expense blocked"}, {"removal blocked", "created"}])
        self.assertFalse(balance_mismatches())

    def test_waiting_invite_join_rechecks_deleted_group(self):
        invite = create_invite(group_id=self.group.pk, actor=self.admin)
        preview_read = Event()

        def observed_preview(token):
            result = valid_invite(token)
            preview_read.set()
            return result

        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                Group.objects.select_for_update().get(pk=self.group.pk)
                with patch("apps.groups.services.valid_invite", side_effect=observed_preview):
                    future = pool.submit(self.worker, lambda: join_invite(token=invite.token, actor=self.friend))
                    self.assertTrue(preview_read.wait(timeout=10))
                    delete_group(group_id=self.group.pk, actor=self.admin)
            with self.assertRaises(Http404):
                future.result(timeout=15)
