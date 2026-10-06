from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction

from monitors.models import Monitor, CheckResult, Status
from monitors.checker import check_url


class Command(BaseCommand):
    help = "Check active monitors that are due, and record the results."

    def handle(self, *args, **options):
        monitors = Monitor.objects.filter(is_active=True)

        for monitor in monitors:
            started_at = timezone.now()
            if not monitor.is_due(started_at):
                continue
            try:
                result = check_url(monitor.url)
                with transaction.atomic():
                    CheckResult.objects.create(monitor=monitor, **result)
                    monitor.status= Status.UP if result["is_up"] else Status.DOWN
                    monitor.last_checked_at= started_at
                    monitor.save(update_fields=["status", "last_checked_at"])

                label = "UP" if result["is_up"] else "DOWN"
                self.stdout.write(f"{monitor.name}: {label}")
            except Exception as e:
                self.stderr.write(f"{monitor.name}: Error: {e}")
                
            


            
