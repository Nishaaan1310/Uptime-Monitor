from collections import Counter

from django.core.management.base import BaseCommand

from monitors.services import run_due_checks

class Command(BaseCommand):
    help = "Check active monitors that are due, and record the results."

    def handle(self, *args, **options):

        reports = run_due_checks()
        for report in reports:
            if report.status == "error":
                self.stderr.write(f"{report.name}: Error: {report.detail}")
            else:
                self.stdout.write(f"{report.name}: {report.status.upper()}")

        counts = Counter(report.status for report in reports)
        message = f"Checked {len(reports)}: {counts['up']} up, {counts['down']} down"

        if counts["error"]:
            message += f", {counts['error']} errored"
            self.stdout.write(self.style.WARNING(f"\n{message}"))

        else:
            self.stdout.write(self.style.SUCCESS(f"\n{message}"))

                
            


            
