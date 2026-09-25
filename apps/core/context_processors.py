from django.conf import settings
from apps.core.models import FeatureFlag, SystemSetting


def ilims_context(request):
    theme = request.COOKIES.get("ilims_theme", "light")
    settings_obj = SystemSetting.get_settings()
    
    # Get all flags for UI filtering
    flags_dict = {}
    if request.user.is_authenticated:
        try:
            flags = FeatureFlag.objects.all()
            for f in flags:
                flags_dict[f.key.replace(".", "_")] = f.enabled
        except Exception:
            pass

    return {
        "ILIMS_VERSION": settings.ILIMS_VERSION,
        "ILIMS_TITLE": settings.ILIMS_TITLE,
        "ILIMS_SUBTITLE": settings.ILIMS_SUBTITLE,
        "current_theme": theme,
        "ROLE_CHOICES": settings.ROLE_CHOICES,
        "system_settings": settings_obj,
        "features": flags_dict,
    }