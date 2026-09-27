from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import ListView

from apps.core.audit import get_changes, log_audit
from apps.core.forms_qc import QcReviewForm
from apps.core.mixins import HtmxModalMixin, ILIMSViewMixin
from apps.core.models import QcRecord


def _full_reload(url):
    body = (
        '<div id="modal-host" hx-swap-oob="innerHTML"></div>'
        f'<meta http-equiv="refresh" content="0;url={url}">'
    )
    response = HttpResponse(body, status=200)
    response["HX-Redirect"] = url
    response["HX-Trigger"] = "ilims:refresh"
    return response


class QcQueueView(ILIMSViewMixin, ListView):
    """
    QC Verification Queue.
    Lists all samples awaiting QC review. Auto-populated when samples
    advance to 'Report Preparation' stage.
    """

    model = QcRecord
    template_name = "qc/qc_queue.html"
    context_object_name = "records"
    paginate_by = 40
    page_title = "QC Verification Queue"
    page_subtitle = "Review and approve completed sample test results"
    page_icon = "qc"

    def get_queryset(self):
        status_filter = self.request.GET.get("status", "PENDING").upper()
        qs = QcRecord.objects.select_related(
            "sample", "sample__client", "sample__requested_test", "reviewer",
        ).order_by("-created_at")

        if status_filter in dict(QcRecord.Decision.choices):
            qs = qs.filter(decision=status_filter)

        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(code__icontains=q)
                | Q(sample__code__icontains=q)
                | Q(sample__client__name__icontains=q)
                | Q(sample__product_name__icontains=q)
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["current_status"] = self.request.GET.get("status", "PENDING").upper()
        ctx["current_q"] = self.request.GET.get("q", "")
        ctx["counts"] = {
            "pending": QcRecord.objects.filter(decision="PENDING").count(),
            "approved": QcRecord.objects.filter(decision="APPROVED").count(),
            "rejected": QcRecord.objects.filter(decision="REJECTED").count(),
            "rework": QcRecord.objects.filter(decision="REWORK").count(),
        }
        return ctx

    def get_template_names(self):
        if getattr(self.request, "htmx", False) and not getattr(
            self.request.htmx, "boosted", False
        ):
            return ["qc/partials/_qc_queue_rows.html"]
        return [self.template_name]


class QcReviewView(HtmxModalMixin, LoginRequiredMixin, View):
    """
    QC Review Workbench.
    Shows all attached tests for the sample so the QC officer can verify
    outcomes, check attachments, and make a final safety decision.
    """

    modal_template = "qc/partials/_modal_qc_review.html"
    page_template = "qc/qc_review_page.html"
    modal_title = "QC Review"

    def _get_record(self, pk):
        return get_object_or_404(
            QcRecord.objects.select_related(
                "sample", "sample__client", "sample__requested_test", "reviewer",
            ),
            pk=pk,
        )

    def get(self, request, pk):
        record = self._get_record(pk)
        sample = record.sample
        blocked_reason = record.four_eyes_blocked_reason(request.user)

        # Gather all attached tests for this sample
        attached_tests = sample.attached_tests.filter(
            is_deleted=False
        ).select_related("test_type", "operator")

        form = QcReviewForm(instance=record)
        return self.render_modal_or_page(request, {
            "record": record,
            "sample": sample,
            "form": form,
            "attached_tests": attached_tests,
            "blocked_reason": blocked_reason,
            "modal_title": f"QC Review · {sample.code}",
        })

    def post(self, request, pk):
        record = self._get_record(pk)
        sample = record.sample

        if not record.can_be_reviewed_by(request.user):
            messages.error(request, record.four_eyes_blocked_reason(request.user))
            if self._is_modal(request):
                return _full_reload(reverse("core:qc_queue"))
            return redirect("core:qc_queue")

        old_snapshot = QcRecord.objects.get(pk=record.pk)
        form = QcReviewForm(request.POST, instance=record)

        if form.is_valid():
            obj = form.save(commit=False)
            obj.reviewer = request.user
            obj.reviewed_at = timezone.now()
            obj.save()

            changes = get_changes(
                old_snapshot, obj,
                ["decision", "safety_class", "review_notes"],
            )
            action_label = "APPROVE" if obj.decision == "APPROVED" else "UPDATE"
            log_audit(request.user, action_label, obj, changes)

            # Auto-advance sample based on QC decision
            if obj.decision == "APPROVED":
                if sample.workflow_state in ("REPORT_PREP", "TESTING", "ANALYSIS"):
                    sample.advance(
                        request.user, "REPORT_READY",
                        notes=f"QC {obj.code} approved · {obj.get_safety_class_display()}",
                    )
            elif obj.decision == "REJECTED":
                sample.advance(
                    request.user, "REJECTED",
                    notes=f"QC {obj.code} rejected. {obj.review_notes}",
                )
            elif obj.decision == "REWORK":
                sample.advance(
                    request.user, "TESTING",
                    notes=f"QC {obj.code} requested rework. {obj.review_notes}",
                )

            messages.success(
                request,
                f"QC review saved: {obj.get_decision_display()} for {sample.code}.",
            )
            if self._is_modal(request):
                return _full_reload(reverse("core:qc_queue"))
            return redirect("core:qc_queue")

        attached_tests = sample.attached_tests.filter(
            is_deleted=False
        ).select_related("test_type", "operator")

        return self.render_modal_or_page(request, {
            "record": record,
            "sample": sample,
            "form": form,
            "attached_tests": attached_tests,
            "blocked_reason": record.four_eyes_blocked_reason(request.user),
            "modal_title": f"QC Review · {sample.code}",
        }, status=400)