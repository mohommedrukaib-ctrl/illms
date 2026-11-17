

"""
config URL Configuration

Routes all application portals, Django admin, and user accounts.
Enforces secure, permission-checked routing for all media and user uploads.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path


urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("", include("apps.core.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Custom error handlers

from apps.core.views_media import secure_media_serve

urlpatterns = [
    # Django Admin Portal
    path("django-admin/", admin.site.urls),

    # Authentication & User Accounts Portal (Login, 2FA, Profile, Password Changes)
    path("accounts/", include("apps.accounts.urls")),

    # Secure Media Routing — Enforces login & scoping checks before serving files.
    # This prevents directory traversal or unauthorized link-sharing of report PDFs and avatars.
    path("media/<path:path>", secure_media_serve, name="secure_media_serve"),

    # Main Food Safety Molecular Analysis Portal (Core)
    path("", include("apps.core.urls")),

    
]

# Serve static files in development (WhiteNoise handles this in production)
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# Custom Global Error Handlers (WCAG AA compliant, styled error pages)

handler400 = "apps.core.views.error_400"
handler403 = "apps.core.views.error_403"
handler404 = "apps.core.views.error_404"
handler500 = "apps.core.views.error_500"