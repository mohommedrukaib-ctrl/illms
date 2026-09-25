from functools import wraps
from django.core.exceptions import PermissionDenied
from apps.core.models import flag_enabled


def require_flag(key):
    """Enforce a feature flag at the view level."""
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not flag_enabled(key):
                raise PermissionDenied("This module is currently disabled.")
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator