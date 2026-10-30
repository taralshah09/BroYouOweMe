from django.core.management.base import BaseCommand, CommandError

from apps.settlements.services import balance_mismatches


class Command(BaseCommand):
    help = "Verify expense allocations and recompute expenses plus confirmed settlements."

    def handle(self, *args, **options):
        mismatches = balance_mismatches()
        if mismatches:
            raise CommandError(f"Balance mismatches: {mismatches}")
        self.stdout.write(self.style.SUCCESS("Balance integrity check passed."))
