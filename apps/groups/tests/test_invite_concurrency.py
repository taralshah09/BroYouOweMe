from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from unittest.mock import patch

from django.db import close_old_connections, connections, transaction
from django.http import Http404
from django.test import TransactionTestCase

from apps.accounts.models import User
from apps.activity.models import Activity
from apps.groups.models import Group, Membership
from apps.groups.services import create_group, create_invite, join_invite, revoke_invite, valid_invite


class InviteConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin", email="admin@example.com")
        self.friend = User.objects.create_user(username="friend", email="friend@example.com")
        self.group = create_group(actor=self.admin, name="Concurrent invites")
        self.invite = create_invite(group_id=self.group.pk, actor=self.admin)

    def worker(self, operation):
        close_old_connections()
        try:
            return operation()
        finally:
            connections.close_all()

    def test_simultaneous_joins_only_record_once(self):
        ready = Barrier(2)

        def join():
            ready.wait(timeout=10)
            return join_invite(token=self.invite.token, actor=self.friend).pk

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self.worker, join) for _ in range(2)]
            results = [future.result(timeout=15) for future in futures]
        self.assertEqual(results[0], results[1])
        self.assertEqual(Activity.objects.filter(action="member.joined").count(), 1)

    def test_waiting_join_rechecks_after_revocation(self):
        preview_read = Event()

        def observed_preview(token):
            invite = valid_invite(token)
            preview_read.set()
            return invite

        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                Group.objects.select_for_update().get(pk=self.group.pk)
                with patch("apps.groups.services.valid_invite", side_effect=observed_preview):
                    future = pool.submit(self.worker, lambda: join_invite(token=self.invite.token, actor=self.friend))
                    self.assertTrue(preview_read.wait(timeout=10))
                    revoke_invite(group_id=self.group.pk, invite_id=self.invite.pk, actor=self.admin)
            with self.assertRaises(Http404):
                future.result(timeout=15)
        self.assertFalse(Membership.objects.filter(group=self.group, user=self.friend).exists())
