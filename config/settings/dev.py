"""
ILIMS — Development Settings
"""
from .base import *  # noqa: F401, F403

DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0"]

# Relax security for local development
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_SSL_REDIRECT = False

# Console email
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# CSP relaxed for dev (still no CDN)
CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src": ("'self'",),
        "script-src": ("'self'",),
        "style-src": ("'self'", "'unsafe-inline'",),
        "img-src": ("'self'", "data:",),
        "font-src": ("'self'",),
        "connect-src": ("'self'",),
        "frame-ancestors": ("'none'",),
        "form-action": ("'self'",),
        "base-uri": ("'self'",),
    },
}

# WhiteNoise serves static in dev too
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}