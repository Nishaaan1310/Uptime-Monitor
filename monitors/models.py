from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from django.utils import timezone

from .validators import validate_public_url

# Create your models here.

class Status(models.TextChoices):
    PENDING = "PENDING", "Pending Initial Check"
    UP = "UP", "Up"
    DOWN = "DOWN", "Down"

class Monitor(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="monitors")
    name = models.CharField(max_length=255)
    url = models.URLField(max_length=2048, validators=[validate_public_url])
    interval_seconds = models.PositiveIntegerField(default=60, validators=[MinValueValidator(30)])
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=10, choices=Status.choices,
        default = Status.PENDING)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    next_check_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.name} ({self.url})"

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["is_active", "next_check_at"])]

    def is_due(self, now):
        if self.last_checked_at is None:
            return True  
        return (now - self.last_checked_at).total_seconds() >= self.interval_seconds


class CheckResult(models.Model):
    monitor = models.ForeignKey(Monitor, on_delete=models.CASCADE, related_name="results")
    is_up = models.BooleanField()
    status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    response_time_ms = models.PositiveIntegerField(null=True, blank=True)
    error_message = models.TextField(blank=True, default="")
    checked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-checked_at"]
        indexes = [models.Index(fields=["monitor", "-checked_at"])]

    def __str__(self):
        state = "UP" if self.is_up else "DOWN"
        return f"{self.monitor.name}: {state} at {self.checked_at}"
