from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator

# Create your models here.

class Monitor(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="monitors")
    name = models.CharField(max_length=255)
    url = models.URLField(max_length=2048)
    interval_seconds = models.PositiveIntegerField(default=60, validators=[MinValueValidator(30)])
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.url})"

    class Meta:
        ordering = ["-created_at"]

