from django.urls import path
from .views import MonitorCreateView, monitor_list

app_name = "monitors"

urlpatterns = [
    path("new/", MonitorCreateView.as_view(), name="create"),
    path("dashboard/", monitor_list, name="dashboard"),
]