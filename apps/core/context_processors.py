from django.conf import settings
from apps.core.models import FeatureFlag, SystemSetting, Notification


def ilims_context(request):
    theme = request.COOKIES.get("ilims_theme", "light")
    settings_obj = SystemSetting.get_settings()

    flags_dict = {}
    latest = []
    unread_count = 0

    if getattr(request, "user", None) and request.user.is_authenticated:
        try:
            for f in FeatureFlag.objects.all():
                flags_dict[f.key.replace(".", "_")] = f.enabled
        except Exception:
            pass

        try:
            notif_qs = Notification.objects.filter(user=request.user).order_by("-created_at")
            unread_count = notif_qs.filter(is_read=False).count()
            latest = list(notif_qs[:3])
        except Exception:
            pass

    return {
        "ILIMS_VERSION": getattr(settings, "ILIMS_VERSION", ""),
        "ILIMS_TITLE": getattr(settings, "ILIMS_TITLE", "ILIMS"),
        "ILIMS_SUBTITLE": getattr(settings, "ILIMS_SUBTITLE", ""),
        "current_theme": theme,
        "ROLE_CHOICES": getattr(settings, "ROLE_CHOICES", []),
        "system_settings": settings_obj,
        "features": flags_dict,
        "latest": latest,
        "unread": latest,
        "unread_count": unread_count,
    }