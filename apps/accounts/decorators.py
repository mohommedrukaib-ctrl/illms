from functools import wraps

from django.conf import settings
from django.core.exceptions import PermissionDenied


def role_required(*roles):
    """Decorator that restricts view access to specific roles."""

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                from django.shortcuts import redirect

                return redirect(settings.LOGIN_URL)
            if request.user.role not in roles and not request.user.is_superuser:
                raise PermissionDenied("You do not have permission to access this page.")
            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator