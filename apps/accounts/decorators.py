from functools import wraps




from django.conf import settings
from django.core.exceptions import PermissionDenied


def role_required(*roles):
    """Decorator that restricts view access to specific roles or superusers."""
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect(settings.LOGIN_URL)
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            if request.user.role not in roles:
                raise PermissionDenied("You do not have permission to access this page.")
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


def module_required(module_key):
    """Decorator that restricts view access to specific modules."""
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect(settings.LOGIN_URL)
            if not request.user.has_module(module_key):
                raise PermissionDenied("Your role cannot access this module.")
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator