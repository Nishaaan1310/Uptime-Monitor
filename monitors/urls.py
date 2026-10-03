from django.urls import path
from .views import create_monitor

app_name = "monitors"

urlpatterns = [
    path("new/", create_monitor, name="create")
]