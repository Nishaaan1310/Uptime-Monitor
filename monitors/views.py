from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .forms import MonitorForm
from .models import Monitor
from django.views.generic import CreateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy

# Create your views here.

class MonitorCreateView(LoginRequiredMixin, CreateView):
    form_class = MonitorForm
    template_name = "monitors/monitor_form.html"
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

@login_required
def monitor_delete(request, pk):
    monitor = get_object_or_404(Monitor, pk=pk, owner=request.user)
    if request.method == "POST":
        monitor.delete()
        return redirect("monitors:dashboard")
    
    return render(request, "monitors/confirm_delete.html", {
        "monitor":monitor
    })

@login_required
def monitor_edit(request, pk):
    monitor = get_object_or_404(Monitor, pk=pk, owner=request.user)
    if request.method == "POST":
        form = MonitorForm(request.POST, instance=monitor)
        if form.is_valid:
            form.save()
            return redirect("monitors:dashboard")
    else:
        form = MonitorForm(instance=monitor)
        return render(request, "monitors/monitor_form.html", {
            "form": form,
            "monitor": monitor
        })





   
    


