import hashlib
import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone

from .managers import UserManager


# Default module keys (aligned with feature flags / sidebar)
DEFAULT_MODULE_KEYS = [
    ("module.samples", "Samples"),
    ("module.batches", "Batches"),
    ("module.clients", "Clients"),
    ("module.lab_tests", "Lab Tests"),
    ("module.microorganism_id", "Microorganisms"),
    ("module.dna_extraction", "DNA Extraction"),
    ("module.pcr", "PCR / qPCR"),
    ("module.qc_approval", "QC Queue"),
    ("module.reports", "Reports"),
    ("module.reminders", "Reminders"),
    ("module.notifications", "Notifications"),
    ("module.audit_trail", "Audit Trail"),
    ("module.recycle_bin", "Recycle Bin"),
    ("module.users", "User Directory"),
    ("module.settings", "Settings Hub"),
    ("module.customer_portal", "Customer Portal"),
]


def default_role_modules():
    """All modules off by default for custom roles."""
    return {key: False for key, _ in DEFAULT_MODULE_KEYS}


class Role(models.Model):
    """Dynamic role with per-module access. System roles are seeded and non-deletable."""

    class LabScope(models.TextChoices):
        LABORATORY = "LABORATORY", "Own laboratory only"
        GLOBAL = "GLOBAL", "All laboratories"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, unique=True, db_index=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_system = models.BooleanField(
        default=False,
        help_text="Built-in role; code cannot be changed and role cannot be deleted.",
    )
    is_active = models.BooleanField(default=True)
    lab_scope = models.CharField(
        max_length=20,
        choices=LabScope.choices,
        default=LabScope.LABORATORY,
    )
    modules = models.JSONField(default=default_role_modules)
    can_manage_users = models.BooleanField(default=False)
    can_manage_roles = models.BooleanField(default=False)
    can_manage_settings = models.BooleanField(default=False)
    can_approve_qc = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "accounts_role"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.code:
            self.code = self.code.strip().upper().replace(" ", "_")
        base = default_role_modules()
        current = self.modules or {}
        base.update({k: bool(current.get(k, False)) for k in base})
        self.modules = base
        super().save(*args, **kwargs)

    def has_module(self, key: str) -> bool:
        if not self.is_active:
            return False
        return bool((self.modules or {}).get(key, False))

    def is_global_scope(self) -> bool:
        return self.lab_scope == self.LabScope.GLOBAL

    @classmethod
    def seed_defaults(cls):
        """Idempotent seed for the built-in roles."""
        presets = [
            {
                "code": "TECHNICIAN",
                "name": "Lab Technician",
                "lab_scope": cls.LabScope.LABORATORY,
                "modules": {
                    "module.samples": True,
                    "module.batches": True,
                    "module.clients": True,
                    "module.lab_tests": True,
                    "module.dna_extraction": True,
                    "module.pcr": True,
                    "module.reminders": True,
                    "module.notifications": True,
                },
                "can_approve_qc": False,
                "can_manage_users": False,
                "can_manage_roles": False,
                "can_manage_settings": False,
            },
            {
                "code": "ANALYST",
                "name": "Analyst",
                "lab_scope": cls.LabScope.LABORATORY,
                "modules": {
                    "module.samples": True,
                    "module.batches": True,
                    "module.clients": True,
                    "module.lab_tests": True,
                    "module.microorganism_id": True,
                    "module.dna_extraction": True,
                    "module.pcr": True,
                    "module.reports": True,
                    "module.reminders": True,
                    "module.notifications": True,
                },
                "can_approve_qc": False,
                "can_manage_users": False,
                "can_manage_roles": False,
                "can_manage_settings": False,
            },
            {
                "code": "QC_OFFICER",
                "name": "QC Officer",
                "lab_scope": cls.LabScope.LABORATORY,
                "modules": {
                    "module.samples": True,
                    "module.lab_tests": True,
                    "module.pcr": True,
                    "module.qc_approval": True,
                    "module.reports": True,
                    "module.reminders": True,
                    "module.notifications": True,
                    "module.audit_trail": True,
                },
                "can_approve_qc": True,
                "can_manage_users": False,
                "can_manage_roles": False,
                "can_manage_settings": False,
            },
            {
                "code": "FOOD_SAFETY_OFFICER",
                "name": "Food Safety Officer",
                "lab_scope": cls.LabScope.GLOBAL,
                "modules": {
                    "module.samples": True,
                    "module.batches": True,
                    "module.clients": True,
                    "module.lab_tests": True,
                    "module.microorganism_id": True,
                    "module.dna_extraction": True,
                    "module.pcr": True,
                    "module.qc_approval": True,
                    "module.reports": True,
                    "module.reminders": True,
                    "module.notifications": True,
                    "module.audit_trail": True,
                    "module.recycle_bin": True,
                },
                "can_approve_qc": True,
                "can_manage_users": False,
                "can_manage_roles": False,
                "can_manage_settings": False,
            },
            {
                "code": "ADMIN",
                "name": "Administrator",
                "lab_scope": cls.LabScope.GLOBAL,
                "modules": {key: True for key, _ in DEFAULT_MODULE_KEYS},
                "can_approve_qc": True,
                "can_manage_users": True,
                "can_manage_roles": True,
                "can_manage_settings": True,
            },
        ]
        for p in presets:
            mods = default_role_modules()
            mods.update(p["modules"])
            obj, created = cls.objects.get_or_create(
                code=p["code"],
                defaults={
                    "name": p["name"],
                    "is_system": True,
                    "is_active": True,
                    "lab_scope": p["lab_scope"],
                    "modules": mods,
                    "can_approve_qc": p["can_approve_qc"],
                    "can_manage_users": p["can_manage_users"],
                    "can_manage_roles": p["can_manage_roles"],
                    "can_manage_settings": p["can_manage_settings"],
                },
            )
            if not created and obj.is_system:
                obj.name = p["name"]
                obj.lab_scope = p["lab_scope"]
                obj.is_system = True
                obj.save(update_fields=["name", "lab_scope", "is_system", "updated_at"])


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
        max_length=50,
        default="TECHNICIAN",
        db_index=True,
        help_text="Role code from accounts.Role",
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

    def get_role_obj(self):
        if not hasattr(self, "_role_cache"):
            try:
                self._role_cache = Role.objects.filter(code=self.role, is_active=True).first()
            except Exception:
                self._role_cache = None
        return self._role_cache

    def get_role_display(self):
        role_obj = self.get_role_obj()
        if role_obj:
            return role_obj.name
        try:
            return self.Role(self.role).label
        except ValueError:
            return self.role or "—"

    def has_module(self, key: str) -> bool:
        if self.is_superuser:
            return True
        role_obj = self.get_role_obj()
        if role_obj:
            return role_obj.has_module(key)
        if self.role == "ADMIN":
            return True
        return False

    def has_role_perm(self, perm: str) -> bool:
        """perm: manage_users | manage_roles | manage_settings | approve_qc | global_scope"""
        if self.is_superuser:
            return True
        role_obj = self.get_role_obj()
        if not role_obj:
            if self.role == "ADMIN":
                return True
            if perm == "global_scope" and self.role in ("ADMIN", "FOOD_SAFETY_OFFICER"):
                return True
            if perm == "approve_qc" and self.role in ("QC_OFFICER", "FOOD_SAFETY_OFFICER", "ADMIN"):
                return True
            return False
        mapping = {
            "manage_users": role_obj.can_manage_users,
            "manage_roles": role_obj.can_manage_roles,
            "manage_settings": role_obj.can_manage_settings,
            "approve_qc": role_obj.can_approve_qc,
            "global_scope": role_obj.is_global_scope(),
        }
        return bool(mapping.get(perm, False))

    @property
    def must_setup_2fa(self):
        roles_requiring_2fa = getattr(settings, "ROLES_REQUIRING_2FA", [])
        if self.role in roles_requiring_2fa or self.requires_2fa:
            try:
                from django_otp import devices_for_user
                return not any(d.confirmed for d in devices_for_user(self, confirmed=True))
            except ImportError:
                return False
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