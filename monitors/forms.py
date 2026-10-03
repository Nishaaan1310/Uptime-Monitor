from django import forms
from .models import Monitor

class MonitorForm(forms.ModelForm):
    class Meta:
        model = Monitor
        fields = ["name", "url", "interval_seconds"]