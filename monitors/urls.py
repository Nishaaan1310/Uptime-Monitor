from django.urls import path
from .views import MonitorCreateView, monitor_list, monitor_delete, monitor_edit

app_name = "monitors"

urlpatterns = [
    path("new/", MonitorCreateView.as_view(), name="create"),
    path("dashboard/", monitor_list, name="dashboard"),
    path("<int:pk>/delete/", monitor_delete, name="delete"),
    path("<int:pk>/edit/", monitor_edit, name="edit")
]