from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views import View

from apps.core.audit import get_changes, log_audit
from apps.core.forms_sample_test import SampleTestForm
from apps.core.mixins import HtmxModalMixin, ILIMSViewMixin
from apps.core.models import LabMethod, Reminder, Sample, SampleTest, next_code
from apps.core.notifications import push_notification


def _full_reload(url):
    body = (
        '<div id="modal-host" hx-swap-oob="innerHTML"></div>'
        f'<meta http-equiv="refresh" content="0;url={url}">'
    )
    response = HttpResponse(body, status=200)
    response["HX-Redirect"] = url
    response["HX-Trigger"] = "ilims:refresh"
    return response


def _create_test_reminder(*, sample, assignee, request_user, title, message=""):
    """Create a workbench reminder + optional notification for a new test."""
    if not sample or not assignee:
        return

    due = sample.due_date or timezone.now().date()
    today = timezone.now().date()
    days = (due - today).days

    if days < 0:
        kind = Reminder.Kind.OVERDUE
    elif days == 0:
        kind = Reminder.Kind.DUE_TODAY
    elif days <= 2:
        kind = Reminder.Kind.DUE_SOON
    else:
        kind = Reminder.Kind.CUSTOM

    priority = (
        Reminder.Priority.HIGH
        if getattr(sample, "priority", "") == "URGENT"
        else Reminder.Priority.NORMAL
    )

    # Don't spam duplicate open reminders
    if Reminder.objects.filter(
        sample=sample,
        assigned_to=assignee,
        title=title,
        is_done=False,
    ).exists():
        return

    Reminder.objects.create(
        kind=kind,
        priority=priority,
        title=title,
        message=message or f"Sample {sample.code} · {sample.product_name}",
        sample=sample,
        assigned_to=assignee,
        due_date=due,
    )

    if assignee != request_user:
        push_notification(
            user=assignee,
            title=title,
            message=message or f"New test work item for {sample.code}",
            level="info",
            url=reverse("core:sample_detail", args=[sample.pk]),
        )


def _render_tests_section_swap(request, sample, message="Test saved."):
    """Live OOB swap for the sample detail tests section without full page reload."""
    attached_tests = sample.attached_tests.filter(is_deleted=False).select_related(
        "test_type", "operator"
    )
    html = render_to_string(
        "workflow/partials/_sample_tests_section.html",
        {
            "sample": sample,
            "attached_tests": attached_tests,
            "is_locked": sample.is_locked_for_new_tests(),
        },
        request=request,
    )
    toast = render_to_string(
        "partials/_toast.html",
        {"message": message, "level": "success", "oob": True},
    )
    body = (
        '<div id="modal-host" hx-swap-oob="innerHTML"></div>'
        f'<div id="sample-tests-section" hx-swap-oob="outerHTML">{html}</div>'
        + toast
    )
    return HttpResponse(body)


class SampleTestAttachView(HtmxModalMixin, LoginRequiredMixin, View):
    modal_template = "workflow/partials/_modal_sample_test_form.html"
    page_template = "workflow/sample_test_form_page.html"
    modal_title = "Attach Test to Sample"

    def _get_instance(self, request):
        edit_pk = request.GET.get("edit") or request.POST.get("edit")
        if edit_pk:
            try:
                return SampleTest.objects.get(pk=edit_pk, is_deleted=False)
            except (SampleTest.DoesNotExist, ValueError):
                pass
        return None

    def get(self, request, sample_pk):
        sample = get_object_or_404(Sample, pk=sample_pk, is_deleted=False)
        instance = self._get_instance(request)
        title = (
            f"Edit Test: {instance.test_type.name}"
            if instance
            else f"Attach Test · {sample.code}"
        )
        next_url = request.GET.get(
            "next", reverse("core:sample_detail", args=[sample.pk])
        )

        form = SampleTestForm(
            instance=instance, next_url=next_url, current_user=request.user
        )
        return self.render_modal_or_page(
            request,
            {
                "form": form,
                "sample": sample,
                "instance": instance,
                "next_url": next_url,
                "modal_title": title,
                "edit_pk": str(instance.pk) if instance else "",
            },
        )

    def post(self, request, sample_pk):
        sample = get_object_or_404(Sample, pk=sample_pk, is_deleted=False)
        instance = self._get_instance(request)
        next_url = request.POST.get(
            "next", reverse("core:sample_detail", args=[sample.pk])
        )
        form = SampleTestForm(
            request.POST,
            request.FILES,
            instance=instance,
            next_url=next_url,
            current_user=request.user,
        )

        if form.is_valid():
            test_type_name = form.cleaned_data["test_type_name"]
            test_type, _created = LabMethod.objects.get_or_create(
                name=test_type_name,
                defaults={"category": "GENERAL", "is_active": True},
            )

            test_obj = form.save(commit=False)
            test_obj.sample = sample
            test_obj.test_type = test_type

            if not instance:
                country = sample.client.country if sample.client_id else None
                test_obj.code = next_code("TEST", country)

            if not test_obj.operator_id:
                test_obj.operator = request.user

            test_obj.save()

            action = "UPDATE" if instance else "CREATE"
            log_audit(
                request.user,
                action,
                test_obj,
                get_changes(
                    instance,
                    test_obj,
                    ["test_type_id", "result_outcome", "result_value", "attachment"],
                ),
            )

            # Advance sample to TESTING if still RECEIVED
            if sample.workflow_state == Sample.WorkflowState.RECEIVED:
                sample.advance(
                    request.user,
                    Sample.WorkflowState.TESTING,
                    notes=f"Attached test: {test_type.name}",
                )

            # ── NEW: Reminder + notification only when attaching (not editing) ──
            if not instance:
                assignee = (
                    test_obj.operator
                    or sample.assigned_to
                    or request.user
                )
                _create_test_reminder(
                    sample=sample,
                    assignee=assignee,
                    request_user=request.user,
                    title=f"Complete test: {test_type.name} ({sample.code})",
                    message=(
                        f"Test {test_obj.code} · {sample.product_name} · "
                        f"Client: {sample.client.name if sample.client_id else '—'}"
                    ),
                )

            msg = f"Test '{test_type.name}' attached to {sample.code}."
            if self._is_modal(request):
                return _render_tests_section_swap(request, sample, message=msg)

            messages.success(request, msg)
            return redirect(next_url)

        return self.render_modal_or_page(
            request,
            {
                "form": form,
                "sample": sample,
                "instance": instance,
                "next_url": next_url,
                "modal_title": "Attach Test to Sample",
                "edit_pk": str(instance.pk) if instance else "",
            },
            status=400,
        )