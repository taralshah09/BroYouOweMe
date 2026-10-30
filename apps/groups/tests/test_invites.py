import json
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.core.management.base import CommandError
from django.http import Http404
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.activity.models import Activity
from apps.expenses.models import Expense
from apps.expenses.services import create_expense
from apps.groups.models import Group, Membership
from apps.groups.services import add_member, create_group, create_invite, join_invite, revoke_invite
from apps.settlements.models import Balance
from apps.settlements.services import balance_mismatches


@override_settings(SECURE_SSL_REDIRECT=False, PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
                   STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                             "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class InviteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(username="owner", email="owner@example.com", password="test-pass")
        cls.friend = User.objects.create_user(username="friend", email="friend@example.com", password="test-pass")
        cls.outsider = User.objects.create_user(username="outsider", email="outsider@example.com", password="test-pass")
        cls.group = create_group(actor=cls.admin, name="Private trip")
        add_member(group_id=cls.group.pk, actor=cls.admin, user_id=cls.friend.pk)

    def invite(self):
        return create_invite(group_id=self.group.pk, actor=self.admin)

    def test_permissions_scope_and_qr(self):
        invite = self.invite()
        for user in [self.friend, self.outsider]:
            self.client.force_login(user)
            for path in [f"/groups/{self.group.pk}/invites", f"/groups/{self.group.pk}/invites/{invite.pk}/qr"]:
                self.assertEqual(self.client.get(path).status_code, 403)
            with self.assertRaises(PermissionDenied):
                create_invite(group_id=self.group.pk, actor=user)
            with self.assertRaises(PermissionDenied):
                revoke_invite(group_id=self.group.pk, invite_id=invite.pk, actor=user)
        self.client.force_login(self.admin)
        response = self.client.get(f"/groups/{self.group.pk}/invites/{invite.pk}/qr")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/svg+xml")
        self.assertIn(b"<svg", response.content)
        self.assertEqual(response["Cache-Control"], "no-store")
        other = create_group(actor=self.admin, name="Other")
        self.assertEqual(self.client.post(f"/groups/{other.pk}/invites/{invite.pk}", {}).status_code, 404)

    def test_multiuse_idempotence_and_rejoin(self):
        invite = self.invite()
        self.assertAlmostEqual((invite.expires_at - invite.created_at).total_seconds(), 7 * 86400, delta=2)
        original = join_invite(token=invite.token, actor=self.admin)
        self.assertEqual(original.role, "admin")
        for user in [self.friend, self.outsider]:
            join_invite(token=invite.token, actor=user)
            join_invite(token=invite.token, actor=user)
        self.assertEqual(self.group.memberships.count(), 3)
        self.assertEqual(Activity.objects.filter(action="member.joined").count(), 1)
        member = Membership.objects.get(group=self.group, user=self.outsider)
        member.left_at = timezone.now()
        member.role = "admin"
        member.save()
        joined = join_invite(token=invite.token, actor=self.outsider)
        self.assertIsNone(joined.left_at)
        self.assertEqual(joined.role, "member")

    def test_expired_revoked_and_deleted_group(self):
        for mode in ["expired", "revoked", "deleted"]:
            invite = self.invite()
            if mode == "expired":
                invite.expires_at = timezone.now() - timedelta(seconds=1)
                invite.save()
            elif mode == "revoked":
                revoke_invite(group_id=self.group.pk, invite_id=invite.pk, actor=self.admin)
            else:
                self.group.deleted_at = timezone.now()
                self.group.save()
            with self.assertRaises(Http404):
                join_invite(token=invite.token, actor=self.outsider)
            self.assertEqual(self.client.get(f"/invite/{invite.token}").status_code, 404)
        self.assertFalse(Membership.objects.filter(group=self.group, user=self.outsider).exists())

    def test_public_preview_does_not_expose_members(self):
        invite = self.invite()
        response = self.client.get(f"/invite/{invite.token}")
        self.assertEqual(response.json(), {"group_name": "Private trip", "member_count": 2})
        self.assertEqual(response["Referrer-Policy"], "no-referrer")
        self.assertFalse(self.client.session.get("pending_invite"))
        self.assertEqual(self.client.get(f"/invite/{invite.token}/join").status_code, 405)

    def test_signup_and_login_auto_join(self):
        invite = self.invite()
        response = self.client.post(f"/invite/{invite.token}/join", {}, HTTP_ACCEPT="text/html")
        self.assertRedirects(response, "/signup", fetch_redirect_response=False)
        self.assertEqual(self.client.post("/signup", {"username": "bad"}).status_code, 400)
        self.assertEqual(self.client.session["pending_invite"], invite.token)
        response = self.client.post("/signup", json.dumps({"username": "newfriend", "email": "new@example.com", "password": "a-good-password-123"}), content_type="application/json")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["group_id"], self.group.pk)
        self.assertNotIn("pending_invite", self.client.session)
        self.client.logout()
        self.client.post(f"/invite/{invite.token}/join", {})
        response = self.client.post("/login", {"username": "outsider", "password": "test-pass"}, HTTP_ACCEPT="text/html")
        self.assertRedirects(response, f"/groups/{self.group.pk}", fetch_redirect_response=False)
        self.assertTrue(Membership.objects.filter(group=self.group, user=self.outsider).exists())

    def test_revoked_during_signup_does_not_join_or_break_account(self):
        invite = self.invite()
        self.client.post(f"/invite/{invite.token}/join", {})
        revoke_invite(group_id=self.group.pk, invite_id=invite.pk, actor=self.admin)
        response = self.client.post("/signup", {"username": "late", "email": "late@example.com", "password": "a-good-password-123"})
        self.assertEqual(response.status_code, 201)
        self.assertFalse(Membership.objects.filter(user__username="late").exists())

    def test_csrf_and_html_screens(self):
        invite = self.invite()
        csrf = Client(enforce_csrf_checks=True)
        self.assertEqual(csrf.post(f"/invite/{invite.token}/join", {}).status_code, 403)
        self.client.force_login(self.admin)
        for path in [f"/groups/{self.group.pk}/invites", f"/invite/{invite.token}", f"/groups/{self.group.pk}/simplified"]:
            self.assertEqual(self.client.get(path, HTTP_ACCEPT="text/html").status_code, 200)

    def test_privacy_no_directory_or_dropdown(self):
        for actor in [None, self.admin, self.friend]:
            self.client.logout()
            if actor:
                self.client.force_login(actor)
            for method in [self.client.get, self.client.post]:
                self.assertEqual(method("/users").status_code, 404)
        self.client.force_login(self.admin)
        page = self.client.get(f"/groups/{self.group.pk}", HTTP_ACCEPT="text/html")
        self.assertNotContains(page, "outsider")
        self.assertNotContains(page, "People")
        response = self.client.post(f"/groups/{self.group.pk}/members", {"username": "OUTSIDER"})
        self.assertEqual(response.status_code, 201)

    def test_simplification_cancels_cycles_without_writes(self):
        add_member(group_id=self.group.pk, actor=self.admin, user_id=self.outsider.pk)
        users = [self.admin, self.friend, self.outsider]
        for index, payer in enumerate(users):
            create_expense(actor=payer, group_id=self.group.pk, paid_by=payer.pk, amount=3,
                           participants=[users[(index + 1) % 3].pk], description="Cycle")
        self.client.force_login(self.admin)
        before = list(Balance.objects.values())
        self.assertEqual(sum(bool(row["net_paise"]) for row in before), 3)
        events = Activity.objects.count()
        self.assertEqual(self.client.get(f"/groups/{self.group.pk}/simplified").json(), {"display_only": True, "transfers": []})
        self.assertEqual(list(Balance.objects.values()), before)
        self.assertEqual(Activity.objects.count(), events)
        self.assertEqual(balance_mismatches(), [])
        stranger = User.objects.create_user(username="stranger", email="s@example.com")
        self.client.force_login(stranger)
        self.assertEqual(self.client.get(f"/groups/{self.group.pk}/simplified").status_code, 403)

    def test_suggestion_cannot_bypass_pairwise_settlement_validation(self):
        add_member(group_id=self.group.pk, actor=self.admin, user_id=self.outsider.pk)
        for payer, participant in [(self.admin, self.friend), (self.friend, self.outsider)]:
            create_expense(actor=payer, group_id=self.group.pk, paid_by=payer.pk,
                           amount=10, participants=[participant.pk], description="Chain")
        self.client.force_login(self.outsider)
        response = self.client.get(f"/groups/{self.group.pk}/simplified")
        self.assertEqual(response.json()["transfers"], [{"payer": self.outsider.pk,
                         "payer_username": "outsider", "receiver": self.admin.pk,
                         "receiver_username": "owner", "amount": 10}])
        response = self.client.post("/settlements", {"group_id": self.group.pk,
                                    "receiver": self.admin.pk, "amount": 10})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(balance_mismatches(), [])

    def test_demo_seed_idempotence_and_collision_rollback(self):
        call_command("seed_demo", stdout=StringIO())
        counts = (User.objects.count(), Group.objects.count(), Expense.objects.count(), Activity.objects.count())
        call_command("seed_demo", stdout=StringIO())
        self.assertEqual(counts, (User.objects.count(), Group.objects.count(), Expense.objects.count(), Activity.objects.count()))
        self.assertEqual(balance_mismatches(), [])
        self.assertEqual(User.objects.filter(username__startswith="demo_").count(), 5)
        user = User.objects.get(username="demo_ankit")
        user.email = "real@example.com"
        user.save()
        with self.assertRaises(CommandError):
            call_command("seed_demo", stdout=StringIO())

    def test_audit_failures_roll_back_invite_and_membership(self):
        from apps.groups.models import Invite

        with patch("apps.activity.services.record", side_effect=RuntimeError("audit failed")):
            with self.assertRaises(RuntimeError):
                self.invite()
        self.assertFalse(Invite.objects.exists())
        invite = self.invite()
        with patch("apps.activity.services.record", side_effect=RuntimeError("audit failed")):
            with self.assertRaises(RuntimeError):
                join_invite(token=invite.token, actor=self.outsider)
            with self.assertRaises(RuntimeError):
                revoke_invite(group_id=self.group.pk, invite_id=invite.pk, actor=self.admin)
        self.assertFalse(Membership.objects.filter(group=self.group, user=self.outsider).exists())
        invite.refresh_from_db()
        self.assertIsNone(invite.revoked_at)
