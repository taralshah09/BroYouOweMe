from django.test import TestCase

from apps.accounts.models import User
from apps.expenses.services import create_expense
from apps.groups.services import add_member, create_group
from apps.settlements.services import create_settlement, overview_for, resolve_settlement


class OverviewTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner", email="owner@example.invalid")
        self.friend = User.objects.create_user(username="friend", email="friend@example.invalid")
        self.group = create_group(actor=self.owner, name="Weekend")
        add_member(actor=self.owner, group_id=self.group.id, user_id=self.friend.id)

    def test_exact_totals_and_confirmed_payments(self):
        create_expense(actor=self.owner, group_id=self.group.id, paid_by=self.owner.id,
                       amount="10.01", description="Coffee")
        result = overview_for(self.owner)
        self.assertEqual((result["net"], result["owed"], result["owes"]), ("5.00", "5.00", "0.00"))
        payment = create_settlement(actor=self.friend, group_id=self.group.id,
                                    receiver=self.owner.id, amount="2.01")
        pending = overview_for(self.owner)
        self.assertEqual(pending["pending_count"], 1)
        self.assertEqual(pending["pending_group"], self.group.id)
        self.assertEqual(pending["net"], "5.00")
        resolve_settlement(actor=self.owner, settlement_id=payment.id, action="confirm")
        self.assertEqual(overview_for(self.owner)["net"], "2.99")
        self.assertEqual(overview_for(self.owner)["pending_count"], 0)
        debtor = overview_for(self.friend)
        self.assertTrue(debtor["negative"])
        self.assertEqual(debtor["owes"], "2.99")
        self.assertEqual(debtor["pending_count"], 0)

    def test_overall_nets_same_pair_across_groups_and_scopes_pending_reviews(self):
        other = create_group(actor=self.owner, name="Flat")
        add_member(actor=self.owner, group_id=other.id, user_id=self.friend.id)
        create_expense(actor=self.owner, group_id=self.group.id, paid_by=self.owner.id,
                       amount="12.00", description="Dinner")
        create_expense(actor=self.friend, group_id=other.id, paid_by=self.friend.id,
                       amount="20.00", description="Groceries")
        create_settlement(actor=self.friend, group_id=self.group.id,
                          receiver=self.owner.id, amount="1.00")
        result = overview_for(self.owner)
        self.assertEqual(result["net"], "4.00")
        self.assertTrue(result["negative"])
        self.assertEqual(result["owed"], "0.00")
        self.assertEqual(overview_for(self.owner, group_id=self.group.id)["owed"], "6.00")
        self.assertEqual(overview_for(self.owner, group_id=other.id)["pending_count"], 0)
