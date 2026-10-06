from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction

from monitors.models import Monitor, CheckResult, Status
from monitors.checker import check_url

class Command(BaseCommand):
    help = "Check active monitors that are due, and record the results."

    def handle(self, *args, **options):
        now = timezone.now()
        due_monitors = Monitor.objects.filter(is_active=True, next_check_at__lte=now).order_by("next_check_at")[:100] # Cap at 100 items per run
        
        total_checked = 0
        down_count = 0
        error_count = 0

        for monitor in due_monitors:
            started_at = timezone.now()

            try:
                result = check_url(monitor.url)

                with transaction.atomic():
                    CheckResult.objects.create(monitor=monitor, **result)

                    monitor.status = Status.UP if result["is_up"] else Status.DOWN
                    monitor.last_checked_at = started_at
                    monitor.next_check_at = started_at + timedelta(seconds=monitor.interval_seconds)
                    monitor.save(update_fields=["status", "last_checked_at", "next_check_at"])
                
                total_checked += 1
                if not result["is_up"]:
                    down_count += 1

                label = "UP" if result["is_up"] else "DOWN"
                self.stdout.write(f"{monitor.name}: {label}")

            except Exception as e:
                error_count += 1
                self.stderr.write(f"{monitor.name}: Error: {e}")

        summary_msg = f"Checked {total_checked} monitors, {down_count} down"

        if error_count > 0 :
            summary_msg += f", {error_count} errored"
            self.stdout.write(self.style.WARNING(f"\n{summary_msg}"))

        else:
            self.stdout.write(self.style.SUCCESS(f"\n{summary_msg}"))

                
            


            
