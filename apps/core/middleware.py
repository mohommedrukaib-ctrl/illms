
from django.http import Http404

from django.shortcuts import render

from django.urls import resolve
from django.utils.cache import add_never_cache_headers
from django.utils.deprecation import MiddlewareMixin


from apps.core.models import flag_enabled


class NoCacheMiddleware(MiddlewareMixin):
    """Add no-cache headers to all authenticated HTML responses."""


class NoCacheMiddleware(MiddlewareMixin):
    """Add no-cache headers to all authenticated HTML responses to prevent stale state caching."""


    def process_response(self, request, response):
        if hasattr(request, "user") and request.user.is_authenticated:
            content_type = response.get("Content-Type", "")
            if "text/html" in content_type:
                add_never_cache_headers(response)
        return response


class FeatureFlagMiddleware:

    """Blocks direct URL requests to routes tied to disabled features."""

    ROUTE_FLAG_MAP = {
        "batches_list": "module.batches",
        "dna_list": "module.dna_extraction",
        "dna_create": "module.dna_extraction",
        "dna_detail": "module.dna_extraction",
        "test_list": "module.pcr",
        "test_create": "module.pcr",
        "test_detail": "module.pcr",
        "microbe_list": "module.microorganism_id",
        "microbe_create": "module.microorganism_id",
        "qc_queue": "module.qc_approval",
        "reports_list": "module.reports",
        "reminders_list": "module.reminders",
        "notifications_list": "module.notifications",

    }

    """
    Blocks direct URL requests to routes tied to disabled features.
    If a feature flag is disabled:
      - Option A: It disappears from the navigation sidebar.
      - Option B: Navigating directly to the URL renders a helpful 'Module Deactivated' 
        guidance page with an instant activation link for administrators.
    """

    ROUTE_FLAG_MAP = {
        # Batches
        "batch_list": ("module.batches", "Batch Management"),
        "batch_create": ("module.batches", "Batch Management"),
        "batch_detail": ("module.batches", "Batch Management"),

        # Diagnostic Lab Tests
        "labtest_list": ("module.lab_tests", "Diagnostic Lab Tests"),
        "labtest_create": ("module.lab_tests", "Diagnostic Lab Tests"),
        "labtest_detail": ("module.lab_tests", "Diagnostic Lab Tests"),

        # DNA Extractions
        "dna_list": ("module.dna_extraction", "DNA Extraction"),
        "dna_create": ("module.dna_extraction", "DNA Extraction"),
        "dna_detail": ("module.dna_extraction", "DNA Extraction"),

        # PCR / qPCR Assays
        "test_list": ("module.pcr", "PCR / qPCR Assays"),
        "test_create": ("module.pcr", "PCR / qPCR Assays"),
        "test_detail": ("module.pcr", "PCR / qPCR Assays"),

        # Microorganism Catalog
        "microbe_list": ("module.microorganism_id", "Microorganism Catalog"),
        "microbe_create": ("module.microorganism_id", "Microorganism Catalog"),

        # QC Approval & Reviews
        "qc_queue": ("module.qc_approval", "Quality Control Queue"),
        "qc_review": ("module.qc_approval", "Quality Control Review"),

        # Reports & Deliverables
        "reports_list": ("module.reports", "Safety Reports"),
        "report_generate": ("module.reports", "Report Generation"),
        "report_detail": ("module.reports", "Report Details"),
        "report_download": ("module.reports", "Report Download"),
        "report_send": ("module.reports", "Report Delivery"),
        "detection_log": ("module.reports", "Pathogen Detection Log"),
        "qc_compliance_log": ("module.reports", "QC Compliance Log"),
        "audit_export": ("module.audit_export", "Audit Trail CSV Export"),

        # Reminders & Alerts
        "reminders_list": ("module.reminders", "Action Reminders"),
        "reminder_action": ("module.reminders", "Reminder Actions"),
        "notifications_list": ("module.notifications", "Notifications Center"),
        "notification_mark_read": ("module.notifications", "Notification Management"),
        "notification_poll": ("module.notifications", "Notification Polling"),

        # Cryptographic Audit Trail
        "audit_list": ("module.audit_trail", "Audit Trail Ledger"),
        "audit_detail": ("module.audit_trail", "Audit Inspection"),
        "audit_verify": ("module.audit_trail", "Audit Integrity Verification"),

        # Recycle Bin
        "recycle_bin": ("module.recycle_bin", "Recycle Bin"),

        # User Directory
        "users_list": ("module.users", "User Directory"),
        "user_create": ("module.users", "User Creation"),
        "user_toggle": ("module.users", "User Access Control"),
        "user_reset_password": ("module.users", "Password Reset"),

        # Public Customer Portal
        "customer_portal": ("module.customer_portal", "Public Customer Portal"),
        "customer_portal_api": ("module.customer_portal", "Customer Portal API"),
        "customer_portal_download": ("module.customer_portal", "Customer Report Download"),

    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            resolved = resolve(request.path_info)

            flag_key = self.ROUTE_FLAG_MAP.get(resolved.url_name)
            if flag_key and not flag_enabled(flag_key):
                raise Http404("This feature is currently disabled.")
        except Http404:
            raise
        except Exception:
            pass

            url_name = resolved.url_name
            mapping = self.ROUTE_FLAG_MAP.get(url_name)
            
            if mapping:
                flag_key, module_name = mapping
                from apps.core.models import flag_enabled
                if not flag_enabled(flag_key):
                    return render(
                        request,
                        "errors/module_disabled.html",
                        {
                            "module_name": module_name,
                            "flag_key": flag_key,
                        },
                        status=403,
                    )
        except Exception:
            pass
            

        return self.get_response(request)