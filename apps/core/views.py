import uuid
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.accounts.decorators import role_required
from apps.core.forms import CountryForm, LaboratoryForm, RegionForm, SystemSettingsForm
from apps.core.models import (
    AuditLog, Client, Country, DnaExtraction, FeatureFlag, FoodBatch, Laboratory,
    LabMethod, Microorganism, MolecularTest, ProductCategory, ProductType,
    QcRecord, Region, Reminder, RiskLevel, Sample, SampleTest, SystemSetting,
    TestResult, next_code,
)
from apps.core.smart_select import SmartRegistry, smart_search

User = get_user_model()


# ─── DASHBOARD ───

@login_required
def dashboard_view(request):
    """
    Main operations dashboard with real-time KPI statistics,
    pure SVG throughput and pathogen distribution charts,
    and right-hand action cards.
    """
    now = timezone.now()
    today = now.date()
    current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # 1. KPI Counts
    active_samples = Sample.objects.filter(
        is_deleted=False,
        workflow_state__in=["RECEIVED", "TESTING", "ANALYSIS", "REPORT_PREP"],
    ).count()

    testing_count = Sample.objects.filter(
        is_deleted=False,
        workflow_state__in=["TESTING", "ANALYSIS"],
    ).count()

    total_clients = Client.objects.filter(is_deleted=False).count()

    monthly_tests = MolecularTest.objects.filter(
        is_deleted=False, run_date__gte=current_month_start
    ).count()

    # 2. Stacked Side Cards Data
    today_reminders = Reminder.objects.filter(
        is_done=False, due_date=today
    ).select_related("sample", "assigned_to")[:5]

    overdue_samples = Sample.objects.filter(
        is_deleted=False,
        due_date__lt=today,
        workflow_state__in=["RECEIVED", "TESTING", "ANALYSIS", "REPORT_PREP"],
    ).select_related("client")[:5]

    recent_detections = TestResult.objects.filter(
        is_deleted=False,
        detection="DETECTED",
    ).select_related("microorganism", "test", "test__sample")[:5]

    recent_samples = Sample.objects.filter(
        is_deleted=False
    ).select_related("client").order_by("-created_at")[:6]

    # 3. Pure SVG Monthly Throughput Calculation (Last 6 Months)
    monthly_data = []
    max_count = 1
    for i in range(5, -1, -1):
        m_start = (current_month_start - timedelta(days=i * 30)).replace(day=1)
        if m_start.month == 12:
            m_end = m_start.replace(year=m_start.year + 1, month=1)
        else:
            m_end = m_start.replace(month=m_start.month + 1)

        count = Sample.objects.filter(
            is_deleted=False,
            created_at__gte=m_start,
            created_at__lt=m_end,
        ).count()

        if count > max_count:
            max_count = count

        monthly_data.append({
            "month_label": m_start.strftime("%b"),
            "count": count,
        })

    chart_bars = []
    x_offset = 35
    for idx, item in enumerate(monthly_data):
        height = int((item["count"] / max_count) * 100) if max_count else 0
        y = 130 - height
        chart_bars.append({
            "label": item["month_label"],
            "count": item["count"],
            "x": x_offset + (idx * 75),
            "y": y,
            "width": 38,
            "height": max(height, 4),
        })

    # 4. Pathogen Distribution
    total_detections = TestResult.objects.filter(is_deleted=False, detection="DETECTED").count()
    top_pathogens = []
    if total_detections > 0:
        grouped = (
            TestResult.objects.filter(is_deleted=False, detection="DETECTED")
            .values("microorganism__name", "microorganism__code")
            .annotate(count=Count("id"))
            .order_by("-count")[:4]
        )
        for g in grouped:
            pct = int((g["count"] / total_detections) * 100)
            top_pathogens.append({
                "name": g["microorganism__name"],
                "code": g["microorganism__code"],
                "count": g["count"],
                "percent": pct,
            })

    return render(request, "pages/dashboard.html", {
        "page_title": "Operations Dashboard",
        "page_subtitle": "Real-time laboratory workflow, diagnostics & quality metrics",
        "page_icon": "dashboard",
        "stats": {
            "active_samples": active_samples,
            "testing_count": testing_count,
            "total_clients": total_clients,
            "monthly_tests": monthly_tests,
        },
        "chart_bars": chart_bars,
        "max_bar_count": max_count,
        "top_pathogens": top_pathogens,
        "total_detections": total_detections,
        "today_reminders": today_reminders,
        "overdue_samples": overdue_samples,
        "recent_detections": recent_detections,
        "recent_samples": recent_samples,
    })


# ─── THEME TOGGLE ───

@login_required
def theme_toggle_view(request):
    """Toggle between light and dark theme via POST form (no JS required)."""
    if request.method == "POST":
        current = request.COOKIES.get("ilims_theme", "light")
        new_theme = "dark" if current == "light" else "light"
        next_url = request.POST.get("next", request.META.get("HTTP_REFERER", "/"))

        response = HttpResponseRedirect(next_url)
        response.set_cookie(
            "ilims_theme",
            new_theme,
            max_age=365 * 24 * 60 * 60,
            samesite="Strict",
            httponly=False,
        )
        return response

    return render(request, "partials/_theme_toggle.html")


# ─── DOCUMENTATION USER MANUAL ───

@login_required
def documentation_view(request):
    """Render the comprehensive interactive user manual."""
    return render(request, "pages/documentation.html", {
        "page_title": "User Manual",
        "page_subtitle": "Complete feature and operational reference guide",
        "page_icon": "report",
    })


# ─── SETTINGS HUB ───

@login_required
@role_required("ADMIN")
def settings_hub_view(request):
    """Central settings and configuration interface."""
    system_settings = SystemSetting.get_settings()
    countries = Country.objects.all()
    regions = Region.objects.select_related("country").all()
    laboratories = Laboratory.objects.select_related("country", "region").all()
    feature_flags = FeatureFlag.objects.all()

    settings_form = SystemSettingsForm(instance=system_settings)
    country_form = CountryForm()
    region_form = RegionForm()
    laboratory_form = LaboratoryForm()

    active_tab = request.GET.get("tab", "general")

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "save_settings":
            form = SystemSettingsForm(request.POST, instance=system_settings)
            if form.is_valid():
                form.save()
                messages.success(request, "Settings updated successfully.")
                return redirect(reverse("core:settings_hub") + "?tab=general")
            else:
                settings_form = form
                active_tab = "general"

        elif action == "add_country":
            form = CountryForm(request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, "Country added successfully.")
                return redirect(reverse("core:settings_hub") + "?tab=countries")
            else:
                country_form = form
                active_tab = "countries"

        elif action == "add_region":
            form = RegionForm(request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, "Region added successfully.")
                return redirect(reverse("core:settings_hub") + "?tab=regions")
            else:
                region_form = form
                active_tab = "regions"

        elif action == "add_laboratory":
            form = LaboratoryForm(request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, "Laboratory facility registered successfully.")
                return redirect(reverse("core:settings_hub") + "?tab=labs")
            else:
                laboratory_form = form
                active_tab = "labs"

        elif action == "toggle_flag":
            flag_key = request.POST.get("flag_key")
            flag_obj = get_object_or_404(FeatureFlag, key=flag_key)
            if not flag_obj.is_core:
                flag_obj.enabled = not flag_obj.enabled
                flag_obj.save()
                messages.success(request, f"Feature '{flag_obj.label}' updated.")
            return redirect(reverse("core:settings_hub") + "?tab=features")

    preview_country = countries.first()
    preview_region = regions.first()
    code_previews = {
        "client": next_code("CLIENT", preview_country, preview_region),
        "sample": next_code("SAMPLE", preview_country, preview_region),
        "batch": next_code("BATCH", preview_country),
        "report": next_code("REPORT", preview_country, preview_region),
    }

    return render(request, "pages/settings_hub.html", {
        "page_title": "Settings Hub",
        "page_subtitle": "Global configuration, geographical metadata & functional parameters",
        "page_icon": "settings",
        "active_tab": active_tab,
        "settings_form": settings_form,
        "country_form": country_form,
        "region_form": region_form,
        "laboratory_form": laboratory_form,
        "countries": countries,
        "regions": regions,
        "laboratories": laboratories,
        "feature_flags": feature_flags,
        "code_previews": code_previews,
    })


# ─── SMART SELECT ENDPOINTS ───

def _is_uuid(val) -> bool:
    if not val:
        return False
    try:
        uuid.UUID(str(val))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


@login_required
def smart_select_results(request, kind_key):
    """HTMX live search and filter endpoint for SmartSelect fields."""
    kind = SmartRegistry.get(kind_key)
    if kind is None:
        return HttpResponse(status=404)

    field_name = request.GET.get("field", "").strip()
    input_id = request.GET.get("input_id", "").strip()

    query = request.GET.get("q", "").strip()
    if not query and field_name:
        query = (
            request.GET.get(f"{field_name}__text")
            or request.GET.get(field_name)
            or ""
        ).strip()

    if "js:event" in query:
        query = ""

    qs = kind.queryset_fn()

    category_filter = (
        request.GET.get("product_category")
        or request.GET.get("product_category__text")
        or request.GET.get("category")
        or ""
    ).strip()

    molecular_type_filter = (request.GET.get("molecular_type") or "").strip()

    if kind_key == "product_type" and category_filter:
        if _is_uuid(category_filter):
            qs = qs.filter(
                Q(category_id=category_filter) | Q(category__isnull=True)
            )
        else:
            qs = qs.filter(
                Q(category__name__iexact=category_filter)
                | Q(category__name__icontains=category_filter)
                | Q(category__isnull=True)
            )

    if kind_key == "lab_method":
        MOL_MAP = {"DNA_EXTRACTION": "DNA_EXTRACTION", "PCR_QPCR": "TEST", "SEQUENCING": "SEQUENCING"}
        if molecular_type_filter and molecular_type_filter in MOL_MAP:
            qs = qs.filter(category=MOL_MAP[molecular_type_filter])
        elif category_filter:
            try:
                qs = qs.filter(
                    Q(allowed_categories__name__icontains=category_filter)
                    | Q(allowed_categories__isnull=True)
                ).distinct()
            except Exception:
                pass

    if query:
        q_obj = Q()
        for fname in kind.search_fields:
            q_obj |= Q(**{f"{fname}__icontains": query})
        qs = qs.filter(q_obj)

    results = qs[: kind.max_results]

    rendered = [
        {
            "pk": kind.value_fn(obj),
            "display": kind.display_fn(obj),
            "code": kind.code_fn(obj),
            "sub": kind.sub_fn(obj),
        }
        for obj in results
    ]

    return render(request, "partials/_smart_select_results.html", {
        "kind_key": kind_key,
        "kind_label": kind.label,
        "results": rendered,
        "query": query,
        "field_name": field_name,
        "input_id": input_id,
        "picker_url": reverse("core:smart_picker", args=[kind_key]),
    })


@login_required
def smart_picker(request, kind_key):
    """Full-page picker fallback for JS-disabled browsers."""
    kind = SmartRegistry.get(kind_key)
    if kind is None:
        return HttpResponse(status=404)

    query = request.GET.get("q", "").strip()
    field_name = request.GET.get("field", "")
    next_url = request.GET.get("next", "/")

    results = smart_search(kind, query, limit=200)

    return render(request, "pages/smart_picker.html", {
        "page_title": f"Pick a {kind.label}",
        "page_subtitle": f"Choose from {kind.label.lower()} records",
        "page_icon": "search",
        "kind_key": kind_key,
        "kind_label": kind.label,
        "results": [
            {
                "pk": kind.value_fn(o),
                "display": kind.display_fn(o),
                "code": kind.code_fn(o),
                "sub": kind.sub_fn(o),
            }
            for o in results
        ],
        "query": query,
        "field_name": field_name,
        "next_url": next_url,
    })


@login_required
def smart_select_demo(request):
    """Demo page to test SmartSelect fields."""
    from apps.core.widgets import SmartSelect

    prefill = {}
    if request.method == "GET":
        for kind_key in ("country", "region", "laboratory"):
            v = request.GET.get(kind_key, "").strip()
            if v:
                prefill[kind_key] = v

    def build_widget(kind_key):
        widget = SmartSelect(kind_key=kind_key, next_url=request.path)
        return widget.get_context(kind_key, prefill.get(kind_key, ""), {"id": f"id_{kind_key}"})["widget"]

    return render(request, "pages/smart_select_demo.html", {
        "page_title": "SmartSelect Demo",
        "page_subtitle": "Verify type-ahead, picker, and resolver behavior",
        "page_icon": "search",
        "country_widget": build_widget("country"),
        "region_widget": build_widget("region"),
        "laboratory_widget": build_widget("laboratory"),
    })


# ─── RECYCLE BIN & SOFT DELETE ───

@login_required
@role_required("ADMIN")
def recycle_bin_view(request):
    """View and restore or permanently remove soft-deleted records."""
    if request.method == "POST":
        action = request.POST.get("action")
        item_type = request.POST.get("type")
        item_id = request.POST.get("id")

        model_map = {
            "client": Client,
            "sample": Sample,
            "microorganism": Microorganism,
            "dna_extraction": DnaExtraction,
            "molecular_test": MolecularTest,
            "food_batch": FoodBatch,
            "user": User,
            "sample_test": SampleTest,
        }
        model = model_map.get(item_type)
        if model:
            try:
                obj = model.objects.get(pk=item_id)
                if action == "restore":
                    obj.is_deleted = False
                    if hasattr(obj, "is_active"):
                        obj.is_active = True
                    obj.save()
                    messages.success(request, f"Restored {obj}.")
                elif action == "hard_delete":
                    label = str(obj)
                    obj.delete()
                    messages.success(request, f"Permanently removed {label}.")
            except model.DoesNotExist:
                messages.error(request, "Record not found.")
        return redirect("core:recycle_bin")

    clients = Client.objects.filter(is_deleted=True)
    samples = Sample.objects.filter(is_deleted=True).select_related("client")
    microbes = Microorganism.objects.filter(is_deleted=True)
    batches = FoodBatch.objects.filter(is_deleted=True).select_related("client")
    dna = DnaExtraction.objects.filter(is_deleted=True).select_related("sample")
    tests = MolecularTest.objects.filter(is_deleted=True).select_related("sample")

    total_count = (
        clients.count() + samples.count() + microbes.count()
        + batches.count() + dna.count() + tests.count()
    )

    return render(request, "pages/recycle_bin.html", {
        "page_title": "Recycle Bin",
        "page_subtitle": "Restore or permanently remove soft-deleted records",
        "page_icon": "settings",
        "clients": clients,
        "samples": samples,
        "microbes": microbes,
        "batches": batches,
        "dna": dna,
        "tests": tests,
        "total": total_count,
    })


@login_required
def soft_delete_record(request):
    """Generic endpoint to soft-delete records with dependency safety."""
    if request.method != "POST":
        return HttpResponse(status=405)

    model_name = request.POST.get("model")
    record_id = request.POST.get("id")
    next_url = request.POST.get("next", request.META.get("HTTP_REFERER", "/"))

    model_map = {
        "client": Client,
        "sample": Sample,
        "microorganism": Microorganism,
        "dna_extraction": DnaExtraction,
        "molecular_test": MolecularTest,
        "food_batch": FoodBatch,
        "user": User,
        "sample_test": SampleTest,
    }

    model = model_map.get(model_name)
    if not model:
        messages.error(request, "Invalid model.")
        return redirect(next_url)

    try:
        obj = get_object_or_404(model, pk=record_id)
    except Exception:
        messages.error(request, "Record not found.")
        return redirect(next_url)

    fk_checks = {
        "client": lambda o: o.samples.filter(is_deleted=False).exists(),
        "sample": lambda o: (
            o.dna_extractions.filter(is_deleted=False).exists()
            or o.molecular_tests.filter(is_deleted=False).exists()
            or o.attached_tests.filter(is_deleted=False).exists()
        ),
        "microorganism": lambda o: (
            o.result_rows.filter(is_deleted=False).exists()
            or o.tests.filter(is_deleted=False).exists()
        ),
        "dna_extraction": lambda o: o.tests.filter(is_deleted=False).exists(),
        "food_batch": lambda o: o.samples.filter(is_deleted=False).exists(),
        "user": lambda o: (
            o.dna_extractions.filter(is_deleted=False).exists()
            or o.molecular_tests.filter(is_deleted=False).exists()
            or o.conducted_sample_tests.filter(is_deleted=False).exists()
        ),
    }

    check_fn = fk_checks.get(model_name)
    if check_fn and check_fn(obj):
        messages.error(
            request,
            f"Cannot delete {obj} — it has active linked records. "
            f"Remove or reassign dependent records first."
        )
        return redirect(next_url)

    if model_name == "user" and obj.pk == request.user.pk:
        messages.error(request, "You cannot delete your own account.")
        return redirect(next_url)

    try:
        if hasattr(obj, "soft_delete"):
            obj.soft_delete()
        else:
            obj.is_deleted = True
            if hasattr(obj, "is_active"):
                obj.is_active = False
            obj.save(update_fields=["is_deleted", "is_active"])
        messages.success(request, f"{obj} moved to the Recycle Bin.")
    except Exception as e:
        messages.error(request, str(e))

    return redirect(next_url)


# ─── ERROR HANDLERS ───

def error_400(request, exception=None):
    return render(request, "errors/400.html", status=400)


def error_403(request, exception=None):
    return render(request, "errors/403.html", status=403)


def error_404(request, exception=None):
    return render(request, "errors/404.html", status=404)


def error_500(request):
    return render(request, "errors/500.html", status=500)