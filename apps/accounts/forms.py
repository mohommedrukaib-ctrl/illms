from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.contrib.auth.password_validation import validate_password

User = get_user_model()


class ILIMSLoginForm(AuthenticationForm):
    """Custom login form with styled fields."""

    username = forms.CharField(
        label="Email or Username",
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "placeholder": "Enter your email or username",
                "autocomplete": "username",
                "autofocus": True,
            }
        ),
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-input",
                "placeholder": "Enter your password",
                "autocomplete": "current-password",
            }
        ),
    )


class TOTPVerifyForm(forms.Form):
    """Form for TOTP code entry."""

    otp_token = forms.CharField(
        label="Authentication Code",
        max_length=6,
        min_length=6,
        widget=forms.TextInput(
            attrs={
                "class": "form-input form-input--code",
                "placeholder": "000000",
                "autocomplete": "one-time-code",
                "inputmode": "numeric",
                "pattern": "[0-9]{6}",
                "autofocus": True,
            }
        ),
    )


class ILIMSPasswordChangeForm(PasswordChangeForm):
    """Custom password change form."""

    old_password = forms.CharField(
        label="Current Password",
        widget=forms.PasswordInput(attrs={"class": "form-input", "autocomplete": "current-password"}),
    )
    new_password1 = forms.CharField(
        label="New Password",
        widget=forms.PasswordInput(attrs={"class": "form-input", "autocomplete": "new-password"}),
        validators=[validate_password],
    )
    new_password2 = forms.CharField(
        label="Confirm New Password",
        widget=forms.PasswordInput(attrs={"class": "form-input", "autocomplete": "new-password"}),
    )


class ProfileForm(forms.ModelForm):
    """User profile edit form."""

    class Meta:
        model = User
        fields = ["first_name", "last_name", "phone"]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-input"}),
            "last_name": forms.TextInput(attrs={"class": "form-input"}),
            "phone": forms.TextInput(attrs={"class": "form-input"}),
        }