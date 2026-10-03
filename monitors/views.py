from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .forms import MonitorForm

# Create your views here.

@login_required
def create_monitor(request):

    if request.method == 'POST':
        form = MonitorForm(request.POST)

        if form.is_valid():
            monitor = form.save(commit=False)
            monitor.owner = request.user
            monitor.save()

            return redirect('users:dashboard')
    else:
        form = MonitorForm()

    return render(request, 'monitors/create.html', {
        'form': form 
    })
