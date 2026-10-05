from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy
from django.views.generic import CreateView

from .forms import CustomLoginForm, CustomUserCreationForm
from django.contrib.auth.decorators import login_required

# Create your views here.

class SignUpView(CreateView):
    form_class = CustomUserCreationForm
    success_url = reverse_lazy("users:login")
    template_name = "users/signup.html"

class CustomLoginView(LoginView):
    form_class = CustomLoginForm
    template_name = "users/login.html"
    next_page = reverse_lazy("monitors:dashboard")

class CustomLogoutView(LogoutView):
    next_page = "users:login"
