from collections import Counter

from django.core.management.base import BaseCommand

from monitors.services import run_due_checks

class Command(BaseCommand):
    help = "Check active monitors that are due, and record the results."

    def handle(self, *args, **options):

        reports = run_due_checks()
        for report in reports:
            line = f"{report.name}: {report.status.upper()}"
            if report.detail:
                line += f" ({report.detail})"
            stream = self.stderr if report.status == "error" else self.stdout
            stream.write(line)

        counts = Counter(report.status for report in reports)
        message = f"Checked {counts['up'] + counts['down']}: {counts['up']} up, {counts['down']} down"
        if counts["skipped"]:
            message += f", {counts['skipped']} skipped"
        if counts["error"]:
            message += f", {counts['error']} errored"

        healthy = not counts["skipped"] and not counts["error"]
        style = self.style.SUCCESS if healthy else self.style.WARNING
        self.stdout.write(style(message))


            
