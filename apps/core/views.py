from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.timezone import now

from apps.accounts.decorators import role_required
from apps.core.forms import CountryForm, LaboratoryForm, RegionForm, SystemSettingsForm
from apps.core.models import (
    Client, Country, FeatureFlag, Laboratory, Region, Sample,
    SystemSetting, next_code
)
from apps.core.smart_select import SmartRegistry, smart_search


# ─── DASHBOARD ───

@login_required
def dashboard_view(request):
    """Main dashboard with real-time KPI statistics."""
    from apps.core.models import MolecularTest

    active_samples = Sample.objects.filter(is_deleted=False, status__is_terminal=False).count()
    needs_qc = Sample.objects.filter(is_deleted=False, status__name__in=["Analysis", "Testing In Progress"]).count()
    total_clients = Client.objects.filter(is_deleted=False).count()

    current_month = now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    monthly_tests = MolecularTest.objects.filter(is_deleted=False, run_date__gte=current_month).count()

    recent_samples = Sample.objects.filter(is_deleted=False).select_related("client", "status").order_by("-created_at")[:5]

    return render(request, "pages/placeholder.html", {
        "page_title": "Dashboard",
        "page_subtitle": "Overview of laboratory operations",
        "page_icon": "dashboard",
        "stats": {
            "active_samples": active_samples,
            "needs_qc": needs_qc,
            "total_clients": total_clients,
            "monthly_tests": monthly_tests,
        },
        "recent_samples": recent_samples,
    })


# ─── THEME TOGGLE ───

@login_required
def theme_toggle_view(request):
    """Toggle between light and dark theme via POST form (no JS needed)."""
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


# ─── SETTINGS HUB ───

@login_required
@role_required("ADMIN")
def settings_hub_view(request):
    """Central interface to manage numbering configurations, feature toggles, and core data."""
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

@login_required
def smart_select_results(request, kind_key):
    """HTMX live search + category/molecular cascade."""
    kind = SmartRegistry.get(kind_key)
    if kind is None:
        return HttpResponse(status=404)

    field_name = request.GET.get("field", "")
    input_id = request.GET.get("input_id", "")

    query = request.GET.get("q", "").strip()
    if not query:
        for k, v in request.GET.items():
            if k.endswith("__text") or k == field_name:
                query = (v or "").strip()
                break
    if "js:event" in query:
        query = ""

    qs = kind.queryset_fn()

    category_filter = (
        request.GET.get("category")
        or request.GET.get("product_category")
        or request.GET.get("product_category__text")
        or ""
    ).strip()

    molecular_type_filter = (request.GET.get("molecular_type") or "").strip()

    if kind_key == "product_type" and category_filter:
        qs = qs.filter(
            Q(category__name__icontains=category_filter) | Q(category__isnull=True)
        )

    if kind_key == "lab_method":
        # Filter by molecular type → LabMethod.category
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
        "page_subtitle": "Verify type-ahead + picker + resolver behavior",
        "page_icon": "search",
        "country_widget": build_widget("country"),
        "region_widget": build_widget("region"),
        "laboratory_widget": build_widget("laboratory"),
    })


# ─── RECYCLE BIN & SOFT DELETE ───

@login_required
@role_required("ADMIN")
def recycle_bin_view(request):
    """View and manage soft-deleted records."""
    from apps.core.models import Microorganism

    if request.method == "POST":
        action = request.POST.get("action")
        item_type = request.POST.get("type")
        item_id = request.POST.get("id")

        model_map = {
            "client": Client,
            "sample": Sample,
            "microorganism": Microorganism,
        }
        model = model_map.get(item_type)
        if model:
            obj = get_object_or_404(model, pk=item_id)
            if action == "restore":
                obj.is_deleted = False
                if hasattr(obj, "is_active"):
                    obj.is_active = True
                obj.save()
                messages.success(request, f"Restored {obj}.")
            elif action == "hard_delete":
                obj.delete()
                messages.success(request, f"Permanently deleted record.")
        return redirect("core:recycle_bin")

    clients = Client.objects.filter(is_deleted=True)
    samples = Sample.objects.filter(is_deleted=True)
    microbes = Microorganism.objects.filter(is_deleted=True)

    return render(request, "pages/recycle_bin.html", {
        "page_title": "Recycle Bin",
        "page_subtitle": "Restore or permanently remove soft-deleted records",
        "page_icon": "settings",
        "clients": clients,
        "samples": samples,
        "microbes": microbes,
    })


@login_required
def soft_delete_record(request):
    """Generic endpoint to soft-delete records."""
    if request.method != "POST":
        return HttpResponse(status=405)

    model_name = request.POST.get("model")
    record_id = request.POST.get("id")

    from apps.core.models import Microorganism

    model_map = {
        "client": Client,
        "sample": Sample,
        "microorganism": Microorganism,
    }

    model = model_map.get(model_name)
    if not model:
        return HttpResponse("Invalid model", status=400)

    obj = get_object_or_404(model, pk=record_id)

    try:
        if hasattr(obj, "soft_delete"):
            obj.soft_delete()
            messages.success(request, f"{obj} moved to Recycle Bin.")
    except ValidationError as e:
        messages.error(request, e.message if hasattr(e, "message") else str(e))

    return redirect(request.META.get("HTTP_REFERER", "/"))


# ─── ERROR HANDLERS ───

def error_400(request, exception=None):
    return render(request, "errors/400.html", status=400)


def error_403(request, exception=None):
    return render(request, "errors/403.html", status=403)


def error_404(request, exception=None):
    return render(request, "errors/404.html", status=404)


def error_500(request):
    return render(request, "errors/500.html", status=500)

