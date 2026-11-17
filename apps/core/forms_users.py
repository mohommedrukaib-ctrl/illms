from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from apps.accounts.models import DEFAULT_MODULE_KEYS, Role, default_role_modules
from apps.core.models import Laboratory

User = get_user_model()


class UserForm(forms.ModelForm):
    password = forms.CharField(
        label="Password",
        required=False,
        widget=forms.PasswordInput(attrs={
            "class": "form-input",
            "placeholder": "Minimum 12 characters",
            "autocomplete": "new-password",
        }),
        help_text="Must contain at least 1 uppercase, 1 lowercase, 1 digit, and 1 special character.",
    )
    laboratory = forms.ModelChoiceField(
        queryset=Laboratory.objects.filter(is_active=True, is_deleted=False),
        required=False,
        label="Laboratory Facility",
        empty_label="— No Laboratory —",
        widget=forms.Select(attrs={"class": "form-input"}),
    )
    role = forms.ChoiceField(
        label="Role",
        widget=forms.Select(attrs={"class": "form-input"}),
    )

    class Meta:
        model = User
        fields = [
            "first_name", "last_name", "username", "email",
            "role", "laboratory", "password", "is_active",
        ]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-input", "placeholder": "First Name"}),
            "last_name": forms.TextInput(attrs={"class": "form-input", "placeholder": "Last Name"}),
            "username": forms.TextInput(attrs={"class": "form-input", "placeholder": "Username"}),
            "email": forms.EmailInput(attrs={"class": "form-input", "placeholder": "Email Address"}),
            "is_active": forms.CheckboxInput(),
        }

    def __init__(self, *args, is_create=True, **kwargs):
        self.is_create = is_create
        super().__init__(*args, **kwargs)
        roles = Role.objects.filter(is_active=True).order_by("name")
        self.fields["role"].choices = [(r.code, r.name) for r in roles]
        if not self.fields["role"].choices:
            self.fields["role"].choices = list(User.Role.choices)
        if is_create:
            self.fields["password"].required = True
        else:
            self.fields["password"].help_text = "Leave blank to preserve current password."

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if not email:
            raise ValidationError("An email address is required.")
        qs = User.objects.filter(email__iexact=email)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(f"Email '{email}' is already registered to another user.")
        return email

    def clean_username(self):
        username = (self.cleaned_data.get("username") or "").strip()
        if not username:
            raise ValidationError("A username is required.")
        qs = User.objects.filter(username__iexact=username)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(f"Username '{username}' is already in use.")
        return username

    def clean_password(self):
        password = self.cleaned_data.get("password")
        if self.is_create and not password:
            raise ValidationError("Password is required for new accounts.")
        if password:
            try:
                validate_password(password, user=self.instance)
            except ValidationError as e:
                raise ValidationError(e.messages)
        return password

    def clean_role(self):
        code = (self.cleaned_data.get("role") or "").strip().upper()
        if not Role.objects.filter(code=code, is_active=True).exists():
            # Allow legacy codes until roles are seeded
            if code not in dict(User.Role.choices):
                raise ValidationError("Select a valid active role.")
        return code


class AdminPasswordResetForm(forms.Form):
    new_password = forms.CharField(
        label="New Secure Password",
        widget=forms.PasswordInput(attrs={
            "class": "form-input",
            "placeholder": "Minimum 12 characters",
            "autocomplete": "new-password",
        }),
        help_text="Must contain at least 1 uppercase, 1 lowercase, 1 digit, and 1 special character.",
    )

    def __init__(self, *args, user_instance=None, **kwargs):
        self.user_instance = user_instance
        super().__init__(*args, **kwargs)

    def clean_new_password(self):
        password = self.cleaned_data.get("new_password")
        if not password:
            raise ValidationError("Password cannot be empty.")
        if self.user_instance:
            try:
                validate_password(password, user=self.user_instance)
            except ValidationError as e:
                raise ValidationError(e.messages)
        return password


class RoleForm(forms.ModelForm):
    class Meta:
        model = Role
        fields = [
            "code", "name", "description", "lab_scope", "is_active",
            "can_manage_users", "can_manage_roles", "can_manage_settings", "can_approve_qc",
        ]
        widgets = {
            "code": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "e.g. LAB_LEAD",
                "style": "text-transform: uppercase;",
            }),
            "name": forms.TextInput(attrs={"class": "form-input", "placeholder": "Display name"}),
            "description": forms.Textarea(attrs={"class": "form-textarea", "rows": 2}),
            "lab_scope": forms.Select(attrs={"class": "form-input"}),
            "is_active": forms.CheckboxInput(),
            "can_manage_users": forms.CheckboxInput(),
            "can_manage_roles": forms.CheckboxInput(),
            "can_manage_settings": forms.CheckboxInput(),
            "can_approve_qc": forms.CheckboxInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Dynamic module checkboxes
        modules = (self.instance.modules if self.instance and self.instance.pk else None) or default_role_modules()
        for key, label in DEFAULT_MODULE_KEYS:
            field_name = f"mod__{key}"
            self.fields[field_name] = forms.BooleanField(
                label=label,
                required=False,
                initial=bool(modules.get(key, False)),
                widget=forms.CheckboxInput(),
            )
        if self.instance and self.instance.pk and self.instance.is_system:
            self.fields["code"].disabled = True
            self.fields["code"].help_text = "System role code cannot be changed."

    def clean_code(self):
        if self.instance and self.instance.pk and self.instance.is_system:
            return self.instance.code
        code = (self.cleaned_data.get("code") or "").strip().upper().replace(" ", "_")
        if not code:
            raise ValidationError("Role code is required.")
        if not code.replace("_", "").isalnum():
            raise ValidationError("Use only letters, numbers, and underscores.")
        qs = Role.objects.filter(code=code)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(f"Role code '{code}' already exists.")
        return code

    def save(self, commit=True):
        role = super().save(commit=False)
        mods = default_role_modules()
        for key, _ in DEFAULT_MODULE_KEYS:
            mods[key] = bool(self.cleaned_data.get(f"mod__{key}", False))
        role.modules = mods
        if commit:
            role.save()
        return role