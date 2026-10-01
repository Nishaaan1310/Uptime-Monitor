from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import (
    AuthenticationForm,
    UserChangeForm,
    UserCreationForm,
)

User = get_user_model()

class CustomUserCreationForm(UserCreationForm):
    
    class Meta:
        model = User
        fields = ("email",)

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if email:
            email = email.lower()
            if User.objects.filter(email=email).exists():
                raise forms.ValidationError("A user with that email already exists")
        return email

class CustomUserChangeForm(UserChangeForm):

    class Meta:
        model = User
        fields = ("email",)

class CustomLoginForm(AuthenticationForm):
    username = forms.EmailField(
        label = "Email", widget=forms.EmailInput(attrs={"autofocus": True})
    )
