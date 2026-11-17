"""
Core application context processors for ILIMS.
"""
from django.conf import settings
from apps.core.models import FeatureFlag, SystemSetting, Notification


def ilims_context(request):
    """
    Global template context processor providing system settings, feature flags,
    theme preferences, and user notification counters.
    """
    theme = request.COOKIES.get("ilims_theme", "light")
    
    # Safe fetch for system settings
    try:
        settings_obj = SystemSetting.get_settings()
    except Exception:
        settings_obj = None

    flags_dict = {}
    latest = []
    unread_count = 0

    user = getattr(request, "user", None)
    if user and user.is_authenticated:
        # Load feature flags
        try:
            for f in FeatureFlag.objects.all():
                key = f.key.replace(".", "_") if hasattr(f, "key") and f.key else f"flag_{f.pk}"
                flags_dict[key] = f.enabled
        except Exception:
            pass

        # Load notifications
        try:
            notif_qs = Notification.objects.filter(user=user).order_by("-created_at")
            unread_count = notif_qs.filter(is_read=False).count()
            latest = list(notif_qs[:3])
        except Exception:
            pass

    return {
        "ILIMS_VERSION": getattr(settings, "ILIMS_VERSION", "1.0.0"),
        "ILIMS_TITLE": getattr(settings, "ILIMS_TITLE", "ILIMS"),
        "ILIMS_SUBTITLE": getattr(settings, "ILIMS_SUBTITLE", "Laboratory Information Management System"),
        "current_theme": theme,
        "ROLE_CHOICES": getattr(settings, "ROLE_CHOICES", []),
        "system_settings": settings_obj,
        "features": flags_dict,
        "latest": latest,
        "unread": latest,
        "unread_count": unread_count,
    }