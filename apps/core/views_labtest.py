"""
Laboratory Workbench Views

Sample-centric diagnostic workbench:
- LabTestListView: Lists active samples requiring testing.
- LabTestDetailView: Streamlined workbench displaying sample details and allowing 
  analysts to attach multiple test results directly.
- LabTestCreateView: Redirects to sample intake with return to workbench.
"""
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import ListView

from apps.core.mixins import ILIMSViewMixin
from apps.core.models import Sample


class LabTestListView(ILIMSViewMixin, ListView):
    """
    Diagnostic Workbench: Lists all active samples that are currently 
    undergoing or pending testing.
    """

    model = Sample
    template_name = "labtest/labtest_list.html"
    context_object_name = "samples"
    paginate_by = 50
    page_title = "Laboratory Workbench"
    page_subtitle = "Select an active sample to manage and attach multiple test results"
    page_icon = "flask"

    def get_queryset(self):
        qs = Sample.objects.filter(
            is_deleted=False,
        ).exclude(
            workflow_state__in=["REPORT_SENT", "REJECTED"]
        ).select_related(
            "client", "product_category", "product_type", "requested_test", "assigned_to"
        ).order_by("-received_date", "-created_at")

        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(code__icontains=q)
                | Q(product_name__icontains=q)
                | Q(client__name__icontains=q)
                | Q(requested_test__name__icontains=q)
            )

        state = self.request.GET.get("state", "").strip()
        if state:
            qs = qs.filter(workflow_state=state)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["current_q"] = self.request.GET.get("q", "")
        ctx["current_state"] = self.request.GET.get("state", "")
        ctx["state_choices"] = [
            ("RECEIVED", "Sample Received"),
            ("TESTING", "Testing In Progress"),
            ("ANALYSIS", "Analysis"),
            ("REPORT_PREP", "Report Preparation"),
            ("REPORT_READY", "Report Ready"),
        ]
        return ctx

    def get_template_names(self):
        if getattr(self.request, "htmx", False) and not getattr(
            self.request.htmx, "boosted", False
        ):
            return ["labtest/partials/_labtest_list_rows.html"]
        return [self.template_name]


class LabTestCreateView(LoginRequiredMixin, View):
    """Redirect to sample intake since tests are attached directly to samples."""

    def get(self, request):
        return redirect(f"{reverse('core:sample_create')}?next={reverse('core:labtest_list')}")


class LabTestDetailView(ILIMSViewMixin, View):
    """
    Focused Laboratory Workbench for a single sample.
    Displays sample details and lists all attached tests with options to add more.
    """

    def get(self, request, pk):
        sample = get_object_or_404(
            Sample.objects.select_related(
                "client", "product_category", "product_type", "requested_test", "assigned_to", "laboratory"
            ),
            pk=pk, is_deleted=False,
        )

        attached_tests = sample.attached_tests.filter(is_deleted=False).select_related("test_type", "operator")

        return render(request, "labtest/labtest_detail.html", {
            "page_title": f"Workbench: {sample.code}",
            "page_icon": "flask",
            "sample": sample,
            "attached_tests": attached_tests,
            "is_locked": sample.is_locked_for_new_tests(),
        })