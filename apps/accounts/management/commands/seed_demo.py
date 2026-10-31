import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User
from apps.expenses.services import create_expense
from apps.groups.models import Group
from apps.groups.services import add_member, create_group


class Command(BaseCommand):
    help = "Create isolated demo users and a sample group. Safe to run repeatedly."

    def add_arguments(self, parser):
        parser.add_argument("--reviewer", action="store_true",
                            help="Create login-enabled reviewer accounts using DEMO_PASSWORD.")

    @transaction.atomic
    def handle(self, *args, **options):
        if options["reviewer"]:
            return self.seed_reviewers()
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

    def seed_reviewers(self):
        password = os.environ.get("DEMO_PASSWORD", "")
        if len(password) < 12:
            raise CommandError("Set DEMO_PASSWORD to at least 12 characters for the public reviewer accounts.")
        users = []
        for name in ["mohit", "rahul", "ankit"]:
            username = f"reviewer_{name}"
            email = f"{username}@example.invalid"
            user = User.objects.filter(username__iexact=username).first()
            if user is not None:
                if (user.email != email or not user.check_password(password)
                        or not user.is_active or user.is_staff or user.is_superuser):
                    raise CommandError(f"Reviewer identity collision: {username}; no changes applied.")
            else:
                if User.objects.filter(email__iexact=email).exists():
                    raise CommandError("Reviewer email collision; no changes applied.")
                user = User.objects.create_user(username=username, email=email, password=password)
            users.append(user)
        owner, rahul, ankit = users
        group = Group.all_objects.filter(created_by=owner, name="Goa Trip (Demo)").first()
        if group is None:
            group = create_group(actor=owner, name="Goa Trip (Demo)")
            for user in [rahul, ankit]:
                add_member(group_id=group.pk, actor=owner, user_id=user.pk)
            create_expense(actor=owner, group_id=group.pk, paid_by=owner.pk,
                           amount="1200.00", description="Dinner at Goa")
        self.stdout.write(self.style.SUCCESS("Reviewer accounts ready: " + ", ".join(user.username for user in users)))
        self.stdout.write(f"Reviewer group: {group.pk}. Existing data and passwords are preserved.")
