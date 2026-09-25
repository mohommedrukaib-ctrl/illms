"""
ILIMS — Production Settings
"""
import os

from .base import *  # noqa: F401, F403

DEBUG = False

ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",")
    if h.strip()
]

# HTTPS / HSTS
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 63072000  # 2 years
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# All cookies already strict via base, just confirm
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Stricter CSP in prod
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
        "upgrade-insecure-requests": True,
    },
}