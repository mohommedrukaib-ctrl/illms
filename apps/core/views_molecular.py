import uuid
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.views import View
from django.views.generic import ListView

from apps.core.audit import get_changes, log_audit
from apps.core.forms_molecular import (
    DnaExtractionForm, MicroorganismForm, MolecularTestForm, TestResultFormSet
)
from apps.core.mixins import HtmxModalMixin, ILIMSViewMixin
from apps.core.models import (
    DnaExtraction, Microorganism, MolecularTest, LabMethod,
    ProductCategory, RiskLevel, Sample, flag_enabled, next_code
)


def _is_uuid(val) -> bool:
    if not val:
        return False
    try:
        uuid.UUID(str(val))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def _full_reload(url: str) -> HttpResponse:
    response = HttpResponse(status=200)
    response["HX-Redirect"] = url
    return response


def _generate_microbe_code(name):
    base = "".join(c for c in name.upper() if c.isalpha())[:4] or "MICR"
    code = base
    n = 1
    while Microorganism.objects.filter(code=code).exists():
        code = f"{base[:3]}{n}"
        n += 1
    return code


def _interpret_ct(ct_value, ct_cutoff=None):
    if ct_value is None:
        return "NOT_DETECTED"
    try:
        ct = Decimal(str(ct_value))
        cutoff = Decimal(str(ct_cutoff)) if ct_cutoff else Decimal("40")
        if ct < Decimal("35"):
            return "DETECTED"
        elif ct <= cutoff:
            return "INCONCLUSIVE"
        return "NOT_DETECTED"
    except Exception:
        return "INCONCLUSIVE"


def _render_sample_sections_swap(request, sample, saved_code, level="success"):
    """
    Return OOB HTML that:
    - Closes the modal
    - Swaps updated DNA/PCR/Seq sections
    - Shows toast
    NO PAGE RELOAD.
    """
    dna_extractions = sample.dna_extractions.filter(is_deleted=False).select_related("method")
    pcr_tests = sample.molecular_tests.filter(
        is_deleted=False, test_type__category__in=["TEST", "ASSAY"]
    ).select_related("test_type", "target")
    seq_tests = sample.molecular_tests.filter(
        is_deleted=False, test_type__category="SEQUENCING"
    ).select_related("test_type", "target")
    untyped = sample.molecular_tests.filter(
        is_deleted=False, test_type__isnull=True
    ).select_related("target")

    ctx = {
        "sample": sample,
        "dna_extractions": dna_extractions,
        "pcr_tests": list(pcr_tests) + list(untyped),
        "seq_tests": seq_tests,
        "is_locked": sample.is_locked_for_new_tests(),
        "show_dna_section": sample.molecular_type == "DNA_EXTRACTION",
        "show_pcr_section": sample.molecular_type == "PCR_QPCR",
        "show_seq_section": sample.molecular_type == "SEQUENCING",
    }

    dna_html = render_to_string("workflow/partials/_dna_section.html", ctx, request=request)
    pcr_html = render_to_string("workflow/partials/_pcr_section.html", ctx, request=request)
    seq_html = render_to_string("workflow/partials/_seq_section.html", ctx, request=request)

    toast = render_to_string(
        "partials/_toast.html",
        {"message": f"Saved {saved_code}.", "level": level, "oob": True},
    )

    body = (
        '<div id="modal-host" hx-swap-oob="innerHTML"></div>'
        + f'<div id="dna-section" hx-swap-oob="outerHTML">{dna_html}</div>'
        + f'<div id="pcr-section" hx-swap-oob="outerHTML">{pcr_html}</div>'
        + f'<div id="seq-section" hx-swap-oob="outerHTML">{seq_html}</div>'
        + toast
    )
    return HttpResponse(body)


# ─── MICROORGANISMS ─────────────────────────────

class MicrobeListView(ILIMSViewMixin, ListView):
    model = Microorganism
    template_name = "molecular/microbe_list.html"
    context_object_name = "microbes"
    paginate_by = 50
    page_title = "Microorganisms"
    page_subtitle = "Foodborne pathogen and target catalog"
    page_icon = "microbe"

    def get_queryset(self):
        qs = Microorganism.objects.filter(is_deleted=False).select_related("category", "risk_level")
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q) | Q(scientific_name__icontains=q))
        return qs

    def get_template_names(self):
        if getattr(self.request, "htmx", False) and not getattr(self.request.htmx, "boosted", False):
            return ["molecular/partials/_microbe_list_rows.html"]
        return [self.template_name]


class MicrobeCreateView(HtmxModalMixin, LoginRequiredMixin, View):
    modal_template = "molecular/partials/_modal_microbe_form.html"
    page_template = "molecular/microbe_form_page.html"
    modal_title = "Add Microorganism"

    def get(self, request):
        return self.render_modal_or_page(request, {
            "form": MicroorganismForm(), "modal_title": self.modal_title,
        })

    def post(self, request):
        form = MicroorganismForm(request.POST)
        cat_text = (request.POST.get("category_name__text") or "").strip()
        cat = ProductCategory.objects.filter(name__iexact=cat_text, is_active=True).first() if cat_text else None
        risk_text = (request.POST.get("risk_name__text") or "").strip()
        risk = RiskLevel.objects.filter(name__iexact=risk_text, is_active=True).first() if risk_text else None

        if form.is_valid():
            obj = form.save(commit=False)
            obj.category = cat
            obj.risk_level = risk
            if not obj.code:
                obj.code = _generate_microbe_code(obj.name)
            obj.save()
            log_audit(request.user, "CREATE", obj, get_changes(None, obj, ["name", "code"]))

            if self._is_modal(request):
                return _full_reload(reverse("core:microbe_list") + f"?saved={obj.name}")
            messages.success(request, f"{obj.name} added.")
            return redirect("core:microbe_list")

        return self.render_modal_or_page(request, {
            "form": form, "modal_title": self.modal_title,
        }, status=400)


# ─── DNA EXTRACTION ─────────────────────────────

class DnaListView(ILIMSViewMixin, ListView):
    model = DnaExtraction
    template_name = "molecular/dna_list.html"
    context_object_name = "extractions"
    paginate_by = 50
    page_title = "DNA Extractions"
    page_subtitle = "Extraction runs linked to samples"
    page_icon = "dna"

    def get_queryset(self):
        qs = DnaExtraction.objects.filter(is_deleted=False).select_related(
            "sample", "sample__client", "operator", "method"
        )
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(code__icontains=q) | Q(sample__code__icontains=q) | Q(kit_name__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["current_q"] = self.request.GET.get("q", "")
        return ctx

    def get_template_names(self):
        if getattr(self.request, "htmx", False) and not getattr(self.request.htmx, "boosted", False):
            return ["molecular/partials/_dna_list_rows.html"]
        return [self.template_name]


class DnaCreateView(HtmxModalMixin, LoginRequiredMixin, View):
    modal_template = "molecular/partials/_modal_dna_form.html"
    page_template = "molecular/dna_form_page.html"
    modal_title = "Log DNA Extraction"

    def get(self, request):
        next_url = request.GET.get("next", reverse("core:dna_list"))
        form = DnaExtractionForm(
            next_url=next_url,
            hide_advanced=flag_enabled("ui.simple_mode"),
            current_user=request.user,
        )

        prefill_sample_pk = prefill_sample_code = prefill_sample_label = ""
        sample_pk = request.GET.get("sample", "").strip()
        if _is_uuid(sample_pk):
            s = Sample.objects.filter(pk=sample_pk, is_deleted=False).first()
            if s:
                if s.is_locked_for_new_tests():
                    messages.error(request, f"Sample {s.code} is locked.")
                    return redirect("core:sample_detail", pk=s.pk)
                prefill_sample_pk = str(s.pk)
                prefill_sample_code = s.code
                prefill_sample_label = f"{s.code} — {s.product_name}"

        return self.render_modal_or_page(request, {
            "form": form, "next_url": next_url, "modal_title": self.modal_title,
            "prefill_sample_pk": prefill_sample_pk,
            "prefill_sample_code": prefill_sample_code,
            "prefill_sample_label": prefill_sample_label,
        })

    def post(self, request):
        next_url = request.POST.get("next", reverse("core:dna_list"))
        form = DnaExtractionForm(
            request.POST, next_url=next_url,
            hide_advanced=flag_enabled("ui.simple_mode"),
            current_user=request.user,
        )

        sample_pk = (request.POST.get("sample_code") or "").strip()
        sample_text = (request.POST.get("sample_code__text") or "").strip()
        sample = None
        if _is_uuid(sample_pk):
            sample = Sample.objects.filter(pk=sample_pk, is_deleted=False).first()
        if not sample and sample_text:
            sample = Sample.objects.filter(code__iexact=sample_text, is_deleted=False).first()
        if not sample:
            form.add_error("sample_code", "Please select a valid Sample.")
        elif sample.is_locked_for_new_tests():
            form.add_error("sample_code", f"Sample {sample.code} is locked.")
            sample = None

        method_text = (request.POST.get("method_name__text") or "").strip()
        method_pk = (request.POST.get("method_name") or "").strip()
        method = None
        if method_pk and _is_uuid(method_pk):
            method = LabMethod.objects.filter(
                pk=method_pk, category="DNA_EXTRACTION", is_active=True, is_deleted=False
            ).first()
        elif method_text:
            method = LabMethod.objects.filter(
                name__iexact=method_text, category="DNA_EXTRACTION", is_active=True, is_deleted=False
            ).first()
        if (method_pk or method_text) and not method:
            form.add_error("method_name", f"Method '{method_text}' not found.")

        if form.is_valid() and sample:
            obj = form.save(commit=False)
            obj.sample = sample
            obj.method = method
            obj.code = next_code("DNA", sample.client.country if sample.client_id else None)
            if not obj.operator_id:
                obj.operator = request.user
            obj.save()
            log_audit(request.user, "CREATE", obj, get_changes(None, obj, ["code", "sample_id"]))

            # Auto-advance sample state
            if sample.workflow_state == "RECEIVED":
                sample.advance(request.user, "TESTING", notes=f"DNA extraction {obj.code} logged")

            # Live swap if called from sample detail
            from_detail = request.POST.get("from_detail") == "1"
            if from_detail and self._is_modal(request):
                return _render_sample_sections_swap(request, sample, obj.code)

            if self._is_modal(request):
                return _full_reload(reverse("core:dna_list") + f"?saved={obj.code}")

            messages.success(request, f"Extraction {obj.code} saved.")
            return redirect(next_url)

        return self.render_modal_or_page(request, {
            "form": form, "next_url": next_url, "modal_title": self.modal_title,
            "prefill_sample_pk": str(sample.pk) if sample else "",
            "prefill_sample_code": sample.code if sample else "",
            "prefill_sample_label": f"{sample.code} — {sample.product_name}" if sample else "",
        }, status=400)


class DnaDetailView(ILIMSViewMixin, View):
    def get(self, request, pk):
        obj = get_object_or_404(
            DnaExtraction.objects.select_related("sample", "sample__client", "operator", "method"),
            pk=pk, is_deleted=False,
        )
        return render(request, "molecular/dna_detail.html", {
            "page_title": obj.code, "page_icon": "dna",
            "extraction": obj,
            "tests": obj.tests.filter(is_deleted=False).select_related("target"),
        })


# ─── MOLECULAR TESTS (PCR / qPCR / Sequencing) ─────────────────

class TestListView(ILIMSViewMixin, ListView):
    model = MolecularTest
    template_name = "molecular/test_list.html"
    context_object_name = "tests"
    paginate_by = 50
    page_title = "Molecular Tests"
    page_subtitle = "PCR / qPCR / Sequencing runs"
    page_icon = "flask"

    def get_queryset(self):
        qs = MolecularTest.objects.filter(is_deleted=False).select_related(
            "sample", "sample__client", "target", "operator", "dna_extraction", "test_type"
        )
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(code__icontains=q) | Q(sample__code__icontains=q) | Q(assay_name__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["types"] = LabMethod.objects.filter(category__in=["TEST", "ASSAY", "SEQUENCING"])
        ctx["current_q"] = self.request.GET.get("q", "")
        return ctx

    def get_template_names(self):
        if getattr(self.request, "htmx", False) and not getattr(self.request.htmx, "boosted", False):
            return ["molecular/partials/_test_list_rows.html"]
        return [self.template_name]


class TestCreateView(HtmxModalMixin, LoginRequiredMixin, View):
    modal_template = "molecular/partials/_modal_test_form.html"
    page_template = "molecular/test_form_page.html"
    modal_title = "Register Molecular Test"

    def get(self, request):
        next_url = request.GET.get("next", reverse("core:test_list"))
        form = MolecularTestForm(
            next_url=next_url, hide_advanced=flag_enabled("ui.simple_mode"),
            current_user=request.user,
        )

        prefill_sample_pk = prefill_sample_code = prefill_sample_label = ""
        sample_pk = request.GET.get("sample", "").strip()
        if _is_uuid(sample_pk):
            s = Sample.objects.filter(pk=sample_pk, is_deleted=False).first()
            if s:
                if s.is_locked_for_new_tests():
                    messages.error(request, f"Sample {s.code} is locked.")
                    return redirect("core:sample_detail", pk=s.pk)
                prefill_sample_pk = str(s.pk)
                prefill_sample_code = s.code
                prefill_sample_label = f"{s.code} — {s.product_name}"

        return self.render_modal_or_page(request, {
            "form": form, "formset": TestResultFormSet(),
            "next_url": next_url, "modal_title": self.modal_title,
            "prefill_sample_pk": prefill_sample_pk,
            "prefill_sample_code": prefill_sample_code,
            "prefill_sample_label": prefill_sample_label,
        })

    def post(self, request):
        next_url = request.POST.get("next", reverse("core:test_list"))
        form = MolecularTestForm(
            request.POST, next_url=next_url,
            hide_advanced=flag_enabled("ui.simple_mode"),
            current_user=request.user,
        )
        formset = TestResultFormSet(request.POST)

        sample_pk = (request.POST.get("sample_code") or "").strip()
        sample_text = (request.POST.get("sample_code__text") or "").strip()
        sample = None
        if _is_uuid(sample_pk):
            sample = Sample.objects.filter(pk=sample_pk, is_deleted=False).first()
        if not sample and sample_text:
            sample = Sample.objects.filter(code__iexact=sample_text, is_deleted=False).first()
        if not sample:
            form.add_error("sample_code", "Please select a valid Sample.")
        elif sample.is_locked_for_new_tests():
            form.add_error("sample_code", f"Sample {sample.code} is locked.")
            sample = None

        type_text = (request.POST.get("test_type_name__text") or "").strip()
        type_pk = (request.POST.get("test_type_name") or "").strip()
        test_type = None
        if type_pk and _is_uuid(type_pk):
            test_type = LabMethod.objects.filter(
                pk=type_pk, category__in=["TEST", "ASSAY", "SEQUENCING"],
                is_active=True, is_deleted=False,
            ).first()
        elif type_text:
            test_type = LabMethod.objects.filter(
                name__iexact=type_text, category__in=["TEST", "ASSAY", "SEQUENCING"],
                is_active=True, is_deleted=False,
            ).first()
        if (type_pk or type_text) and not test_type:
            form.add_error("test_type_name", f"Test type '{type_text}' not found.")

        target_text = (request.POST.get("target_name__text") or "").strip()
        target_pk = (request.POST.get("target_name") or "").strip()
        target = None
        target_created = False
        if target_pk and _is_uuid(target_pk):
            target = Microorganism.objects.filter(pk=target_pk, is_deleted=False).first()
        elif target_text:
            target = Microorganism.objects.filter(
                Q(name__iexact=target_text) | Q(code__iexact=target_text),
                is_deleted=False,
            ).first()
            if not target:
                target = Microorganism.objects.create(
                    name=target_text.strip().title(),
                    code=_generate_microbe_code(target_text),
                    is_active=False,
                )
                target_created = True

        if form.is_valid() and formset.is_valid() and sample:
            obj = form.save(commit=False)
            obj.sample = sample
            obj.test_type = test_type
            obj.target = target
            obj.code = next_code("TEST", sample.client.country if sample.client_id else None)
            if not obj.operator_id:
                obj.operator = request.user
            obj.save()

            formset.instance = obj
            saved_results = formset.save(commit=False)
            for r in saved_results:
                if r.ct_value and not r.detection:
                    r.detection = _interpret_ct(r.ct_value, obj.ct_cutoff)
                r.save()
            for form_del in formset.deleted_objects:
                form_del.delete()

            log_audit(request.user, "CREATE", obj, get_changes(None, obj, ["code", "sample_id"]))

            if sample.workflow_state == "RECEIVED":
                sample.advance(request.user, "TESTING", notes=f"Test {obj.code} registered")

            if target_created:
                messages.warning(request,
                    f"New microorganism '{target.name}' added (pending admin activation).")

            from_detail = request.POST.get("from_detail") == "1"
            if from_detail and self._is_modal(request):
                return _render_sample_sections_swap(request, sample, obj.code)

            if self._is_modal(request):
                return _full_reload(reverse("core:test_detail", args=[obj.pk]) + "?saved=1")

            messages.success(request, f"Test {obj.code} registered.")
            return redirect("core:test_detail", pk=obj.pk)

        return self.render_modal_or_page(request, {
            "form": form, "formset": formset,
            "next_url": next_url, "modal_title": self.modal_title,
            "prefill_sample_pk": str(sample.pk) if sample else "",
            "prefill_sample_code": sample.code if sample else "",
            "prefill_sample_label": f"{sample.code} — {sample.product_name}" if sample else "",
        }, status=400)


class TestDetailView(ILIMSViewMixin, View):
    def get(self, request, pk):
        obj = get_object_or_404(
            MolecularTest.objects.select_related(
                "sample", "sample__client", "target", "operator", "dna_extraction", "test_type"
            ),
            pk=pk, is_deleted=False,
        )
        return render(request, "molecular/test_detail.html", {
            "page_title": obj.code, "page_icon": "flask",
            "test": obj,
            "results": obj.results.filter(is_deleted=False).select_related("microorganism"),
        })

    def post(self, request, pk):
        obj = get_object_or_404(MolecularTest, pk=pk, is_deleted=False)
        formset = TestResultFormSet(request.POST, instance=obj)
        if formset.is_valid():
            saved = formset.save(commit=False)
            for r in saved:
                if r.ct_value and not r.detection:
                    r.detection = _interpret_ct(r.ct_value, obj.ct_cutoff)
                r.save()
            for d in formset.deleted_objects:
                d.delete()
            messages.success(request, "Results saved.")
        return redirect("core:test_detail", pk=obj.pk)