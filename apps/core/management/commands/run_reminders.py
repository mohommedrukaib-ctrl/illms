"""
Cron management command: creates overdue/due-soon reminders,
pushes notifications, and sends email digests.

Usage:
    python manage.py run_reminders

Cron (every 15 minutes):
    */15 * * * * cd /path/to/ilims && venv/bin/python manage.py run_reminders
"""
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.utils import timezone

from apps.core.models import (
    Notification, QcRecord, Reminder, Sample, SystemSetting,
)
from apps.core.notifications import push_notification


class Command(BaseCommand):
    help = "Scan samples and QC records, create reminders, push notifications, send email digests."

    def handle(self, *args, **options):
        today = timezone.now().date()
        sla = SystemSetting.get_settings().sla_settings
        tat_normal = sla.get("tat_normal_days", 5)
        tat_urgent = sla.get("tat_urgent_days", 2)

        created_count = 0
        notified_count = 0

        # ── 1. Scan active samples for due/overdue ──
        active_samples = Sample.objects.filter(
            is_deleted=False,
            workflow_state__in=["RECEIVED", "TESTING", "ANALYSIS", "REPORT_PREP"],
        ).select_related("client", "assigned_to")

        for sample in active_samples:
            if not sample.due_date:
                continue

            days_left = (sample.due_date - today).days
            priority = "URGENT" if sample.priority == "URGENT" else "NORMAL"
            tat = tat_urgent if sample.priority == "URGENT" else tat_normal

            if days_left < 0:
                kind = "OVERDUE"
                title = f"OVERDUE: Report for Sample {sample.code}"
                msg = (
                    f"Report for Sample {sample.code} ({sample.product_name}) "
                    f"was due on {sample.due_date.strftime('%d %B')}. "
                    f"Client: {sample.client.name}."
                )
                priority = "URGENT"
            elif days_left == 0:
                kind = "DUE_TODAY"
                title = f"DUE TODAY: Report for Sample {sample.code}"
                msg = (
                    f"Report for Sample {sample.code} must be submitted to "
                    f"{sample.client.name} today."
                )
            elif days_left <= 2:
                kind = "DUE_SOON"
                title = f"Due Soon: Sample {sample.code}"
                msg = (
                    f"Report for Sample {sample.code} must be submitted to "
                    f"{sample.client.name} on {sample.due_date.strftime('%d %B')}."
                )
            else:
                continue

            # Avoid duplicates: skip if an active reminder of same kind exists
            existing = Reminder.objects.filter(
                sample=sample, kind=kind, is_done=False
            ).exists()
            if existing:
                continue

            reminder = Reminder.objects.create(
                kind=kind,
                priority=priority,
                title=title,
                message=msg,
                sample=sample,
                assigned_to=sample.assigned_to,
                due_date=sample.due_date,
            )
            created_count += 1

            # Push notification to assigned user
            if sample.assigned_to:
                push_notification(
                    sample.assigned_to,
                    title=f"🔔 {title}",
                    message=msg,
                    level="warning" if kind == "OVERDUE" else "info",
                    url=f"/samples/{sample.pk}/",
                )
                notified_count += 1

        # ── 2. Scan pending QC records ──
        pending_qc = QcRecord.objects.filter(
            decision="PENDING",
        ).select_related("test", "test__operator", "sample")

        for qc in pending_qc:
            existing = Reminder.objects.filter(
                qc_record=qc, kind="QC_PENDING", is_done=False
            ).exists()
            if existing:
                continue

            Reminder.objects.create(
                kind="QC_PENDING",
                priority="HIGH",
                title=f"QC Pending: Test {qc.test.code}",
                message=(
                    f"Molecular test {qc.test.code} for sample {qc.sample.code} "
                    f"is awaiting QC review."
                ),
                qc_record=qc,
                sample=qc.sample,
                due_date=today,
            )
            created_count += 1

            # Notify all QC officers
            from django.contrib.auth import get_user_model
            User = get_user_model()
            qc_officers = User.objects.filter(
                role="QC_OFFICER", is_active=True, is_deleted=False
            )
            for officer in qc_officers:
                push_notification(
                    officer,
                    title="🔔 QC Review Required",
                    message=f"Test {qc.test.code} needs your review.",
                    level="info",
                    url="/qc/",
                )
                notified_count += 1

        # ── 3. Send email digest to users with overdue reminders ──
        self._send_email_digests(today)

        self.stdout.write(
            self.style.SUCCESS(
                f"Reminders: {created_count} created, "
                f"{notified_count} notifications pushed."
            )
        )

    def _send_email_digests(self, today):
        """Send a daily email digest to users who have overdue reminders."""
        from django.contrib.auth import get_user_model
        User = get_user_model()

        users_with_overdue = User.objects.filter(
            reminders__is_done=False,
            reminders__due_date__lte=today,
            is_active=True,
        ).distinct()

        for user in users_with_overdue:
            overdue = Reminder.objects.filter(
                assigned_to=user, is_done=False, due_date__lte=today
            ).order_by("due_date")[:10]

            if not overdue.exists():
                continue

            lines = [f"Hi {user.get_short_name()},\n"]
            lines.append("You have the following overdue or due-today reminders:\n")
            for r in overdue:
                lines.append(f"  • [{r.get_kind_display()}] {r.title}")
                if r.message:
                    lines.append(f"    {r.message}")
            lines.append(f"\nLog in to ILIMS to take action: {settings.LOGIN_URL}")

            body = "\n".join(lines)

            try:
                send_mail(
                    subject=f"ILIMS Reminder Digest — {today.strftime('%d %B %Y')}",
                    message=body,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=True,
                )
            except Exception:
                pass