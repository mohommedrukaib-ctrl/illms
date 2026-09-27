from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.files.base import ContentFile
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import ListView

from apps.core.audit import log_audit
from apps.core.forms_reports import ReportGenerateForm, ReportSendForm
from apps.core.mixins import HtmxModalMixin, ILIMSViewMixin
from apps.core.models import (
    AuditLog, Client, MolecularTest, QcRecord, Report, Sample,
    next_code,
)
from apps.core.pdf import generate_food_safety_report


def _full_reload(url):
    body = (
        f'<div id="modal-host" hx-swap-oob="innerHTML"></div>'
        f'<meta http-equiv="refresh" content="0;url={url}">'
    )
    response = HttpResponse(body, status=200)
    response["HX-Redirect"] = url
    return response


class ReportListView(ILIMSViewMixin, ListView):
    model = Report
    template_name = "reports/report_list.html"
    context_object_name = "reports"
    paginate_by = 40
    page_title = "Reports"
    page_subtitle = "Food-safety analysis reports"
    page_icon = "report"

    def get_queryset(self):
        qs = Report.objects.select_related(
            "sample", "client", "generated_by"
        ).order_by("-created_at")
        status = self.request.GET.get("status", "").upper()
        if status in dict(Report.Status.choices):
            qs = qs.filter(status=status)
        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(code__icontains=q)
                | Q(sample__code__icontains=q)
                | Q(client__name__icontains=q)
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["current_status"] = self.request.GET.get("status", "")
        ctx["current_q"] = self.request.GET.get("q", "")
        return ctx

    def get_template_names(self):
        if getattr(self.request, "htmx", False) and not getattr(
            self.request.htmx, "boosted", False
        ):
            return ["reports/partials/_report_list_rows.html"]
        return [self.template_name]


class ReportGenerateView(HtmxModalMixin, LoginRequiredMixin, View):
    modal_template = "reports/partials/_modal_report_generate.html"
    page_template = "reports/report_generate_page.html"
    modal_title = "Generate Report"

    def _get_sample(self, request):
        sample_pk = request.GET.get("sample") or request.POST.get("sample")
        if sample_pk:
            return get_object_or_404(Sample, pk=sample_pk, is_deleted=False)
        return None

    def get(self, request):
        sample = self._get_sample(request)
        if not sample:
            messages.error(request, "No sample specified.")
            return redirect("core:sample_list")

        report, created = Report.objects.get_or_create(
            sample=sample,
            defaults={
                "code": next_code("REPORT", sample.client.country if sample.client_id else None),
                "client": sample.client,
                "generated_by": request.user,
            },
        )

        # Pre-fill safety class from latest QC
        latest_qc = sample.qc_records.filter(decision="APPROVED").first()
        if latest_qc and report.safety_class == "NOT_APPLICABLE":
            report.safety_class = latest_qc.safety_class
            report.save(update_fields=["safety_class"])

        form = ReportGenerateForm(instance=report)
        return self.render_modal_or_page(request, {
            "form": form,
            "sample": sample,
            "report": report,
            "modal_title": f"Generate Report · {sample.code}",
        })

    def post(self, request):
        sample = self._get_sample(request)
        if not sample:
            messages.error(request, "No sample specified.")
            return redirect("core:sample_list")

        report, created = Report.objects.get_or_create(
            sample=sample,
            defaults={
                "code": next_code("REPORT", sample.client.country if sample.client_id else None),
                "client": sample.client,
                "generated_by": request.user,
            },
        )

        form = ReportGenerateForm(request.POST, instance=report)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.generated_by = request.user
            obj.status = Report.Status.GENERATED

            # Generate PDF
            pdf_buf = generate_food_safety_report(obj)
            filename = f"{obj.code}_{sample.code}.pdf"
            obj.pdf_file.save(filename, ContentFile(pdf_buf.read()), save=False)
            obj.save()

            log_audit(request.user, "EXPORT", obj, {"action": "report_generated"})

            # Advance sample to Report Ready
            if sample.workflow_state in ("REPORT_PREP", "TESTING", "ANALYSIS"):
                sample.advance(request.user, "REPORT_READY",
                               notes=f"Report {obj.code} generated")

            messages.success(request, f"Report {obj.code} generated successfully.")
            if self._is_modal(request):
                return _full_reload(reverse("core:report_detail", args=[obj.pk]))
            return redirect("core:report_detail", pk=obj.pk)

        return self.render_modal_or_page(request, {
            "form": form,
            "sample": sample,
            "report": report,
            "modal_title": f"Generate Report · {sample.code}",
        }, status=400)


class ReportDetailView(ILIMSViewMixin, View):
    def get(self, request, pk):
        report = get_object_or_404(
            Report.objects.select_related("sample", "client", "generated_by", "approved_by"),
            pk=pk,
        )
        sample = report.sample
        tests = sample.molecular_tests.filter(is_deleted=False).select_related(
            "test_type", "target", "operator"
        )
        qc_records = sample.qc_records.select_related("reviewer", "test").all()
        extractions = sample.dna_extractions.filter(is_deleted=False).select_related(
            "method", "operator"
        )
        send_form = ReportSendForm(
            initial={"recipient_email": report.sent_to or sample.client.email}
        )
        return render(request, "reports/report_detail.html", {
            "page_title": report.code,
            "page_icon": "report",
            "report": report,
            "sample": sample,
            "tests": tests,
            "qc_records": qc_records,
            "extractions": extractions,
            "send_form": send_form,
        })


class ReportDownloadView(LoginRequiredMixin, View):
    def get(self, request, pk):
        report = get_object_or_404(Report, pk=pk)
        if report.pdf_file:
            response = HttpResponse(report.pdf_file.read(), content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="{report.code}.pdf"'
            return response
        # Regenerate on the fly if no file
        pdf_buf = generate_food_safety_report(report)
        response = HttpResponse(pdf_buf.read(), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{report.code}.pdf"'
        return response


class ReportSendView(LoginRequiredMixin, View):
    def post(self, request, pk):
        report = get_object_or_404(Report, pk=pk)
        form = ReportSendForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["recipient_email"]
            report.sent_to = email
            report.sent_at = timezone.now()
            report.status = Report.Status.SENT
            report.save(update_fields=["sent_to", "sent_at", "status"])
                        # Send email to client
            from apps.core.views_portal import send_report_email
            send_report_email(report)

            # Advance sample
            sample = report.sample
            if sample.workflow_state == "REPORT_READY":
                sample.advance(request.user, "REPORT_SENT",
                               notes=f"Report {report.code} sent to {email}")

            log_audit(request.user, "EXPORT", report, {"action": "report_sent", "to": email})

            # TODO: Actually send email via Celery / django.core.mail in Phase 8
            messages.success(request, f"Report marked as sent to {email}.")
        else:
            messages.error(request, "Invalid email address.")
        return redirect("core:report_detail", pk=pk)

class DetectionLogView(ILIMSViewMixin, ListView):
    """Deliverable 3: Microorganism Detection Log."""
    template_name = "reports/detection_log.html"
    context_object_name = "detections"
    paginate_by = 100
    page_title = "Microorganism Detection Log"
    page_subtitle = "All pathogen detections across samples"
    page_icon = "microbe"

    def get_queryset(self):
        from apps.core.models import TestResult
        qs = TestResult.objects.filter(
            is_deleted=False,
            detection="DETECTED",
        ).select_related(
            "microorganism", "test", "test__sample", "test__sample__client"
        ).order_by("-created_at")
        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(microorganism__name__icontains=q)
                | Q(test__sample__code__icontains=q)
            )
        return qs


class QcComplianceLogView(ILIMSViewMixin, ListView):
    """Deliverable 5: QC Compliance Log."""
    template_name = "reports/qc_compliance_log.html"
    context_object_name = "records"
    paginate_by = 100
    page_title = "QC Compliance Log"
    page_subtitle = "Complete QC review history for accreditation"
    page_icon = "qc"

    def get_queryset(self):
        return QcRecord.objects.exclude(decision="PENDING").select_related(
            "test", "sample", "reviewer"
        ).order_by("-reviewed_at")


class AuditExportView(LoginRequiredMixin, View):
    """Deliverable 6: Export the cryptographic audit trail as CSV."""
    def get(self, request):
        import csv
        logs = AuditLog.objects.select_related("user").order_by("-timestamp")[:5000]
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="audit_trail.csv"'
        writer = csv.writer(response)
        writer.writerow(["Timestamp", "User", "Action", "Model", "Record", "Changes", "Hash"])
        for log in logs:
            writer.writerow([
                log.timestamp.isoformat(),
                log.user.username if log.user else "SYSTEM",
                log.action,
                log.model_name,
                log.record_id,
                str(log.changes)[:200],
                log.hash[:16] + "...",
            ])
        log_audit(request.user, "EXPORT", request.user, {"action": "audit_export"})
        return response