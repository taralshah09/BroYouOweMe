from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User
from apps.expenses.services import create_expense
from apps.groups.models import Group
from apps.groups.services import add_member, create_group


class Command(BaseCommand):
    help = "Create isolated demo users and a sample group. Safe to run repeatedly."

    @transaction.atomic
    def handle(self, *args, **options):
        users = []
        for name in ["mohit", "rahul", "ankit", "priya", "sneha"]:
            username, email = f"demo_{name}", f"demo_{name}@example.invalid"
            user = User.objects.filter(username__iexact=username).first()
            if user is not None:
                if user.email != email or user.has_usable_password():
                    raise CommandError(f"Demo identity collision: {username}; no changes applied.")
            else:
                if User.objects.filter(email__iexact=email).exists():
                    raise CommandError("Demo email collision; no changes applied.")
                user = User.objects.create_user(username=username, email=email, password=None)
            users.append(user)
        owner = users[0]
        group = Group.objects.filter(created_by=owner, name="Demo Goa Trip").first()
        if group is None:
            group = create_group(actor=owner, name="Demo Goa Trip")
            for user in users[1:]:
                add_member(group_id=group.pk, actor=owner, user_id=user.pk)
            for payer, amount, description in [(owner, "1200.00", "Demo dinner"),
                                                (users[1], "650.50", "Demo taxi"),
                                                (users[3], "1000.00", "Demo groceries")]:
                create_expense(actor=owner, group_id=group.pk, paid_by=payer.pk,
                               amount=amount, description=description)
        self.stdout.write(self.style.SUCCESS("Demo users ready: " + ", ".join(user.username for user in users)))
        self.stdout.write(f"Demo group: {group.pk}. Dummy accounts cannot log in; invite them by exact username to test splits.")
