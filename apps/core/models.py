import hashlib
import uuid
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from apps.accounts.validators import SecureFileUploadValidator, randomize_upload_filename


# ═══════════════════════════════════════════════════════════════
# GEOGRAPHY & INFRASTRUCTURE
# ═══════════════════════════════════════════════════════════════

class Country(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, unique=True)
    iso2 = models.CharField("ISO 3166-1 alpha-2", max_length=2, unique=True)
    iso3 = models.CharField("ISO 3166-1 alpha-3", max_length=3, unique=True)
    dial_code = models.CharField(max_length=10, blank=True)
    currency = models.CharField(max_length=10, blank=True)
    timezone = models.CharField(max_length=50, default="UTC")
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "core_country"
        ordering = ["name"]
        verbose_name_plural = "Countries"

    def __str__(self):
        return f"{self.name} ({self.iso2})"

    def clean(self):
        self.iso2 = self.iso2.upper()
        self.iso3 = self.iso3.upper()


class Region(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name="regions")
    code = models.CharField(max_length=10)
    name = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "core_region"
        ordering = ["name"]
        unique_together = [("country", "code")]

    def __str__(self):
        return f"{self.name} ({self.code})"


class Laboratory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    country = models.ForeignKey(Country, on_delete=models.PROTECT, related_name="laboratories")
    region = models.ForeignKey(Region, on_delete=models.SET_NULL, null=True, blank=True, related_name="laboratories")
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        db_table = "core_laboratory"
        ordering = ["name"]
        verbose_name_plural = "Laboratories"

    def __str__(self):
        return self.name


# ═══════════════════════════════════════════════════════════════
# SYSTEM CONFIGURATION
# ═══════════════════════════════════════════════════════════════

class SystemSetting(models.Model):
    """Singleton system configurations stored as JSONB blobs."""
    id = models.IntegerField(primary_key=True, default=1)
    organization_name = models.CharField(max_length=255, default="ILIMS Lab Corporation")
    numbering_settings = models.JSONField(default=dict)
    sla_settings = models.JSONField(default=dict)
    security_settings = models.JSONField(default=dict)
    print_settings = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "core_system_setting"

    def __str__(self):
        return "System Settings"

    def save(self, *args, **kwargs):
        self.id = 1
        super().save(*args, **kwargs)
        cache.set("ilims_system_settings", self, 3600)

    @classmethod
    def get_settings(cls):
        cached = cache.get("ilims_system_settings")
        if cached:
            return cached
        obj, _ = cls.objects.get_or_create(
            id=1,
            defaults={
                "numbering_settings": {
                    "client_prefix": "CUS", "sample_prefix": "FS",
                    "batch_prefix": "BAT", "report_prefix": "RPT",
                    "dna_prefix": "DNA", "test_prefix": "TST",
                    "qc_prefix": "QC",
                    "separator": "-", "padding": 5, "reset_yearly": True,
                },
                "sla_settings": {
                    "tat_normal_days": 5, "tat_urgent_days": 2, "working_days_only": True,
                },
                "security_settings": {
                    "force_otp_all": False, "session_idle_timeout": 1800, "password_expiry_days": 90,
                },
                "print_settings": {
                    "receipt_size": "A5",
                    "receipt_header": "Laboratory Sample Receipt",
                    "receipt_footer": "Please retain this receipt for report collection.",
                }
            }
        )
        cache.set("ilims_system_settings", obj, 3600)
        return obj


class IdSequence(models.Model):
    """Database-level sequence generator, race-safe."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=50)
    scope = models.CharField(max_length=100, default="GLOBAL")
    year = models.IntegerField()
    last_value = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "core_id_sequence"
        unique_together = [("kind", "scope", "year")]


class FeatureFlag(models.Model):
    key = models.CharField(max_length=100, unique=True, db_index=True)
    label = models.CharField(max_length=200)
    group = models.CharField(max_length=100, default="Modules")
    description = models.TextField(blank=True)
    enabled = models.BooleanField(default=True)
    roles = models.JSONField(default=list)
    is_core = models.BooleanField(default=False)

    class Meta:
        db_table = "core_feature_flag"
        ordering = ["group", "label"]

    def __str__(self):
        return self.label

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        cache.delete(f"feature_flag_{self.key}")


# ═══════════════════════════════════════════════════════════════
# DYNAMIC DICTIONARIES
# ═══════════════════════════════════════════════════════════════

class ProductCategory(models.Model):
    """E.g. Food, Water, Swab, Environmental."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "dict_product_category"
        ordering = ["name"]
        verbose_name_plural = "Product Categories"

    def save(self, *args, **kwargs):
        if self.name:
            self.name = self.name.strip().title()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class ProductType(models.Model):
    """E.g. Dairy, Raw Meat, Beverage, Ready-To-Eat."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    category = models.ForeignKey(ProductCategory, on_delete=models.PROTECT, related_name="types", null=True, blank=True)
    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "dict_product_type"
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if self.name:
            self.name = self.name.strip().title()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class WorkflowStatus(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50, unique=True)
    color = models.CharField(max_length=20, default="info", help_text="ok, warn, danger, info, brand")
    order = models.PositiveIntegerField(default=100)
    is_terminal = models.BooleanField(default=False)
    is_locked = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "dict_workflow_status"
        ordering = ["order", "name"]
        verbose_name_plural = "Workflow Statuses"

    def save(self, *args, **kwargs):
        if self.name:
            self.name = self.name.strip().title()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class LabMethod(models.Model):
    CATEGORY_CHOICES = [
        ("DNA_EXTRACTION", "DNA Extraction"),
        ("TEST", "PCR / qPCR"),
        ("SEQUENCING", "Sequencing"),
        ("CULTURE", "Microbiology Culture"),
        ("CHEMICAL", "Chemical Analysis"),
        ("ALLERGEN", "Allergen Testing"),
        ("HEAVY_METAL", "Heavy Metal Testing"),
        ("PESTICIDE", "Pesticide Residue"),
        ("SENSORY", "Sensory Evaluation"),
        ("GENERAL", "General Diagnostic Test"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=150, unique=True)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default="GENERAL")
    allowed_categories = models.ManyToManyField("ProductCategory", blank=True, related_name="lab_methods")
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "dict_lab_method"
        ordering = ["category", "name"]

    def save(self, *args, **kwargs):
        if self.name:
            self.name = self.name.strip().upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class RiskLevel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50, unique=True)
    color = models.CharField(max_length=20, default="warn")
    severity = models.PositiveIntegerField(default=1, help_text="1=Low, 5=Critical")
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "dict_risk_level"
        ordering = ["severity"]

    def __str__(self):
        return self.name


# ═══════════════════════════════════════════════════════════════
# CODE GENERATOR & FLAG HELPER
# ═══════════════════════════════════════════════════════════════

def next_code(kind, country=None, region=None):
    settings_obj = SystemSetting.get_settings()
    opts = settings_obj.numbering_settings

    prefix_map = {
        "CLIENT": opts.get("client_prefix", "CUS"),
        "SAMPLE": opts.get("sample_prefix", "FS"),
        "BATCH": opts.get("batch_prefix", "BAT"),
        "REPORT": opts.get("report_prefix", "RPT"),
        "DNA": opts.get("dna_prefix", "DNA"),
        "TEST": opts.get("test_prefix", "TST"),
        "QC": opts.get("qc_prefix", "QC"),
    }
    prefix = prefix_map.get(kind, "DOC")
    sep = opts.get("separator", "-")
    padding = int(opts.get("padding", 5))
    reset_yearly = opts.get("reset_yearly", True)

    now = timezone.now()
    year = now.year if reset_yearly else 1900

    scope_parts = []
    if country:
        scope_parts.append(country.iso2.upper())
    if region:
        scope_parts.append(region.code.upper())
    scope = "-".join(scope_parts) if scope_parts else "GLOBAL"

    with transaction.atomic():
        seq, _ = IdSequence.objects.select_for_update().get_or_create(
            kind=kind, scope=scope, year=year, defaults={"last_value": 0}
        )
        seq.last_value += 1
        seq.save(update_fields=["last_value"])
        counter = seq.last_value

    num_str = str(counter).zfill(padding)
    code_parts = [prefix]
    if scope != "GLOBAL":
        code_parts.extend(scope_parts)
    if reset_yearly:
        code_parts.append(str(now.year))
    code_parts.append(num_str)
    return sep.join(code_parts)


def flag_enabled(key):
    cache_key = f"feature_flag_{key}"
    val = cache.get(cache_key)
    if val is not None:
        return val
    try:
        flag = FeatureFlag.objects.get(key=key)
        enabled = flag.enabled
    except FeatureFlag.DoesNotExist:
        enabled = True
    cache.set(cache_key, enabled, 300)
    return enabled


# ═══════════════════════════════════════════════════════════════
# AUDIT LOG
# ═══════════════════════════════════════════════════════════════

class AuditLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    timestamp = models.DateTimeField(db_index=True)
    user = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)  # <-- New Field
    action = models.CharField(max_length=50)
    model_name = models.CharField(max_length=100, db_index=True)
    record_id = models.CharField(max_length=100, db_index=True)
    changes = models.JSONField(default=dict)
    previous_hash = models.CharField(max_length=64)
    hash = models.CharField(max_length=64, unique=True)

    class Meta:
        db_table = "core_audit_log"
        ordering = ["-timestamp"]

# ═══════════════════════════════════════════════════════════════
# CLIENT & SPECIMEN BATCH MODELS
# ═══════════════════════════════════════════════════════════════

class Client(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, unique=True, db_index=True)
    name = models.CharField(max_length=255)
    contact_person = models.CharField(max_length=200, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    country = models.ForeignKey(Country, on_delete=models.PROTECT)
    region = models.ForeignKey(Region, on_delete=models.SET_NULL, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "core_client"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["phone"],
                condition=models.Q(phone__isnull=False) & ~models.Q(phone=""),
                name="unique_client_phone_nonempty",
            ),
            models.UniqueConstraint(
                fields=["address"],
                condition=models.Q(address__isnull=False) & ~models.Q(address=""),
                name="unique_client_address_nonempty",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.name:
            self.name = self.name.strip().title()
        if self.contact_person:
            self.contact_person = self.contact_person.strip().title()
        if self.phone is not None and not str(self.phone).strip():
            self.phone = None
        if self.address is not None and not str(self.address).strip():
            self.address = None
        super().save(*args, **kwargs)

    def can_be_deleted(self):
        return not self.samples.filter(is_deleted=False).exists()

    def soft_delete(self):
        if not self.can_be_deleted():
            raise ValidationError("Cannot delete client with active samples.")
        self.is_deleted = True
        self.is_active = False
        self.save(update_fields=["is_deleted", "is_active"])

    def __str__(self):
        return self.name


class FoodBatch(models.Model):
    """Product batch grouping for traceability."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, unique=True, db_index=True)
    batch_number = models.CharField("Batch / Lot Number", max_length=100, default="")
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="batches")
    product_name = models.CharField("Product Name", max_length=200, blank=True)
    production_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    quantity = models.PositiveIntegerField("Quantity (units)", null=True, blank=True)
    storage_condition = models.CharField(
        max_length=50,
        choices=[
            ("AMBIENT", "Ambient"),
            ("REFRIGERATED", "Refrigerated"),
            ("FROZEN", "Frozen"),
        ],
        default="AMBIENT",
    )
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "core_food_batch"
        ordering = ["-created_at"]
        verbose_name_plural = "Food Batches"

    def __str__(self):
        return f"{self.code} ({self.batch_number})"

    def sample_count(self):
        return self.samples.filter(is_deleted=False).count()

    def soft_delete(self):
        if self.samples.filter(is_deleted=False).exists():
            raise ValidationError("Cannot delete batch with active samples.")
        self.is_deleted = True
        self.is_active = False
        self.save(update_fields=["is_deleted", "is_active"])


# ═══════════════════════════════════════════════════════════════
# SAMPLE (INTAKE SPECIMEN)
# ═══════════════════════════════════════════════════════════════

class Sample(models.Model):
    """A Sample is any specimen or food product submitted for testing."""

    class TestCategory(models.TextChoices):
        DNA_EXTRACTION = "DNA_EXTRACTION", "DNA Extraction"
        PCR_QPCR = "PCR_QPCR", "PCR / qPCR"
        SEQUENCING = "SEQUENCING", "Sequencing"
        CULTURE = "CULTURE", "Microbiology Culture"
        CHEMICAL = "CHEMICAL", "Chemical Analysis"
        ALLERGEN = "ALLERGEN", "Allergen Testing"
        HEAVY_METAL = "HEAVY_METAL", "Heavy Metal Testing"
        PESTICIDE = "PESTICIDE", "Pesticide Residue"
        SENSORY = "SENSORY", "Sensory Evaluation"
        GENERAL = "GENERAL", "General Diagnostic Test"

    MolecularType = TestCategory  # Backward compatibility alias

    class WorkflowState(models.TextChoices):
        RECEIVED = "RECEIVED", "Sample Received"
        TESTING = "TESTING", "Testing In Progress"
        ANALYSIS = "ANALYSIS", "Analysis"
        REPORT_PREP = "REPORT_PREP", "Report Preparation"
        REPORT_READY = "REPORT_READY", "Report Ready"
        REPORT_SENT = "REPORT_SENT", "Report Sent"
        REJECTED = "REJECTED", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, unique=True, db_index=True)
    tracking_code = models.CharField(
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text="Secure public tracking token for the customer portal.",
    )
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="samples")
    laboratory = models.ForeignKey(
        Laboratory,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="samples",
        help_text="The laboratory facility managing this sample.",
    )

    product_name = models.CharField(max_length=200)
    product_category = models.ForeignKey(ProductCategory, on_delete=models.PROTECT, null=True, blank=True, related_name="samples")
    product_type = models.ForeignKey(ProductType, on_delete=models.PROTECT, null=True, blank=True, related_name="samples")

    molecular_type = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Legacy test type field.",
    )

    requested_test = models.ForeignKey(LabMethod, on_delete=models.PROTECT, null=True, blank=True, related_name="requested_samples")
    batch = models.ForeignKey(FoodBatch, on_delete=models.SET_NULL, null=True, blank=True, related_name="samples")

    priority = models.CharField(max_length=20, choices=[("NORMAL", "Normal"), ("URGENT", "Urgent")], default="NORMAL")
    storage_condition = models.CharField(
        max_length=50,
        choices=[
            ("AMBIENT", "Ambient (Room Temp)"),
            ("REFRIGERATED", "Refrigerated (2-8°C)"),
            ("FROZEN", "Frozen (-20°C or below)")
        ],
        default="AMBIENT"
    )
    due_date = models.DateField(null=True, blank=True)
    received_date = models.DateField(default=timezone.now)
    production_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)

    workflow_state = models.CharField(max_length=20, choices=WorkflowState.choices, default=WorkflowState.RECEIVED, db_index=True)
    status = models.ForeignKey(WorkflowStatus, on_delete=models.PROTECT, null=True, blank=True, related_name="samples")
    assigned_to = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True)
    remarks = models.TextField(blank=True)

    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "core_sample"
        ordering = ["-created_at"]

    def soft_delete(self):
        self.is_deleted = True
        self.save(update_fields=["is_deleted"])

    def is_locked_for_new_tests(self):
        locked_states = {"REPORT_PREP", "REPORT_READY", "REPORT_SENT", "REJECTED"}
        return self.workflow_state in locked_states

    def state_color(self):
        colors = {
            "RECEIVED": "info",
            "TESTING": "warn",
            "ANALYSIS": "warn",
            "REPORT_PREP": "brand",
            "REPORT_READY": "ok",
            "REPORT_SENT": "ok",
            "REJECTED": "danger",
        }
        return colors.get(self.workflow_state, "info")

    def generate_tracking_code(self):
        """Generate a secure, unique tracking code for the customer portal."""
        phone = self.client.phone if (self.client_id and self.client and self.client.phone) else "UNKNOWN"
        raw = f"{self.pk}:{phone}:{settings.SECRET_KEY}"
        hash_hex = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16].upper()
        self.tracking_code = f"ILIMS-{hash_hex[:8]}-{hash_hex[8:]}"
        self.save(update_fields=["tracking_code"])
        return self.tracking_code

    @transaction.atomic
    def advance(self, user, to_state, notes=""):
        """Transition workflow_state, write event log, audit log, and auto-create QC record."""
        if hasattr(to_state, "name"):
            new_state = to_state.name.upper().replace(" ", "_")
        else:
            new_state = str(to_state).upper().strip()

        state_map = {
            "SAMPLE_RECEIVED": "RECEIVED",
            "TESTING_IN_PROGRESS": "TESTING",
            "REPORT_PREPARATION": "REPORT_PREP",
        }
        new_state = state_map.get(new_state, new_state)

        if new_state not in dict(self.WorkflowState.choices):
            return

        if self.workflow_state == new_state:
            return

        old_display = self.get_workflow_state_display()
        self.workflow_state = new_state
        self.save(update_fields=["workflow_state", "updated_at"])
        new_display = self.get_workflow_state_display()

        # Write timeline event
        SampleEvent.objects.create(
            sample=self,
            from_status=old_display,
            to_status=new_display,
            changed_by=user if getattr(user, "is_authenticated", False) else None,
            notes=notes,
        )

        # Write audit log
        from apps.core.audit import log_audit
        log_audit(
            user=user,
            action="STATUS_CHANGE",
            instance=self,
            changes={
                "workflow_state": {"old": old_display, "new": new_display},
                "notes": {"old": "", "new": notes},
            },
        )

        # Auto-create QC record when sample reaches Report Preparation
        if new_state == "REPORT_PREP":
            existing_qc = QcRecord.objects.filter(
                sample=self, decision="PENDING"
            ).exists()
            if not existing_qc:
                qc_code = next_code("QC", self.client.country if self.client_id else None)
                QcRecord.objects.create(
                    code=qc_code,
                    sample=self,
                    test=None,
                    decision=QcRecord.Decision.PENDING,
                    safety_class=QcRecord.SafetyClass.NOT_APPLICABLE,
                )

                # Push notification to all QC officers
                try:
                    from apps.core.notifications import push_to_role
                    push_to_role(
                        "QC_OFFICER",
                        title=f"🔔 QC Review Required: {self.code}",
                        message=f"Sample {self.code} ({self.product_name}) is ready for QC verification.",
                        level="info",
                        url="/qc/",
                    )
                except Exception:
                    pass

    def __str__(self):
        return self.code


class SampleEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sample = models.ForeignKey(Sample, on_delete=models.CASCADE, related_name="events")
    from_status = models.CharField(max_length=100, blank=True)
    to_status = models.CharField(max_length=100)
    changed_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "core_sample_event"
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.sample.code}: {self.from_status} → {self.to_status}"


# ═══════════════════════════════════════════════════════════════
# DIRECT SAMPLE TEST ATTACHMENT MODEL
# ═══════════════════════════════════════════════════════════════

class SampleTest(models.Model):
    """
    Direct test attached to a sample. Supports any test type (Dengue, Culture, Chemical, etc.)
    with qualitative/quantitative outcomes and uploaded lab report attachments.
    """

    class Outcome(models.TextChoices):
        POSITIVE = "POSITIVE", "Positive / Detected"
        NEGATIVE = "NEGATIVE", "Negative / Not Detected"
        NORMAL = "NORMAL", "Normal / Within Limits"
        ABNORMAL = "ABNORMAL", "Abnormal / Exceeds Limits"
        INCONCLUSIVE = "INCONCLUSIVE", "Inconclusive"
        OTHER = "OTHER", "See Notes / Attachment"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, unique=True, db_index=True)
    sample = models.ForeignKey(Sample, on_delete=models.CASCADE, related_name="attached_tests")
    test_type = models.ForeignKey(LabMethod, on_delete=models.PROTECT, related_name="sample_test_runs")
    result_outcome = models.CharField(max_length=20, choices=Outcome.choices, default=Outcome.NEGATIVE, db_index=True)
    result_value = models.CharField("Quantitative Value", max_length=255, blank=True, help_text="e.g. 'Titer 1:160', '1500 CFU/g', '5.2 ppm', 'Reactive'")
    test_date = models.DateField(default=timezone.now)
    operator = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="conducted_sample_tests")
    attachment = models.FileField(
        upload_to=randomize_upload_filename,
        blank=True,
        null=True,
        validators=[
            SecureFileUploadValidator(
                allowed_extensions=["pdf", "png", "jpg", "jpeg", "webp"],
                allowed_mimetypes=["application/pdf", "image/png", "image/jpeg", "image/pjpeg", "image/webp"],
                max_size_mb=10,
            )
        ],
        help_text="Upload scanned bench sheet, strip photo, or instrument report.",
    )
    notes = models.TextField(blank=True)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "core_sample_test"
        ordering = ["-test_date", "-created_at"]

    def __str__(self):
        return f"{self.code} · {self.test_type.name}: {self.get_result_outcome_display()}"

    def outcome_color(self):
        colors = {
            "POSITIVE": "danger",
            "ABNORMAL": "danger",
            "NEGATIVE": "ok",
            "NORMAL": "ok",
            "INCONCLUSIVE": "warn",
            "OTHER": "info",
        }
        return colors.get(self.result_outcome, "info")

    def soft_delete(self):
        self.is_deleted = True
        self.save(update_fields=["is_deleted"])


# ═══════════════════════════════════════════════════════════════
# GENERIC LABORATORY TESTS
# ═══════════════════════════════════════════════════════════════

class LabTest(models.Model):
    """
    Generic test record for non-molecular analyses:
    Culture, Chemical, Allergen, Heavy Metal, Pesticide, Sensory.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, unique=True, db_index=True)
    sample = models.ForeignKey(Sample, on_delete=models.PROTECT, related_name="lab_tests")
    test_type = models.ForeignKey(
        LabMethod, on_delete=models.PROTECT, related_name="lab_test_runs",
        null=True, blank=True,
    )
    target = models.ForeignKey("Microorganism", on_delete=models.PROTECT, related_name="lab_test_detections", null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    method_name = models.CharField(max_length=200, blank=True)
    run_date = models.DateField(default=timezone.now)
    operator = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="lab_tests")
    instrument = models.CharField(max_length=200, blank=True)
    parameters = models.JSONField(default=dict, blank=True)
    detection = models.CharField(
        max_length=20,
        choices=[
            ("DETECTED", "Detected"),
            ("NOT_DETECTED", "Not Detected"),
            ("INCONCLUSIVE", "Inconclusive"),
            ("WITHIN_LIMITS", "Within Limits"),
            ("EXCEEDS_LIMITS", "Exceeds Limits"),
            ("NOT_APPLICABLE", "Not Applicable"),
        ],
        default="NOT_APPLICABLE",
    )
    result_value = models.CharField(max_length=200, blank=True)
    result_unit = models.CharField(max_length=50, blank=True)
    limit_value = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "core_lab_test"
        ordering = ["-run_date", "-created_at"]

    def __str__(self):
        return self.code

    def soft_delete(self):
        self.is_deleted = True
        self.save(update_fields=["is_deleted"])

    @property
    def category_display(self):
        if self.test_type:
            return self.test_type.get_category_display()
        return "General"


# ═══════════════════════════════════════════════════════════════
# MOLECULAR MODELS
# ═══════════════════════════════════════════════════════════════

class Microorganism(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, unique=True)
    scientific_name = models.CharField(max_length=255, blank=True)
    code = models.CharField(max_length=30, unique=True)
    category = models.ForeignKey(ProductCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name="microorganisms")
    risk_level = models.ForeignKey(RiskLevel, on_delete=models.SET_NULL, null=True, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "core_microorganism"
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if self.name:
            self.name = self.name.strip()
        if self.code:
            self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    def can_be_deleted(self):
        return not self.result_rows.exists() and not self.tests.exists()

    def soft_delete(self):
        if not self.can_be_deleted():
            raise ValidationError("Cannot delete microorganism used in tests.")
        self.is_deleted = True
        self.is_active = False
        self.save(update_fields=["is_deleted", "is_active"])

    def __str__(self):
        return self.name


class DnaExtraction(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, unique=True, db_index=True)
    sample = models.ForeignKey(Sample, on_delete=models.PROTECT, related_name="dna_extractions")
    method = models.ForeignKey(
        LabMethod, on_delete=models.PROTECT, related_name="dna_extractions_used",
        null=True, blank=True
    )
    kit_name = models.CharField(max_length=200, blank=True)
    extraction_date = models.DateField(default=timezone.now)
    operator = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="dna_extractions")
    concentration_ng_ul = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    purity_260_280 = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True)
    purity_260_230 = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True)
    volume_ul = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    status = models.ForeignKey(WorkflowStatus, on_delete=models.PROTECT, null=True, blank=True, related_name="dna_extractions")
    notes = models.TextField(blank=True)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "core_dna_extraction"
        ordering = ["-extraction_date", "-created_at"]

    def soft_delete(self):
        self.is_deleted = True
        self.save(update_fields=["is_deleted"])

    def __str__(self):
        return self.code


class MolecularTest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, unique=True, db_index=True)
    sample = models.ForeignKey(Sample, on_delete=models.PROTECT, related_name="molecular_tests")
    dna_extraction = models.ForeignKey(DnaExtraction, on_delete=models.SET_NULL, null=True, blank=True, related_name="tests")
    test_type = models.ForeignKey(
        LabMethod, on_delete=models.PROTECT, related_name="tests_used",
        null=True, blank=True
    )
    target = models.ForeignKey(Microorganism, on_delete=models.PROTECT, related_name="tests", null=True, blank=True)
    assay_name = models.CharField(max_length=200, blank=True)
    run_date = models.DateField(default=timezone.now)
    operator = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="molecular_tests")
    instrument = models.CharField(max_length=200, blank=True)
    status = models.ForeignKey(WorkflowStatus, on_delete=models.PROTECT, null=True, blank=True, related_name="molecular_tests")
    ct_value = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    ct_cutoff = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    slope = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    r_squared = models.DecimalField(max_digits=6, decimal_places=4, null=True, blank=True)
    sequence_id = models.CharField(max_length=100, blank=True)
    read_length = models.PositiveIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "core_molecular_test"
        ordering = ["-run_date", "-created_at"]

    def soft_delete(self):
        self.is_deleted = True
        self.save(update_fields=["is_deleted"])

    @property
    def detection_summary(self):
        results = self.results.filter(is_deleted=False)
        if not results.exists():
            return "No results"
        if results.filter(detection="DETECTED").exists():
            return "Detected"
        if results.filter(detection="INCONCLUSIVE").exists():
            return "Inconclusive"
        return "Not detected"

    def __str__(self):
        return self.code


class TestResult(models.Model):
    class Detection(models.TextChoices):
        DETECTED = "DETECTED", "Detected"
        NOT_DETECTED = "NOT_DETECTED", "Not Detected"
        INCONCLUSIVE = "INCONCLUSIVE", "Inconclusive"
        INVALID = "INVALID", "Invalid"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    test = models.ForeignKey(MolecularTest, on_delete=models.CASCADE, related_name="results")
    microorganism = models.ForeignKey(Microorganism, on_delete=models.PROTECT, related_name="result_rows")
    detection = models.CharField(max_length=20, choices=Detection.choices)
    ct_value = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    gene_target = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "core_test_result"
        ordering = ["microorganism__name"]

    def __str__(self):
        return f"{self.microorganism.code}: {self.detection}"


# ═══════════════════════════════════════════════════════════════
# QUALITY CONTROL & FOOD-SAFETY CLASSIFICATION
# ═══════════════════════════════════════════════════════════════

class QcRecord(models.Model):
    class Decision(models.TextChoices):
        PENDING = "PENDING", "Pending Review"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        REWORK = "REWORK", "Send Back for Rework"

    class SafetyClass(models.TextChoices):
        SAFE = "SAFE", "Safe"
        UNSAFE = "UNSAFE", "Unsafe"
        NEEDS_REVIEW = "NEEDS_REVIEW", "Needs Further Review"
        NOT_APPLICABLE = "NOT_APPLICABLE", "Not Applicable"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, unique=True, db_index=True)
    test = models.OneToOneField(MolecularTest, on_delete=models.CASCADE, related_name="qc_record", null=True, blank=True)
    sample = models.ForeignKey(Sample, on_delete=models.CASCADE, related_name="qc_records")
    decision = models.CharField(max_length=20, choices=Decision.choices, default=Decision.PENDING, db_index=True)
    safety_class = models.CharField(max_length=20, choices=SafetyClass.choices, default=SafetyClass.NOT_APPLICABLE, db_index=True)
    reviewer = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="qc_reviews")
    review_notes = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "core_qc_record"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["decision", "safety_class"])]

    def __str__(self):
        return f"{self.code} · {self.get_decision_display()}"

    def decision_color(self):
        colors = {"PENDING": "warn", "APPROVED": "ok", "REJECTED": "danger", "REWORK": "info"}
        return colors.get(self.decision, "info")

    def safety_color(self):
        colors = {"SAFE": "ok", "UNSAFE": "danger", "NEEDS_REVIEW": "warn", "NOT_APPLICABLE": "info"}
        return colors.get(self.safety_class, "info")

    def can_be_reviewed_by(self, user):
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        if self.test and self.test.operator_id and self.test.operator_id == user.id:
            return False
        return True

    def four_eyes_blocked_reason(self, user):
        if self.test and self.test.operator_id == user.id and not user.is_superuser:
            return "Four-eyes rule: you cannot approve a test you performed. A different QC officer must review this record."
        return ""


# ═══════════════════════════════════════════════════════════════
# REPORTS & DELIVERABLES
# ═══════════════════════════════════════════════════════════════

class Report(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        GENERATED = "GENERATED", "Generated"
        APPROVED = "APPROVED", "Approved"
        SENT = "SENT", "Sent to Client"
        ARCHIVED = "ARCHIVED", "Archived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, unique=True, db_index=True)
    sample = models.OneToOneField(Sample, on_delete=models.PROTECT, related_name="report")
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="reports")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    safety_class = models.CharField(max_length=20, choices=QcRecord.SafetyClass.choices, default=QcRecord.SafetyClass.NOT_APPLICABLE)
    summary = models.TextField(blank=True)
    generated_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="generated_reports")
    approved_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_reports")
    sent_to = models.EmailField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    pdf_file = models.FileField(
        upload_to=randomize_upload_filename,
        blank=True,
        validators=[
            SecureFileUploadValidator(
                allowed_extensions=["pdf"],
                allowed_mimetypes=["application/pdf"],
                max_size_mb=10,
            )
        ],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "core_report"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.code} · {self.sample.code}"

    def status_color(self):
        colors = {"DRAFT": "info", "GENERATED": "warn", "APPROVED": "ok", "SENT": "brand", "ARCHIVED": "info"}
        return colors.get(self.status, "info")

    def safety_color(self):
        colors = {"SAFE": "ok", "UNSAFE": "danger", "NEEDS_REVIEW": "warn", "NOT_APPLICABLE": "info"}
        return colors.get(self.safety_class, "info")


# ═══════════════════════════════════════════════════════════════
# REMINDERS & NOTIFICATIONS
# ═══════════════════════════════════════════════════════════════

class Reminder(models.Model):
    class Kind(models.TextChoices):
        DUE_SOON = "DUE_SOON", "Due Soon"
        DUE_TODAY = "DUE_TODAY", "Due Today"
        OVERDUE = "OVERDUE", "Overdue"
        QC_PENDING = "QC_PENDING", "QC Pending Review"
        CUSTOM = "CUSTOM", "Custom"

    class Priority(models.TextChoices):
        LOW = "LOW", "Low"
        NORMAL = "NORMAL", "Normal"
        HIGH = "HIGH", "High"
        URGENT = "URGENT", "Urgent"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=20, choices=Kind.choices, db_index=True)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.NORMAL)
    title = models.CharField(max_length=255)
    message = models.TextField(blank=True)
    sample = models.ForeignKey(Sample, on_delete=models.CASCADE, null=True, blank=True, related_name="reminders")
    qc_record = models.ForeignKey(QcRecord, on_delete=models.CASCADE, null=True, blank=True, related_name="reminders")
    assigned_to = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="reminders")
    due_date = models.DateField(db_index=True)
    is_done = models.BooleanField(default=False)
    snoozed_until = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "core_reminder"
        ordering = ["due_date", "-priority"]
        indexes = [
            models.Index(fields=["is_done", "due_date"]),
            models.Index(fields=["assigned_to", "is_done"]),
        ]

    def __str__(self):
        return f"{self.get_kind_display()}: {self.title}"

    def kind_color(self):
        colors = {"DUE_SOON": "warn", "DUE_TODAY": "danger", "OVERDUE": "danger", "QC_PENDING": "info", "CUSTOM": "brand"}
        return colors.get(self.kind, "info")

    def priority_color(self):
        colors = {"LOW": "info", "NORMAL": "brand", "HIGH": "warn", "URGENT": "danger"}
        return colors.get(self.priority, "info")

    @property
    def is_snoozed(self):
        if not self.snoozed_until:
            return False
        return self.snoozed_until > timezone.now().date()

    @property
    def is_effectively_due(self):
        return not self.is_done and not self.is_snoozed


class Notification(models.Model):
    class Level(models.TextChoices):
        INFO = "info", "Info"
        SUCCESS = "success", "Success"
        WARNING = "warning", "Warning"
        ERROR = "error", "Error"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="notifications")
    level = models.CharField(max_length=10, choices=Level.choices, default=Level.INFO)
    title = models.CharField(max_length=255)
    message = models.TextField(blank=True)
    url = models.CharField(max_length=500, blank=True)
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "core_notification"
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.level}] {self.title}"