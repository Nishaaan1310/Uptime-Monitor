from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .forms import MonitorForm
from .models import Monitor
from django.views.generic import CreateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy

# Create your views here.

class MonitorCreateView(LoginRequiredMixin, CreateView):
    form_class = MonitorForm
    template_name = "monitors/create.html"
    success_url = reverse_lazy("monitors:dashboard")

    def form_valid(self, form):
        form.instance.owner = self.request.user
        return super().form_valid(form)

@login_required
def monitor_list(request):
    monitors = request.user.monitors.all()
    return render(request, "monitors/dashboard.html", {
        "monitors": monitors
    })


