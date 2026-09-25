import hashlib
import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone

from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    """Custom user with role-based access, soft delete, and audit fields."""

    class Role(models.TextChoices):
        TECHNICIAN = "TECHNICIAN", "Lab Technician"
        ANALYST = "ANALYST", "Analyst"
        QC_OFFICER = "QC_OFFICER", "QC Officer"
        FOOD_SAFETY_OFFICER = "FOOD_SAFETY_OFFICER", "Food Safety Officer"
        ADMIN = "ADMIN", "Administrator"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField("Email Address", unique=True, db_index=True)
    username = models.CharField("Username", max_length=150, unique=True, db_index=True)
    first_name = models.CharField("First Name", max_length=150)
    last_name = models.CharField("Last Name", max_length=150)
    role = models.CharField(
        "Role",
        max_length=25,
        choices=Role.choices,
        default=Role.TECHNICIAN,
        db_index=True,
    )
    phone = models.CharField("Phone", max_length=30, blank=True)
    laboratory = models.ForeignKey(
        "core.Laboratory",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staff",
    )
    avatar = models.ImageField("Avatar", upload_to="avatars/", blank=True)

    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)
    last_password_change = models.DateTimeField(null=True, blank=True)
    force_password_change = models.BooleanField(default=False)
    requires_2fa = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    class Meta:
        db_table = "accounts_user"
        ordering = ["last_name", "first_name"]
        indexes = [
            models.Index(fields=["email"]),
            models.Index(fields=["role"]),
            models.Index(fields=["is_active", "is_deleted"]),
        ]
        verbose_name = "User"
        verbose_name_plural = "Users"

    def __str__(self):
        return f"{self.get_full_name()} ({self.get_role_display()})"

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.username

    def get_short_name(self):
        return self.first_name or self.username

    def get_initials(self):
        if self.first_name and self.last_name:
            return f"{self.first_name[0]}{self.last_name[0]}".upper()
        return self.username[:2].upper()

    def soft_delete(self):
        self.is_deleted = True
        self.is_active = False
        self.save(update_fields=["is_deleted", "is_active"])

    @property
    def must_setup_2fa(self):
        """Check if user's role requires 2FA but they haven't set it up."""
        if self.role in settings.ROLES_REQUIRING_2FA or self.requires_2fa:
            from django_otp import devices_for_user

            return not any(d.confirmed for d in devices_for_user(self, confirmed=True))
        return False


class PasswordHistory(models.Model):
    """Stores hashed previous passwords to prevent reuse."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="password_history",
    )
    password_hash = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "accounts_password_history"
        ordering = ["-created_at"]

    @staticmethod
    def make_hash(password):
        """Create a SHA-256 hash for comparison (not for auth)."""
        return hashlib.sha256(password.encode("utf-8")).hexdigest()


    @property
    def must_setup_2fa(self):
        """Check if user's role requires 2FA but they haven't set it up."""
        if not getattr(settings, "ROLES_REQUIRING_2FA", []):
            return False
            
        if self.role in settings.ROLES_REQUIRING_2FA or self.requires_2fa:
            from django_otp import devices_for_user

            return not any(d.confirmed for d in devices_for_user(self, confirmed=True))
        return False

    