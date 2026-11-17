"""
Public Customer Portal — Outside the authenticated ILIMS system.
Customers track samples and download reports using a tracking ID + phone number.
No login required. Secured via token matching and rate limiting.
"""
from django.conf import settings
from django.core.mail import EmailMessage
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from apps.core.models import Client, Report, Sample


def verify_tracking(tracking_code, phone):
    """
    Verify that the tracking code matches a sample owned by the client
    with the given phone number. Returns the Sample or None.
    """
    if not tracking_code or not phone:
        return None

    tracking_code = tracking_code.strip().upper()
    phone = phone.strip()

    client = Client.objects.filter(phone=phone, is_deleted=False).first()
    if not client:
        return None

    sample = Sample.objects.filter(
        tracking_code=tracking_code,
        client=client,
        is_deleted=False,
    ).select_related("client", "product_category", "product_type").first()

    return sample


class SimpleRateLimiter:
    """
    In-memory rate limiter: max requests per IP within a sliding window.
    """
    _hits = {}

    @classmethod
    def is_allowed(cls, ip, limit=15, window=60):
        now = timezone.now().timestamp()
        key = str(ip)
        if key not in cls._hits:
            cls._hits[key] = []
        cls._hits[key] = [t for t in cls._hits[key] if now - t < window]
        if len(cls._hits[key]) >= limit:
            return False
        cls._hits[key].append(now)
        return True


@method_decorator(csrf_exempt, name="dispatch")
class CustomerPortalView(View):
    """
    Public landing page for customer sample tracking.
    """

    def get(self, request):
        return render(request, "portal/customer_portal.html", {
            "page_title": "Track Your Sample",
            "page_subtitle": "Enter your tracking ID and registered phone number to view live test results",
        })

    def post(self, request):
        tracking_code = request.POST.get("tracking_code", "").strip()
        phone = request.POST.get("phone", "").strip()

        client_ip = request.META.get("HTTP_X_FORWARDED_FOR") or request.META.get("REMOTE_ADDR", "unknown")
        if not SimpleRateLimiter.is_allowed(client_ip):
            return render(request, "portal/customer_portal.html", {
                "error": "Too many requests. Please wait a minute before trying again.",
                "tracking_code": tracking_code,
                "phone": phone,
            })

        sample = verify_tracking(tracking_code, phone)
        if not sample:
            return render(request, "portal/customer_portal.html", {
                "error": "No matching sample found. Please verify your Tracking ID and phone number.",
                "tracking_code": tracking_code,
                "phone": phone,
            })

        report = Report.objects.filter(sample=sample).first()
        qc_records = sample.qc_records.select_related("reviewer").all()
        attached_tests = sample.attached_tests.filter(is_deleted=False).select_related("test_type", "operator")

        return render(request, "portal/customer_results.html", {
            "sample": sample,
            "report": report,
            "qc_records": qc_records,
            "attached_tests": attached_tests,
            "tracking_code": sample.tracking_code,
            "phone": phone,
        })


@method_decorator(csrf_exempt, name="dispatch")
class CustomerTrackingAPI(View):
    """
    JSON API endpoint for customer mobile tracking or external lookups.
    """

    def get(self, request):
        tracking_code = request.GET.get("tracking_code", "").strip()
        phone = request.GET.get("phone", "").strip()

        client_ip = request.META.get("HTTP_X_FORWARDED_FOR") or request.META.get("REMOTE_ADDR", "unknown")
        if not SimpleRateLimiter.is_allowed(client_ip, limit=20, window=60):
            return JsonResponse({"error": "Rate limit exceeded. Please try again later."}, status=429)

        sample = verify_tracking(tracking_code, phone)
        if not sample:
            return JsonResponse({"error": "Invalid tracking ID or phone number."}, status=404)

        report = Report.objects.filter(sample=sample).first()
        qc_records = sample.qc_records.filter(decision__in=["APPROVED", "REJECTED"]).all()
        attached_tests = sample.attached_tests.filter(is_deleted=False).select_related("test_type")

        data = {
            "tracking_code": sample.tracking_code,
            "sample_code": sample.code,
            "product_name": sample.product_name,
            "client_name": sample.client.name,
            "status": sample.get_workflow_state_display(),
            "status_code": sample.workflow_state,
            "received_date": sample.received_date.isoformat() if sample.received_date else None,
            "due_date": sample.due_date.isoformat() if sample.due_date else None,
            "safety_classification": report.get_safety_class_display() if report else None,
            "report_available": bool(report and report.pdf_file and report.status in ("GENERATED", "APPROVED", "SENT")),
            "report_download_url": f"/portal/download/{sample.tracking_code}/?phone={phone}" if report else None,
            "attached_tests": [
                {
                    "test_name": t.test_type.name,
                    "outcome": t.get_result_outcome_display(),
                    "value": t.result_value or None,
                    "test_date": t.test_date.isoformat() if t.test_date else None,
                }
                for t in attached_tests
            ],
            "qc_decisions": [
                {
                    "decision": qc.get_decision_display(),
                    "safety": qc.get_safety_class_display(),
                    "date": qc.reviewed_at.isoformat() if qc.reviewed_at else None,
                }
                for qc in qc_records
            ],
        }
        return JsonResponse(data)


class CustomerReportDownloadView(View):
    """
    Secure report PDF download. Verifies tracking code + phone before serving file.
    """

    def get(self, request, tracking_code):
        phone = request.GET.get("phone", "").strip()

        sample = verify_tracking(tracking_code, phone)
        if not sample:
            return HttpResponse("Access Denied: Invalid credentials.", status=403)

        report = Report.objects.filter(sample=sample).first()
        if not report:
            return HttpResponse("Report not yet generated.", status=404)

        if report.pdf_file:
            response = HttpResponse(report.pdf_file.read(), content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="{report.code}_FoodSafetyReport.pdf"'
            return response

        # Generate on the fly if needed
        from apps.core.pdf import generate_food_safety_report
        pdf_buf = generate_food_safety_report(report)
        response = HttpResponse(pdf_buf.read(), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{report.code}_FoodSafetyReport.pdf"'
        return response


def send_report_email(report):
    """
    Send the finalized food safety report to the client's registered email.
    """
    client = report.client
    if not client or not client.email:
        return False

    tracking_code = report.sample.tracking_code or "N/A"
    subject = f"Laboratory Analysis Report — Sample {report.sample.code}"
    body = (
        f"Dear {client.contact_person or client.name},\n\n"
        f"The laboratory analysis for your submitted sample has been completed and verified.\n\n"
        f"Sample Identifier: {report.sample.code}\n"
        f"Product / Specimen: {report.sample.product_name}\n"
        f"Tracking ID: {tracking_code}\n"
        f"Safety Classification: {report.get_safety_class_display()}\n\n"
        f"You can view live analysis progress and download the official report via our Customer Portal:\n"
        f"/portal/\n\n"
        f"Login requires your Tracking ID ({tracking_code}) and your registered phone number.\n\n"
        f"Best regards,\n"
        f"{getattr(settings, 'ILIMS_TITLE', 'ILIMS')} Laboratory Services\n"
    )

    try:
        email = EmailMessage(
            subject=subject,
            body=body,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "ilims@example.com"),
            to=[client.email],
        )
        if report.pdf_file:
            email.attach(
                f"{report.code}_Report.pdf",
                report.pdf_file.read(),
                "application/pdf",
            )
        email.send(fail_silently=True)
        return True
    except Exception:
        return False