from django.http import Http404
from django.urls import resolve
from django.utils.cache import add_never_cache_headers
from django.utils.deprecation import MiddlewareMixin

from apps.core.models import flag_enabled


class NoCacheMiddleware(MiddlewareMixin):
    """Add no-cache headers to all authenticated HTML responses."""

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
        return self.get_response(request)