from django.core.management.base import BaseCommand, CommandError

from apps.settlements.services import balance_mismatches


class Command(BaseCommand):
    help = "Recompute Phase 1 equal-split expenses and verify maintained balances."

    def handle(self, *args, **options):
        mismatches = balance_mismatches()
        if mismatches:
            raise CommandError(f"Balance mismatches: {mismatches}")
        self.stdout.write(self.style.SUCCESS("Balance integrity check passed."))
