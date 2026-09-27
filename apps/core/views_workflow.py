import uuid

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import ListView

from apps.core.audit import get_changes, log_audit
from apps.core.forms_workflow import AdvanceStatusForm, ClientForm, SampleForm
from apps.core.mixins import HtmxModalMixin, ILIMSViewMixin
from apps.core.models import (
    Client, Country, Sample, ProductCategory, ProductType, LabMethod,
    Reminder, flag_enabled, next_code,
)
from apps.core.notifications import push_notification, push_to_role, notify_self
from apps.core.permissions import LaboratoryScopedPermissionMixin


def _is_uuid(val) -> bool:
    """Safely check whether a string is a valid UUID."""
    if not val:
        return False
    try:
        uuid.UUID(str(val))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def _full_reload(url: str) -> HttpResponse:
    """
    Return an HTMX redirect with an OOB modal clear and meta-refresh fallback.
    Guarantees page lists auto-refresh even if HX-Redirect is swallowed.
    """
    body = (
        '<div id="modal-host" hx-swap-oob="innerHTML"></div>'
        f'<meta http-equiv="refresh" content="0;url={url}">'
    )
    response = HttpResponse(body, status=200)
    response["HX-Redirect"] = url
    response["HX-Trigger"] = "ilims:refresh"
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


MOLECULAR_TYPE_TO_METHOD_CATEGORY = {
    "DNA_EXTRACTION": "DNA_EXTRACTION",
    "PCR_QPCR": "TEST",
    "SEQUENCING": "SEQUENCING",
}


# ══════════════════════════════════════════════════════════════════
# CLIENTS
# ══════════════════════════════════════════════════════════════════

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
                Q(name__icontains=q)
                | Q(code__icontains=q)
                | Q(email__icontains=q)
                | Q(phone__icontains=q)
            )
        return qs

    def get_template_names(self):
        if getattr(self.request, "htmx", False) and not getattr(
            self.request.htmx, "boosted", False
        ):
            return ["workflow/partials/_client_list_rows.html"]
        return [self.template_name]


class ClientCreateView(HtmxModalMixin, LoginRequiredMixin, View):
    modal_template = "workflow/partials/_modal_client_form.html"
    page_template = "workflow/client_form_page.html"
    modal_title = "Register New Client"

    def _get_instance(self, request):
        edit_pk = request.GET.get("edit") or request.POST.get("edit")
        if edit_pk:
            try:
                return Client.objects.get(pk=edit_pk, is_deleted=False)
            except (Client.DoesNotExist, ValueError):
                pass
        return None

    def get(self, request):
        instance = self._get_instance(request)
        title = "Edit Client" if instance else "Register New Client"
        next_url = request.GET.get("next", reverse("core:client_list"))

        form = ClientForm(instance=instance, next_url=next_url, request_get=request.GET)
        return self.render_modal_or_page(request, {
            "form": form,
            "next_url": next_url,
            "modal_title": title,
            "edit_pk": str(instance.pk) if instance else "",
        })


# ══════════════════════════════════════════════════════════════════
# SAMPLES
# ══════════════════════════════════════════════════════════════════

class SampleListView(LaboratoryScopedPermissionMixin, ILIMSViewMixin, ListView):
    model = Sample
    template_name = "workflow/sample_list.html"
    context_object_name = "samples"
    paginate_by = 50
    page_title = "Product / Sample Intake"
    page_subtitle = "Products and samples pending or undergoing laboratory testing"
    page_icon = "sample"

    def get_queryset(self):
        qs = Sample.objects.filter(is_deleted=False).select_related(
            "client", "product_category", "product_type",
            "requested_test", "assigned_to",
        )
        # Apply object-level laboratory scoping based on user role
        qs = self.scope_queryset(qs, self.request.user, lab_field_path="laboratory")

        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(code__icontains=q)
                | Q(product_name__icontains=q)
                | Q(client__name__icontains=q)
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
        if getattr(self.request, "htmx", False) and not getattr(
            self.request.htmx, "boosted", False
        ):
            return ["workflow/partials/_sample_list_rows.html"]
        return [self.template_name]


class SampleCreateView(HtmxModalMixin, LoginRequiredMixin, View):
    modal_template = "workflow/partials/_modal_sample_form.html"
    page_template = "workflow/sample_form_page.html"
    modal_title = "Register Sample Intake"

    def _get_instance(self, request):
        edit_pk = request.GET.get("edit") or request.POST.get("edit")
        if edit_pk:
            try:
                return Sample.objects.get(pk=edit_pk, is_deleted=False)
            except (Sample.DoesNotExist, ValueError):
                pass
        return None

    def get(self, request):
        next_url = request.GET.get("next", reverse("core:sample_list"))
        instance = self._get_instance(request)

        form = SampleForm(
            instance=instance,
            next_url=next_url,
            request_get=request.GET,
            hide_advanced=flag_enabled("ui.simple_mode"),
        )

        title = "Edit Sample" if instance else self.modal_title
        return self.render_modal_or_page(request, {
            "form": form,
            "next_url": next_url,
            "modal_title": title,
            "edit_pk": str(instance.pk) if instance else "",
        })

    def post(self, request):
        next_url = request.POST.get("next", reverse("core:sample_list"))
        instance = self._get_instance(request)

        # SmartSelect: ensure main keys are populated from __text when needed
        data = request.POST.copy()
        for key in ("client_name", "product_category", "product_type", "requested_test"):
            raw = (data.get(key) or "").strip()
            text = (data.get(f"{key}__text") or "").strip()
            if not raw and text:
                data[key] = text

        form = SampleForm(
            data,
            instance=instance,
            next_url=next_url,
            hide_advanced=flag_enabled("ui.simple_mode"),
        )

        # ── Resolve or create Client ──
        client_pk_raw = (data.get("client_name") or "").strip()
        client_text = (data.get("client_name__text") or "").strip()
        if client_pk_raw and not _is_uuid(client_pk_raw):
            client_text = client_text or client_pk_raw

        client_phone = (
            data.get("client_phone_mirror")
            or data.get("client_phone")
            or ""
        ).strip()

        client = None
        try:
            if _is_uuid(client_pk_raw):
                client = Client.objects.filter(
                    pk=client_pk_raw, is_deleted=False
                ).first()

            if not client and client_text:
                client = Client.objects.filter(
                    name__iexact=client_text.strip(), is_deleted=False
                ).first()

            if not client and client_text:
                # New client path
                if not client_phone:
                    form.add_error(
                        "client_phone",
                        "Phone required for new client (click + to unlock).",
                    )
                elif Client.objects.filter(
                    phone=client_phone, is_deleted=False
                ).exists():
                    form.add_error(
                        "client_phone",
                        f"Phone '{client_phone}' already used.",
                    )
                else:
                    country = Country.objects.filter(is_active=True).first()
                    if not country:
                        form.add_error(None, "No country configured in Settings.")
                    else:
                        client = Client.objects.create(
                            name=client_text.strip().title(),
                            phone=client_phone,
                            country=country,
                            code=next_code("CLIENT", country, None),
                        )
                        log_audit(
                            request.user,
                            "CREATE",
                            client,
                            get_changes(None, client, ["name", "phone", "code"]),
                        )
        except Exception as e:
            form.add_error(None, str(e))

        if not client and not form.errors:
            form.add_error("client_name", "Select or type a client.")

        if not (client and form.is_valid()):
            if client_text and "client_name" in form.fields:
                form.fields["client_name"].widget.attrs["data-prefill-display"] = client_text
            if client and _is_uuid(str(getattr(client, "pk", ""))):
                try:
                    form.data = form.data.copy()
                    form.data["client_name"] = str(client.pk)
                except Exception:
                    pass

            return self.render_modal_or_page(request, {
                "form": form,
                "next_url": next_url,
                "modal_title": "Edit Sample" if instance else self.modal_title,
                "edit_pk": str(instance.pk) if instance else "",
            }, status=400)

        # ── Resolve Category & Product Type ──
        cat_text = (form.cleaned_data.get("_category_text") or "").strip().title()
        type_text = (form.cleaned_data.get("_type_text") or "").strip().title()
        test_text = (form.cleaned_data.get("_test_text") or "").strip().upper()

        cat = None
        if cat_text:
            cat, _ = ProductCategory.objects.get_or_create(
                name=cat_text, defaults={"is_active": True},
            )

        ptype = None
        if type_text:
            ptype, _ = ProductType.objects.get_or_create(
                name=type_text,
                defaults={"category": cat, "is_active": True},
            )
            if cat and not ptype.category_id:
                ptype.category = cat
                ptype.save(update_fields=["category"])

        lab_test = None
        if test_text:
            lab_test, _ = LabMethod.objects.get_or_create(
                name=test_text,
                defaults={"category": "GENERAL", "is_active": True},
            )

        sample = form.save(commit=False)
        sample.client = client
        sample.product_category = cat
        sample.product_type = ptype
        sample.requested_test = lab_test

        if not instance:
            sample.workflow_state = Sample.WorkflowState.RECEIVED
            sample.code = next_code(
                "SAMPLE",
                client.country,
                getattr(client, "region", None),
            )
            if (
                hasattr(request.user, "laboratory")
                and request.user.laboratory
                and not sample.laboratory_id
            ):
                sample.laboratory = request.user.laboratory

        sample.save()

        if not sample.tracking_code:
            sample.generate_tracking_code()

        from apps.core.models import SampleTest
        if lab_test and not sample.attached_tests.filter(
            test_type=lab_test, is_deleted=False
        ).exists():
            SampleTest.objects.create(
                code=next_code("TEST", client.country if client else None),
                sample=sample,
                test_type=lab_test,
                operator=sample.assigned_to or request.user,
            )

        action = "UPDATE" if instance else "CREATE"
        log_audit(
            request.user,
            action,
            sample,
            get_changes(
                instance,
                sample,
                ["code", "client_id", "product_name", "requested_test_id"],
            ),
        )

        # ══════════════════════════════════════════════════════════
        # NOTIFICATIONS & REMINDERS
        # ══════════════════════════════════════════════════════════
        sample_url = reverse("core:sample_detail", args=[sample.pk])

        # Always notify the user who saved (Shows up in the Bell to confirm)
        notify_self(
            request.user,
            title=f"{'Updated' if instance else 'Saved'} sample: {sample.code}",
            message=f"{sample.product_name} · Due: {sample.due_date or '—'}",
            level="success",
            url=sample_url,
        )

        # Work items (Reminders and Assignee notifications) only on creation
        if not instance:
            # Assignee for work items = assigned technician, OR fallback to you
            assignee = sample.assigned_to or request.user

            # 1. Notify other assignee if it's a different person
            if sample.assigned_to_id and sample.assigned_to_id != request.user.id:
                push_notification(
                    user=sample.assigned_to,
                    title=f"New Sample Assigned: {sample.code}",
                    message=f"You have been assigned to analyze {sample.product_name}.",
                    level="info",
                    url=sample_url,
                )

            # 2. Auto-create reminder if a due date exists
            if sample.due_date:
                today = timezone.now().date()
                days_until_due = (sample.due_date - today).days

                if days_until_due < 0:
                    kind = Reminder.Kind.OVERDUE
                elif days_until_due == 0:
                    kind = Reminder.Kind.DUE_TODAY
                elif days_until_due <= 2:
                    kind = Reminder.Kind.DUE_SOON
                else:
                    kind = Reminder.Kind.CUSTOM

                priority = (
                    Reminder.Priority.URGENT 
                    if sample.priority == "URGENT" 
                    else Reminder.Priority.NORMAL
                )
                
                title = f"Complete Test: {sample.code}"
                
                if not Reminder.objects.filter(
                    sample=sample,
                    assigned_to=assignee,
                    title=title,
                    is_done=False,
                ).exists():
                    Reminder.objects.create(
                        kind=kind,
                        priority=priority,
                        title=title,
                        message=f"Requested Test: {sample.requested_test.name if sample.requested_test else 'General'} | Product: {sample.product_name}",
                        sample=sample,
                        assigned_to=assignee,
                        due_date=sample.due_date,
                    )

            # 3. Notify all lab managers for urgent samples
            if sample.priority == "URGENT":
                try:
                    push_to_role(
                        "LAB_MANAGER",
                        title=f"⚠️ Urgent Sample Received: {sample.code}",
                        message=f"Client: {client.name} | Product: {sample.product_name}",
                        level="warning",
                        url=sample_url,
                    )
                except Exception:
                    pass

        receipt_url = reverse("core:sample_receipt", args=[sample.pk])
        if self._is_modal(request):
            return _full_reload(next_url + f"?saved={sample.code}")

        messages.success(request, f"Sample {sample.code} registered.")
        return redirect(receipt_url)


class SampleReceiptView(ILIMSViewMixin, View):
    def get(self, request, pk):
        sample = get_object_or_404(
            Sample.objects.select_related(
                "client", "client__country", "product_category",
                "product_type", "requested_test", "laboratory",
            ),
            pk=pk, is_deleted=False,
        )

        # Ensure tracking code exists
        if not sample.tracking_code:
            sample.generate_tracking_code()

        from apps.core.utils_qr import generate_qr_svg
        qr_svg = generate_qr_svg(sample.tracking_code)

        return render(request, "workflow/sample_receipt.html", {
            "page_title": f"Receipt: {sample.code}",
            "page_icon": "print",
            "sample": sample,
            "qr_svg": qr_svg,
        })


class SampleDetailView(LaboratoryScopedPermissionMixin, ILIMSViewMixin, View):
    def get(self, request, pk):
        sample = get_object_or_404(
            Sample.objects.select_related(
                "client", "product_category", "product_type",
                "requested_test", "assigned_to", "batch",
            ),
            pk=pk,
            is_deleted=False,
        )

        # Enforce laboratory object-level scoping
        self.check_object_permission(request, sample, lab_attr="laboratory")

        events = sample.events.select_related("changed_by").all()
        from apps.core.models import AuditLog
        audits = AuditLog.objects.filter(
            record_id=str(sample.pk), model_name="Sample",
        )
        tab = request.GET.get("tab", "overview")

        dna_extractions = sample.dna_extractions.filter(
            is_deleted=False,
        ).select_related("method")

        pcr_tests = sample.molecular_tests.filter(
            is_deleted=False,
            test_type__category__in=["TEST", "ASSAY"],
        ).select_related("test_type", "target")

        seq_tests = sample.molecular_tests.filter(
            is_deleted=False,
            test_type__category="SEQUENCING",
        ).select_related("test_type", "target")

        # Tests with no test_type also go into PCR bucket
        untyped_tests = sample.molecular_tests.filter(
            is_deleted=False,
            test_type__isnull=True,
        ).select_related("target")

        return render(request, "workflow/sample_detail.html", {
            "page_title": f"Sample {sample.code}",
            "page_icon": "sample",
            "sample": sample,
            "events": events,
            "audits": audits,
            "active_tab": tab,
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
            "form": form,
            "sample": sample,
            "modal_title": f"Update Status: {sample.code}",
        })

    def post(self, request, pk):
        sample = get_object_or_404(Sample, pk=pk, is_deleted=False)
        form = AdvanceStatusForm(request.POST)

        if form.is_valid():
            to_state = form.cleaned_data["to_state"]
            notes = form.cleaned_data["notes"]
            old_state = sample.workflow_state
            sample.advance(request.user, to_state, notes)

            # ══════════════════════════════════════════════════════
            # NOTIFY on major status transitions
            # ══════════════════════════════════════════════════════
            try:
                sample_url = reverse("core:sample_detail", args=[sample.pk])
                new_state = sample.workflow_state
                
                # Notify self that status updated
                notify_self(
                    request.user,
                    title=f"Status updated: {sample.code}",
                    message=sample.get_workflow_state_display(),
                    level="info",
                    url=sample_url,
                )

                # Notify assignee when Report Ready
                if new_state == "REPORT_READY" and sample.assigned_to:
                    push_notification(
                        user=sample.assigned_to,
                        title=f"✅ Report Ready: {sample.code}",
                        message=f"{sample.product_name} is ready for delivery.",
                        level="success",
                        url=sample_url,
                    )

                # Notify assignee on rejection
                if new_state == "REJECTED" and sample.assigned_to:
                    push_notification(
                        user=sample.assigned_to,
                        title=f"❌ Sample Rejected: {sample.code}",
                        message=notes or "Sample was rejected during review.",
                        level="error",
                        url=sample_url,
                    )

                # Auto-complete any open reminders when done
                if new_state in ("REPORT_SENT", "REJECTED"):
                    Reminder.objects.filter(
                        sample=sample, is_done=False,
                    ).update(is_done=True)

            except Exception:
                pass

            if self._is_modal(request):
                # Live OOB swap: update status card + close modal + toast
                html = render_to_string(
                    "workflow/partials/_status_card.html",
                    {"sample": sample},
                    request=request,
                )
                toast = render_to_string(
                    "partials/_toast.html",
                    {
                        "message": f"Status updated to {sample.get_workflow_state_display()}.",
                        "level": "success",
                        "oob": True,
                    },
                )
                body = (
                    '<div id="modal-host" hx-swap-oob="innerHTML"></div>'
                    + f'<div id="status-card" hx-swap-oob="outerHTML">{html}</div>'
                    + toast
                )
                return HttpResponse(body)

            messages.success(
                request,
                f"Status updated to {sample.get_workflow_state_display()}.",
            )
            return redirect(reverse("core:sample_detail", args=[sample.pk]))

        return self.render_modal_or_page(request, {
            "form": form,
            "sample": sample,
            "modal_title": f"Update Status: {sample.code}",
        }, status=400)