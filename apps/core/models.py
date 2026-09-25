import uuid
from django.db import models, transaction
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.utils import timezone


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
    print_settings = models.JSONField(default=dict)  # NEW: A5 vs Thermal
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
                    "client_prefix": "CUS", "sample_prefix": "PRD",
                    "batch_prefix": "BAT", "report_prefix": "RPT",
                    "dna_prefix": "DNA", "test_prefix": "TST",
                    "separator": "-", "padding": 5, "reset_yearly": True,
                },
                "sla_settings": {
                    "tat_normal_days": 5, "tat_urgent_days": 2, "working_days_only": True,
                },
                "security_settings": {
                    "force_otp_all": False, "session_idle_timeout": 1800, "password_expiry_days": 90,
                },
                "print_settings": {
                    "receipt_size": "A5",  # A5 or THERMAL
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
# DYNAMIC DICTIONARIES (REPLACES ALL DROPDOWNS)
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
    """E.g. Dairy, Raw Meat, Vegetable, Drinking Water. Belongs to a Category."""
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
    """Dynamic workflow states: Received, Testing, Analysis, Report Ready, etc."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50, unique=True)
    color = models.CharField(max_length=20, default="info", help_text="ok, warn, danger, info, brand")
    order = models.PositiveIntegerField(default=100)
    is_terminal = models.BooleanField(default=False, help_text="Final state (Report Sent, Rejected).")
    is_locked = models.BooleanField(default=False, help_text="Cannot be deleted (system core state).")
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
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    category = models.CharField(max_length=50, default="TEST")  # DNA_EXTRACTION / TEST / SEQUENCING
    allowed_categories = models.ManyToManyField(
        "ProductCategory", blank=True, related_name="lab_methods"
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "dict_lab_method"
        ordering = ["category", "name"]

    def __str__(self):
        return self.name
class RiskLevel(models.Model):
    """Dynamic risk levels for microorganisms."""
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
# CODE GENERATOR
# ═══════════════════════════════════════════════════════════════

def next_code(kind, country=None, region=None):
    settings_obj = SystemSetting.get_settings()
    opts = settings_obj.numbering_settings

    prefix_map = {
        "CLIENT": opts.get("client_prefix", "CUS"),
        "SAMPLE": opts.get("sample_prefix", "PRD"),
        "BATCH": opts.get("batch_prefix", "BAT"),
        "REPORT": opts.get("report_prefix", "RPT"),
        "DNA": opts.get("dna_prefix", "DNA"),
        "TEST": opts.get("test_prefix", "TST"),
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
# BUSINESS MODELS (CLIENT / PRODUCT SAMPLE)
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
        """Cannot be deleted if it has samples linked."""
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
    """Optional product batch grouping."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, unique=True)
    client = models.ForeignKey(Client, on_delete=models.PROTECT)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        db_table = "core_food_batch"

class Sample(models.Model):
    """A Sample is any product submitted for testing (food, water, swab, etc.)."""

    class MolecularType(models.TextChoices):
        DNA_EXTRACTION = "DNA_EXTRACTION", "DNA Extraction"
        PCR_QPCR = "PCR_QPCR", "PCR / qPCR"
        SEQUENCING = "SEQUENCING", "Sequencing"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, unique=True, db_index=True)
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="samples")

    product_name = models.CharField(max_length=200)
    product_category = models.ForeignKey(
        ProductCategory, on_delete=models.PROTECT, null=True, blank=True, related_name="samples"
    )
    product_type = models.ForeignKey(
        ProductType, on_delete=models.PROTECT, null=True, blank=True, related_name="samples"
    )

    molecular_type = models.CharField(
        max_length=20,
        choices=MolecularType.choices,
        default=MolecularType.DNA_EXTRACTION,
        db_index=True,
        help_text="Type of molecular workflow this sample will undergo.",
    )

    requested_test = models.ForeignKey(
        LabMethod, on_delete=models.PROTECT, null=True, blank=True,
        related_name="requested_samples"
    )
    batch = models.ForeignKey(
        FoodBatch, on_delete=models.SET_NULL, null=True, blank=True, related_name="samples"
    )

    priority = models.CharField(
        max_length=20, choices=[("NORMAL", "Normal"), ("URGENT", "Urgent")], default="NORMAL"
    )
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

    # Hardcoded workflow status (no more WorkflowStatus FK dependency for UI)
    class WorkflowState(models.TextChoices):
        RECEIVED = "RECEIVED", "Sample Received"
        TESTING = "TESTING", "Testing In Progress"
        ANALYSIS = "ANALYSIS", "Analysis"
        REPORT_PREP = "REPORT_PREP", "Report Preparation"
        REPORT_READY = "REPORT_READY", "Report Ready"
        REPORT_SENT = "REPORT_SENT", "Report Sent"
        REJECTED = "REJECTED", "Rejected"

    workflow_state = models.CharField(
        max_length=20,
        choices=WorkflowState.choices,
        default=WorkflowState.RECEIVED,
        db_index=True,
    )

    # Kept for backward compat; not used in new UI
    status = models.ForeignKey(
        WorkflowStatus, on_delete=models.PROTECT, null=True, blank=True, related_name="samples"
    )
    assigned_to = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True
    )
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

    @transaction.atomic
    def advance(self, user, to_state, notes=""):
        """Transition workflow_state and write event log + audit log."""
        # Accept either state code or WorkflowStatus instance for backward compat
        if hasattr(to_state, "name"):
            new_state = to_state.name.upper().replace(" ", "_")
        else:
            new_state = str(to_state).upper().strip()

        # Map friendly names to state codes
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

        SampleEvent.objects.create(
            sample=self,
            from_status=old_display,
            to_status=new_display,
            changed_by=user if getattr(user, "is_authenticated", False) else None,
            notes=notes,
        )

        from apps.core.audit import log_audit
        log_audit(
            user=user,
            action="STATUS_CHANGE",
            instance=self,
            changes={"workflow_state": {"old": old_display, "new": new_display}, "notes": {"old": "", "new": notes}}
        )

    def __str__(self):
        return self.code


class SampleEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sample = models.ForeignKey(Sample, on_delete=models.CASCADE, related_name="events")
    from_status = models.CharField(max_length=100, blank=True)
    to_status = models.CharField(max_length=100)
    changed_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True
    )
    notes = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "core_sample_event"
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.sample.code}: {self.from_status} → {self.to_status}"
# ═══════════════════════════════════════════════════════════════
# MOLECULAR MODELS
# ═══════════════════════════════════════════════════════════════

class Microorganism(models.Model):
    """Catalog of pathogens / targets."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, unique=True)
    scientific_name = models.CharField(max_length=255, blank=True)
    code = models.CharField(max_length=30, unique=True)
    category = models.ForeignKey(
        ProductCategory, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="microorganisms",
        help_text="E.g. Bacteria, Virus, Parasite (dynamic dictionary)."
    )
    risk_level = models.ForeignKey(
        RiskLevel, on_delete=models.SET_NULL, null=True, blank=True
    )
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
        limit_choices_to={"category": "DNA_EXTRACTION"}, null=True, blank=True
    )
    kit_name = models.CharField(max_length=200, blank=True)
    extraction_date = models.DateField(default=timezone.now)
    operator = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="dna_extractions"
    )
    concentration_ng_ul = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    purity_260_280 = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True)
    purity_260_230 = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True)
    volume_ul = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    status = models.ForeignKey(
        WorkflowStatus, on_delete=models.PROTECT, null=True, blank=True,
        related_name="dna_extractions"
    )
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
    dna_extraction = models.ForeignKey(
        DnaExtraction, on_delete=models.SET_NULL, null=True, blank=True, related_name="tests"
    )
    test_type = models.ForeignKey(
        LabMethod, on_delete=models.PROTECT, related_name="tests_used",
        limit_choices_to={"category__in": ["TEST", "ASSAY", "SEQUENCING"]},
        null=True, blank=True
    )
    target = models.ForeignKey(
        Microorganism, on_delete=models.PROTECT, related_name="tests", null=True, blank=True
    )
    assay_name = models.CharField(max_length=200, blank=True)
    run_date = models.DateField(default=timezone.now)
    operator = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="molecular_tests"
    )
    instrument = models.CharField(max_length=200, blank=True)
    status = models.ForeignKey(
        WorkflowStatus, on_delete=models.PROTECT, null=True, blank=True,
        related_name="molecular_tests"
    )
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
    microorganism = models.ForeignKey(
        Microorganism, on_delete=models.PROTECT, related_name="result_rows"
    )
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