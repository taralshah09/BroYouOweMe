from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.core.exceptions import ValidationError
from django.db import close_old_connections, connections
from django.test import TransactionTestCase, override_settings

from apps.accounts.models import User
from apps.expenses.services import create_expense
from apps.groups.services import add_member, create_group
from apps.settlements.models import Settlement
from apps.settlements.services import balance_mismatches, balances_for, create_settlement, resolve_settlement


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class SettlementConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.a = User.objects.create_user(username="alice", email="alice@example.com")
        self.b = User.objects.create_user(username="bob", email="bob@example.com")
        self.group = create_group(actor=self.a, name="Concurrent")
        add_member(actor=self.a, group_id=self.group.id, user_id=self.b.id)
        create_expense(actor=self.a, group_id=self.group.id, paid_by=self.a.id, amount=10, description="Dinner")

    def race(self, operation):
        ready = Barrier(2)
        def worker(index):
            close_old_connections()
            try:
                ready.wait(timeout=10)
                try:
                    operation()
                    return "ok"
                except ValidationError:
                    return "invalid"
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(worker, range(2)))

    def test_concurrent_claims_cannot_overreserve_debt(self):
        results = self.race(lambda: create_settlement(actor=self.b, group_id=self.group.id, receiver=self.a.id, amount=5))
        self.assertCountEqual(results, ["ok", "invalid"])
        self.assertEqual(Settlement.objects.count(), 1)
        self.assertEqual(balance_mismatches(), [])

    def test_concurrent_confirmations_apply_payment_once(self):
        row = create_settlement(actor=self.b, group_id=self.group.id, receiver=self.a.id, amount=5)
        results = self.race(lambda: resolve_settlement(actor=self.a, settlement_id=row.id, action="confirm"))
        self.assertCountEqual(results, ["ok", "invalid"])
        self.assertEqual(balances_for(self.a, group_id=self.group.id), {})
        self.assertEqual(balance_mismatches(), [])
