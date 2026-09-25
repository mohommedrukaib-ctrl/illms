import uuid

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
from apps.core.forms_workflow import AdvanceStatusForm, ClientForm, SampleForm
from apps.core.mixins import HtmxModalMixin, ILIMSViewMixin
from apps.core.models import (
    Client, Country, Sample, ProductCategory, ProductType, LabMethod,
    flag_enabled, next_code,
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
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


MOLECULAR_TYPE_TO_METHOD_CATEGORY = {
    "DNA_EXTRACTION": "DNA_EXTRACTION",
    "PCR_QPCR": "TEST",
    "SEQUENCING": "SEQUENCING",
}


class ClientListView(ILIMSViewMixin, ListView):
    model = Client
    template_name = "workflow/client_list.html"
    context_object_name = "clients"
    paginate_by = 50
    page_title = "Clients"
    page_subtitle = "Manage laboratory clients and contact information"
    page_icon = "client"

    def get_queryset(self):
        qs = Client.objects.filter(is_deleted=False).select_related("country", "region")
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(name__icontains=q) | Q(code__icontains=q)
                | Q(email__icontains=q) | Q(phone__icontains=q)
            )
        return qs

    def get_template_names(self):
        if getattr(self.request, "htmx", False) and not getattr(self.request.htmx, "boosted", False):
            return ["workflow/partials/_client_list_rows.html"]
        return [self.template_name]


class ClientCreateView(HtmxModalMixin, LoginRequiredMixin, View):
    modal_template = "workflow/partials/_modal_client_form.html"
    page_template = "workflow/client_form_page.html"
    modal_title = "Register New Client"

    def get(self, request):
        next_url = request.GET.get("next", reverse("core:client_list"))
        form = ClientForm(next_url=next_url)
        return self.render_modal_or_page(request, {
            "form": form, "next_url": next_url, "modal_title": self.modal_title,
        })

    def post(self, request):
        next_url = request.POST.get("next", reverse("core:client_list"))
        form = ClientForm(request.POST, next_url=next_url)

        if form.is_valid():
            client = form.save(commit=False)
            client.code = next_code("CLIENT", client.country, client.region)
            try:
                client.save()
            except Exception as exc:
                msg = str(exc).lower()
                if "phone" in msg:
                    form.add_error("phone", "This phone number is already registered.")
                else:
                    form.add_error(None, f"Could not save client: {exc}")
                return self.render_modal_or_page(request, {
                    "form": form, "next_url": next_url, "modal_title": self.modal_title,
                }, status=400)

            log_audit(request.user, "CREATE", client,
                      get_changes(None, client, ["name", "code", "email", "phone", "country_id"]))

            if self._is_modal(request):
                return _full_reload(reverse("core:client_list") + f"?saved={client.code}")

            messages.success(request, f"Client {client.code} registered.")
            return redirect(next_url)

        return self.render_modal_or_page(request, {
            "form": form, "next_url": next_url, "modal_title": self.modal_title,
        }, status=400)


class SampleListView(ILIMSViewMixin, ListView):
    model = Sample
    template_name = "workflow/sample_list.html"
    context_object_name = "samples"
    paginate_by = 50
    page_title = "Product / Sample Intake"
    page_subtitle = "Products and samples pending or undergoing laboratory testing"
    page_icon = "sample"

    def get_queryset(self):
        qs = Sample.objects.filter(is_deleted=False).select_related(
            "client", "product_category", "product_type", "requested_test", "assigned_to"
        )
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(code__icontains=q) | Q(product_name__icontains=q) | Q(client__name__icontains=q)
            )
        state = self.request.GET.get("state", "")
        if state:
            qs = qs.filter(workflow_state=state)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["state_choices"] = Sample.WorkflowState.choices
        ctx["current_q"] = self.request.GET.get("q", "")
        ctx["current_state"] = self.request.GET.get("state", "")
        return ctx

    def get_template_names(self):
        if getattr(self.request, "htmx", False) and not getattr(self.request.htmx, "boosted", False):
            return ["workflow/partials/_sample_list_rows.html"]
        return [self.template_name]


class SampleCreateView(HtmxModalMixin, LoginRequiredMixin, View):
    modal_template = "workflow/partials/_modal_sample_form.html"
    page_template = "workflow/sample_form_page.html"
    modal_title = "Register Sample Intake"

    def _get_return_config(self, request):
        """Extract return_to and derive molecular_type + lock flag."""
        source = request.GET if request.method == "GET" else request.POST
        return_to = (source.get("return_to") or "").strip().lower()

        mapping = {
            "dna": ("DNA_EXTRACTION", True),
            "test": ("PCR_QPCR", True),
            "pcr": ("PCR_QPCR", True),
            "sequencing": ("SEQUENCING", True),
        }
        mol_type, lock = mapping.get(return_to, (None, False))
        return return_to, mol_type, lock

    def get(self, request):
        next_url = request.GET.get("next", reverse("core:sample_list"))
        return_to, initial_mol, lock = self._get_return_config(request)

        form = SampleForm(
            next_url=next_url,
            hide_advanced=flag_enabled("ui.simple_mode"),
            lock_molecular_type=lock,
            initial_molecular_type=initial_mol,
        )

        return self.render_modal_or_page(request, {
            "form": form, "next_url": next_url,
            "modal_title": self.modal_title, "return_to": return_to,
            "locked_molecular_type": initial_mol if lock else "",
        })

    def post(self, request):
        next_url = request.POST.get("next", reverse("core:sample_list"))
        return_to, initial_mol, lock = self._get_return_config(request)

        form = SampleForm(
            request.POST,
            next_url=next_url,
            hide_advanced=flag_enabled("ui.simple_mode"),
            lock_molecular_type=lock,
            initial_molecular_type=initial_mol,
        )

        # Resolve or create Client
        client_pk_raw = (request.POST.get("client_name") or "").strip()
        client_text = (request.POST.get("client_name__text") or "").strip()
        client_phone = (
            request.POST.get("client_phone_mirror")
            or request.POST.get("client_phone") or ""
        ).strip()

        client = None
        try:
            if _is_uuid(client_pk_raw):
                client = Client.objects.filter(pk=client_pk_raw, is_deleted=False).first()
            if not client and client_text:
                client = Client.objects.filter(name__iexact=client_text.strip(), is_deleted=False).first()
            if not client and client_text:
                if not client_phone:
                    form.add_error("client_phone", "Phone required for new client (click + to unlock).")
                elif Client.objects.filter(phone=client_phone, is_deleted=False).exists():
                    form.add_error("client_phone", f"Phone '{client_phone}' already used.")
                else:
                    country = Country.objects.filter(is_active=True).first()
                    if not country:
                        form.add_error(None, "No country in Settings.")
                    else:
                        client = Client.objects.create(
                            name=client_text.strip().title(),
                            phone=client_phone,
                            country=country,
                            code=next_code("CLIENT", country, None),
                        )
                        log_audit(request.user, "CREATE", client,
                                  get_changes(None, client, ["name", "phone", "code"]))
        except Exception as e:
            form.add_error(None, str(e))

        if not client and not form.errors:
            form.add_error("client_name", "Select or type a client.")

        if not (client and form.is_valid()):
            return self.render_modal_or_page(request, {
                "form": form, "next_url": next_url,
                "modal_title": self.modal_title, "return_to": return_to,
                "locked_molecular_type": initial_mol if lock else "",
            }, status=400)

        cat_text = (form.cleaned_data.get("_category_text") or "").strip().title()
        type_text = (form.cleaned_data.get("_type_text") or "").strip().title()
        test_text = (form.cleaned_data.get("_test_text") or "").strip()
        molecular_type = form.cleaned_data.get("molecular_type") or initial_mol

        cat = ProductCategory.objects.get_or_create(
            name=cat_text, defaults={"is_active": True}
        )[0] if cat_text else None

        ptype = None
        if type_text:
            ptype, _ = ProductType.objects.get_or_create(
                name=type_text, defaults={"category": cat, "is_active": True}
            )
            if cat and not ptype.category_id:
                ptype.category = cat
                ptype.save(update_fields=["category"])

        method_category = MOLECULAR_TYPE_TO_METHOD_CATEGORY.get(molecular_type, "TEST")
        lab_test = None
        if test_text:
            lab_test, _ = LabMethod.objects.get_or_create(
                name=test_text,
                defaults={"category": method_category, "is_active": True},
            )

        sample = form.save(commit=False)
        sample.client = client
        sample.product_category = cat
        sample.product_type = ptype
        sample.requested_test = lab_test
        sample.molecular_type = molecular_type
        sample.workflow_state = Sample.WorkflowState.RECEIVED
        sample.code = next_code("SAMPLE", client.country, getattr(client, "region", None))
        sample.save()
        log_audit(request.user, "CREATE", sample,
                  get_changes(None, sample, ["code", "client_id", "product_name", "molecular_type"]))

        if return_to in ("dna", "test", "pcr", "sequencing"):
            return self._reopen_parent_modal(request, return_to, sample)

        receipt_url = reverse("core:sample_receipt", args=[sample.pk])
        if self._is_modal(request):
            samples = Sample.objects.filter(is_deleted=False).select_related(
                "client", "product_type"
            )[:50]
            rows = render_to_string(
                "workflow/partials/_sample_list_rows.html",
                {"samples": samples}, request=request,
            )
            toast = render_to_string(
                "partials/_toast.html",
                {"message": f"Sample {sample.code} registered.", "level": "success", "oob": True},
            )
            body = (
                '<div id="modal-host" hx-swap-oob="innerHTML"></div>'
                + toast
                + f'<tbody id="sample-tbody" hx-swap-oob="innerHTML">{rows}</tbody>'
                + f"<script>window.open('{receipt_url}','_blank','width=800,height=900');</script>"
            )
            return HttpResponse(body)

        messages.success(request, f"Sample {sample.code} registered.")
        return redirect(receipt_url)

    def _reopen_parent_modal(self, request, return_to, sample):
        from apps.core.forms_molecular import (
            DnaExtractionForm, MolecularTestForm, TestResultFormSet,
        )

        toast = render_to_string(
            "partials/_toast.html",
            {
                "message": f"Sample {sample.code} created — complete the form below.",
                "level": "success", "oob": True,
            },
        )
        label = f"{sample.code} — {sample.product_name}" if sample.product_name else sample.code

        if return_to == "dna":
            form = DnaExtractionForm(
                next_url=reverse("core:dna_list"),
                hide_advanced=flag_enabled("ui.simple_mode"),
                current_user=request.user,
            )
            html = render_to_string(
                "molecular/partials/_modal_dna_form.html",
                {
                    "form": form,
                    "next_url": reverse("core:dna_list"),
                    "modal_title": "Log DNA Extraction",
                    "prefill_sample_pk": str(sample.pk),
                    "prefill_sample_code": sample.code,
                    "prefill_sample_label": label,
                },
                request=request,
            )
            return HttpResponse(html + toast)

        form = MolecularTestForm(
            next_url=reverse("core:test_list"),
            hide_advanced=flag_enabled("ui.simple_mode"),
            current_user=request.user,
        )
        formset = TestResultFormSet()
        html = render_to_string(
            "molecular/partials/_modal_test_form.html",
            {
                "form": form,
                "formset": formset,
                "next_url": reverse("core:test_list"),
                "modal_title": "Register Molecular Test",
                "prefill_sample_pk": str(sample.pk),
                "prefill_sample_code": sample.code,
                "prefill_sample_label": label,
            },
            request=request,
        )
        return HttpResponse(html + toast)


class SampleReceiptView(ILIMSViewMixin, View):
    def get(self, request, pk):
        sample = get_object_or_404(
            Sample.objects.select_related("client", "product_category", "product_type", "requested_test"),
            pk=pk, is_deleted=False,
        )
        return render(request, "workflow/sample_receipt.html", {
            "page_title": "Sample Receipt", "page_icon": "print", "sample": sample,
        })


class SampleDetailView(ILIMSViewMixin, View):
    def get(self, request, pk):
        sample = get_object_or_404(
            Sample.objects.select_related(
                "client", "product_category", "product_type", "requested_test",
                "assigned_to", "batch",
            ),
            pk=pk, is_deleted=False,
        )
        events = sample.events.select_related("changed_by").all()
        from apps.core.models import AuditLog
        audits = AuditLog.objects.filter(record_id=str(sample.pk), model_name="Sample")
        tab = request.GET.get("tab", "overview")

        dna_extractions = sample.dna_extractions.filter(is_deleted=False).select_related("method")
        pcr_tests = sample.molecular_tests.filter(
            is_deleted=False, test_type__category__in=["TEST", "ASSAY"]
        ).select_related("test_type", "target")
        seq_tests = sample.molecular_tests.filter(
            is_deleted=False, test_type__category="SEQUENCING"
        ).select_related("test_type", "target")

        # Tests with no test_type or unknown category also go into PCR bucket
        untyped_tests = sample.molecular_tests.filter(
            is_deleted=False, test_type__isnull=True
        ).select_related("target")

        return render(request, "workflow/sample_detail.html", {
            "page_title": f"Sample {sample.code}", "page_icon": "sample",
            "sample": sample, "events": events, "audits": audits, "active_tab": tab,
            "dna_extractions": dna_extractions,
            "pcr_tests": list(pcr_tests) + list(untyped_tests),
            "seq_tests": seq_tests,
            "is_locked": sample.is_locked_for_new_tests(),
            "show_dna_section": sample.molecular_type == "DNA_EXTRACTION",
            "show_pcr_section": sample.molecular_type == "PCR_QPCR",
            "show_seq_section": sample.molecular_type == "SEQUENCING",
            "breadcrumbs": [
                {"label": "Home", "url": "/"},
                {"label": "Samples", "url": reverse("core:sample_list")},
                {"label": sample.code, "url": ""},
            ],
        })


class SampleAdvanceStatusView(HtmxModalMixin, LoginRequiredMixin, View):
    modal_template = "workflow/partials/_modal_sample_status.html"
    page_template = "workflow/sample_status_page.html"
    modal_title = "Update Status"

    def get(self, request, pk):
        sample = get_object_or_404(Sample, pk=pk, is_deleted=False)
        form = AdvanceStatusForm(initial={"to_state": sample.workflow_state})
        return self.render_modal_or_page(request, {
            "form": form, "sample": sample,
            "modal_title": f"Update Status: {sample.code}",
        })

    def post(self, request, pk):
        sample = get_object_or_404(Sample, pk=pk, is_deleted=False)
        form = AdvanceStatusForm(request.POST)
        if form.is_valid():
            to_state = form.cleaned_data["to_state"]
            notes = form.cleaned_data["notes"]
            sample.advance(request.user, to_state, notes)

            if self._is_modal(request):
                # Live swap: return updated status card + close modal
                html = render_to_string(
                    "workflow/partials/_status_card.html",
                    {"sample": sample}, request=request,
                )
                toast = render_to_string(
                    "partials/_toast.html",
                    {"message": f"Status updated to {sample.get_workflow_state_display()}.",
                     "level": "success", "oob": True},
                )
                body = (
                    '<div id="modal-host" hx-swap-oob="innerHTML"></div>'
                    + f'<div id="status-card" hx-swap-oob="outerHTML">{html}</div>'
                    + toast
                )
                return HttpResponse(body)

            messages.success(request, f"Status updated to {sample.get_workflow_state_display()}.")
            return redirect(reverse("core:sample_detail", args=[sample.pk]))

        return self.render_modal_or_page(request, {
            "form": form, "sample": sample,
            "modal_title": f"Update Status: {sample.code}",
        }, status=400)