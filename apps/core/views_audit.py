import hashlib
import json
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views import View
from django.views.generic import ListView

from apps.accounts.decorators import role_required
from apps.core.audit import generate_hash
from apps.core.mixins import HtmxModalMixin, ILIMSViewMixin
from apps.core.models import AuditLog


class AuditListView(ILIMSViewMixin, ListView):
    model = AuditLog
    template_name = "audit/audit_list.html"
    context_object_name = "logs"
    paginate_by = 50
    page_title = "Audit Trail"
    page_subtitle = "Immutable, SHA-256 chained compliance log"
    page_icon = "audit"

    def get_queryset(self):
        qs = AuditLog.objects.select_related("user").order_by("-timestamp")
        action = self.request.GET.get("action", "").strip()
        model_name = self.request.GET.get("model", "").strip()
        q = self.request.GET.get("q", "").strip()

        if action:
            qs = qs.filter(action=action)
        if model_name:
            qs = qs.filter(model_name__iexact=model_name)
        if q:
            qs = qs.filter(
                Q(record_id__icontains=q)
                | Q(user__username__icontains=q)
                | Q(hash__icontains=q)
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["current_action"] = self.request.GET.get("action", "")
        ctx["current_model"] = self.request.GET.get("model", "")
        ctx["current_q"] = self.request.GET.get("q", "")
        ctx["actions"] = AuditLog.objects.values_list("action", flat=True).distinct()
        ctx["models"] = AuditLog.objects.values_list("model_name", flat=True).distinct()
        return ctx

    def get_template_names(self):
        if getattr(self.request, "htmx", False) and not getattr(self.request.htmx, "boosted", False):
            return ["audit/partials/_audit_list_rows.html"]
        return [self.template_name]


class AuditDetailModalView(HtmxModalMixin, LoginRequiredMixin, View):
    """View full cryptographic hash and diff changes in modal or standalone page."""
    modal_template = "audit/partials/_modal_audit_diff.html"
    page_template = "audit/audit_diff_page.html"
    modal_title = "Audit Record Details"

    def get(self, request, pk):
        log = get_object_or_404(AuditLog.objects.select_related("user"), pk=pk)
        return self.render_modal_or_page(request, {
            "log": log,
            "modal_title": f"Audit Log · {log.action} {log.model_name}",
        })


class AuditVerifyIntegrityView(LoginRequiredMixin, View):
    """
    Cryptographic verification endpoint.
    Recalculates every SHA-256 hash in sequence from GENESIS to the latest record
    to verify that no database rows have been altered or deleted.
    """
    def get(self, request):
        logs = AuditLog.objects.order_by("timestamp", "id")
        total = logs.count()
        if total == 0:
            return render(request, "audit/audit_verify.html", {
                "status": "EMPTY",
                "message": "No audit records in the database.",
            })

        tampered_record = None
        computed_previous_hash = "GENESIS"

        for record in logs:
            if record.previous_hash != computed_previous_hash:
                tampered_record = record
                break

            user_id = str(record.user_id) if record.user_id else "SYSTEM"
            changes_json = json.dumps(record.changes, cls=DjangoJSONEncoder, sort_keys=True)
            recalculated = generate_hash(
                computed_previous_hash,
                record.timestamp.isoformat(),
                user_id,
                record.action,
                record.model_name,
                record.record_id,
                changes_json,
            )

            if recalculated != record.hash:
                tampered_record = record
                break

            computed_previous_hash = record.hash

        return render(request, "audit/audit_verify.html", {
            "is_valid": tampered_record is None,
            "tampered_record": tampered_record,
            "total_verified": total,
            "latest_hash": computed_previous_hash,
            "page_title": "Audit Chain Verification",
            "page_subtitle": "Cryptographic proof of non-repudiation",
            "page_icon": "audit",
        })