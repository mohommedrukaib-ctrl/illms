from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import ListView

from apps.core.mixins import ILIMSViewMixin
from apps.core.models import Notification, Reminder


def _bell_context(user):
    latest = list(
        Notification.objects.filter(user=user).order_by("-created_at")[:3]
    )
    unread_count = Notification.objects.filter(user=user, is_read=False).count()
    return {"latest": latest, "unread": latest, "unread_count": unread_count}


# ══════════════════════════════════════════════════════════════════
# REMINDERS
# ══════════════════════════════════════════════════════════════════

class ReminderListView(ILIMSViewMixin, ListView):
    model = Reminder
    template_name = "reminders/reminder_list.html"
    context_object_name = "reminders"
    paginate_by = 50
    page_title = "Reminders"
    page_subtitle = "Deadline tracking and action items"
    page_icon = "reminder"

    def get_queryset(self):
        tab = self.request.GET.get("tab", "today")
        today = timezone.now().date()
        user = self.request.user

        # Your open reminders (not actively snoozed into the future)
        base = Reminder.objects.filter(
            assigned_to=user,
            is_done=False,
        ).filter(
            Q(snoozed_until__isnull=True) | Q(snoozed_until__lte=today)
        ).select_related("sample", "sample__client", "assigned_to")

        if tab == "today":
            qs = base.filter(due_date=today)
        elif tab == "upcoming":
            qs = base.filter(
                due_date__gt=today,
                due_date__lte=today + timedelta(days=7),
            )
        elif tab == "overdue":
            qs = base.filter(due_date__lt=today)
        elif tab == "priority":
            qs = base.filter(priority__in=["HIGH", "URGENT"])
        elif tab == "done":
            qs = Reminder.objects.filter(
                assigned_to=user, is_done=True
            ).select_related("sample", "sample__client", "assigned_to")
        else:
            qs = base.filter(due_date=today)

        return qs.order_by("due_date", "-priority")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        today = timezone.now().date()
        user = self.request.user

        base_qs = Reminder.objects.filter(
            assigned_to=user,
            is_done=False,
        ).filter(
            Q(snoozed_until__isnull=True) | Q(snoozed_until__lte=today)
        )

        ctx["active_tab"] = self.request.GET.get("tab", "today")
        ctx["today"] = today
        ctx["counts"] = {
            "today": base_qs.filter(due_date=today).count(),
            "upcoming": base_qs.filter(
                due_date__gt=today,
                due_date__lte=today + timedelta(days=7),
            ).count(),
            "overdue": base_qs.filter(due_date__lt=today).count(),
            "priority": base_qs.filter(priority__in=["HIGH", "URGENT"]).count(),
        }
        return ctx

    def get_template_names(self):
        if getattr(self.request, "htmx", False) and not getattr(
            self.request.htmx, "boosted", False
        ):
            return ["reminders/partials/_reminder_rows.html"]
        return [self.template_name]


class ReminderActionView(LoginRequiredMixin, View):
    def post(self, request, pk, action):
        reminder = get_object_or_404(Reminder, pk=pk, assigned_to=request.user)
        today = timezone.now().date()

        if action == "done":
            reminder.is_done = True
            reminder.save(update_fields=["is_done", "updated_at"])
            messages.success(request, "Reminder marked as done.")

        elif action == "snooze_1d":
            reminder.snoozed_until = today + timedelta(days=1)
            reminder.due_date = reminder.snoozed_until
            reminder.save(update_fields=["snoozed_until", "due_date", "updated_at"])
            messages.info(request, "Snoozed for 1 day.")

        elif action == "snooze_3d":
            reminder.snoozed_until = today + timedelta(days=3)
            reminder.due_date = reminder.snoozed_until
            reminder.save(update_fields=["snoozed_until", "due_date", "updated_at"])
            messages.info(request, "Snoozed for 3 days.")

        elif action == "open":
            if reminder.sample_id:
                return redirect("core:sample_detail", pk=reminder.sample_id)
            if reminder.qc_record_id:
                return redirect("core:qc_review", pk=reminder.qc_record_id)

        next_url = request.POST.get(
            "next",
            request.META.get("HTTP_REFERER", reverse("core:reminders_list")),
        )
        return redirect(next_url)


# ══════════════════════════════════════════════════════════════════
# NOTIFICATIONS
# ══════════════════════════════════════════════════════════════════

class NotificationListView(ILIMSViewMixin, ListView):
    model = Notification
    template_name = "reminders/notification_list.html"
    context_object_name = "notifications"
    paginate_by = 50
    page_title = "Notifications"
    page_subtitle = "Your alerts and system messages"
    page_icon = "bell"

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user).order_by("-created_at")


class NotificationMarkReadView(LoginRequiredMixin, View):
    """Mark one or all read. HTMX from bell → refresh last 3."""

    def post(self, request):
        notif_id = request.POST.get("id")
        if notif_id:
            Notification.objects.filter(pk=notif_id, user=request.user).update(is_read=True)
        else:
            Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)

        if request.headers.get("HX-Request"):
            return render(
                request,
                "reminders/partials/_bell_dropdown.html",
                _bell_context(request.user),
            )

        return redirect(
            request.META.get("HTTP_REFERER", reverse("core:notifications_list"))
        )


class NotificationPollView(LoginRequiredMixin, View):
    """Topbar: last 3 notifications + unread badge."""

    def get(self, request):
        return render(
            request,
            "reminders/partials/_bell_dropdown.html",
            _bell_context(request.user),
        )