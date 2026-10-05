from django.contrib import admin
from .models import Monitor, CheckResult

# Register your models here.

admin.site.register(Monitor)
admin.site.register(CheckResult)