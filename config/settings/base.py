"""
ILIMS — Base Settings
Shared across dev and prod. Never used directly.
"""
import os
from pathlib import Path

# ──────────────────────────────────────────────
# PATHS
# ──────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent.parent
APPS_DIR = BASE_DIR / "apps"

# ──────────────────────────────────────────────
# CORE DJANGO
# ──────────────────────────────────────────────
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "INSECURE-change-me-before-deployment-this-is-50-chars-placeholder-xyz",
)

DEBUG = False

ALLOWED_HOSTS = []

# ──────────────────────────────────────────────
# APPLICATIONS
# ──────────────────────────────────────────────
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
]

THIRD_PARTY_APPS = [
    "django_htmx",
    "axes",
    "django_otp",
    "django_otp.plugins.otp_totp",
    "widget_tweaks",
    "csp",
]

LOCAL_APPS = [
    "apps.core",
    "apps.accounts",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ──────────────────────────────────────────────
# MIDDLEWARE
# ──────────────────────────────────────────────
# ──────────────────────────────────────────────
# MIDDLEWARE
# ──────────────────────────────────────────────
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_otp.middleware.OTPMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "csp.middleware.CSPMiddleware",
    "apps.accounts.middleware.SessionIdleTimeoutMiddleware",
    # "apps.accounts.middleware.TwoFactorEnforcementMiddleware",  # Disabled for dev
    "apps.core.middleware.NoCacheMiddleware",
    "apps.core.middleware.FeatureFlagMiddleware",
    "axes.middleware.AxesMiddleware",
]

# ──────────────────────────────────────────────
# ILIMS CUSTOM
# ──────────────────────────────────────────────
# Set to empty list to disable mandatory 2FA setup for all roles
ROLES_REQUIRING_2FA = []

ROOT_URLCONF = "config.urls"

# ──────────────────────────────────────────────
# TEMPLATES
# ──────────────────────────────────────────────
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            APPS_DIR / "core" / "templates",
            APPS_DIR / "accounts" / "templates",
        ],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.ilims_context",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ──────────────────────────────────────────────
# DATABASE — PostgreSQL 17 with psycopg 3
# ──────────────────────────────────────────────
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "ilims_db"),
        "USER": os.environ.get("DB_USER", "ilims_user"),
        "PASSWORD": os.environ.get("DB_PASSWORD", "ilims_password"),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
        "CONN_MAX_AGE": 600,
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": {
            "connect_timeout": 10,
        },
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ──────────────────────────────────────────────
# AUTH
# ──────────────────────────────────────────────
AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "apps.accounts.backends.EmailOrUsernameBackend",
]

# Argon2id password hashing
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
    {"NAME": "apps.accounts.validators.ComplexityValidator"},
    {"NAME": "apps.accounts.validators.PasswordHistoryValidator"},
]

# ──────────────────────────────────────────────
# DJANGO-AXES (brute-force lockout)
# ──────────────────────────────────────────────
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 0.25  # 15 minutes
AXES_LOCKOUT_PARAMETERS = ["username", "ip_address"]
AXES_LOCKOUT_TEMPLATE = "accounts/locked_out.html"
AXES_RESET_ON_SUCCESS = True
AXES_ENABLE_ACCESS_FAILURE_LOG = True

# ──────────────────────────────────────────────
# DJANGO-OTP (TOTP two-factor)
# ──────────────────────────────────────────────
OTP_TOTP_ISSUER = "ILIMS Food Safety"

# ──────────────────────────────────────────────
# SESSION
# ──────────────────────────────────────────────
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE = 3600  # 1 hour max
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Strict"
SESSION_COOKIE_NAME = "ilims_session"
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_IDLE_TIMEOUT = int(os.environ.get("SESSION_IDLE_TIMEOUT", 1800))

# ──────────────────────────────────────────────
# CSRF
# ──────────────────────────────────────────────
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Strict"
CSRF_COOKIE_NAME = "ilims_csrf"
CSRF_TRUSTED_ORIGINS = [
    o.strip()
    for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "http://localhost:8000").split(",")
    if o.strip()
]

# ──────────────────────────────────────────────
# CONTENT SECURITY POLICY (django-csp 4.x)
# ──────────────────────────────────────────────
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

# ──────────────────────────────────────────────
# SECURITY HEADERS
# ──────────────────────────────────────────────
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# ──────────────────────────────────────────────
# INTERNATIONALIZATION
# ──────────────────────────────────────────────
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ──────────────────────────────────────────────
# STATIC FILES (WhiteNoise)
# ──────────────────────────────────────────────
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# ──────────────────────────────────────────────
# MEDIA / UPLOADS
# ──────────────────────────────────────────────
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
UPLOAD_ROOT = BASE_DIR / "uploads"
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB

# ──────────────────────────────────────────────
# EMAIL
# ──────────────────────────────────────────────
EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = os.environ.get("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", 587))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "True").lower() in ("true", "1")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "ilims@example.com")

# ──────────────────────────────────────────────
# CELERY (optional)
# ──────────────────────────────────────────────
CELERY_BROKER_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE

# ──────────────────────────────────────────────
# LOGGING
# ──────────────────────────────────────────────
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "file": {
            "class": "logging.FileHandler",
            "filename": BASE_DIR / "logs" / "ilims.log",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console", "file"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console", "file"],
            "level": "WARNING",
            "propagate": False,
        },
        "apps": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

# ──────────────────────────────────────────────
# ILIMS CUSTOM
# ──────────────────────────────────────────────
ILIMS_VERSION = "1.0.0"
ILIMS_TITLE = "ILIMS"
ILIMS_SUBTITLE = "Food Safety Portal"

# Roles
ROLE_TECHNICIAN = "TECHNICIAN"
ROLE_ANALYST = "ANALYST"
ROLE_QC_OFFICER = "QC_OFFICER"
ROLE_FOOD_SAFETY_OFFICER = "FOOD_SAFETY_OFFICER"
ROLE_ADMIN = "ADMIN"

ROLE_CHOICES = [
    (ROLE_TECHNICIAN, "Lab Technician"),
    (ROLE_ANALYST, "Analyst"),
    (ROLE_QC_OFFICER, "QC Officer"),
    (ROLE_FOOD_SAFETY_OFFICER, "Food Safety Officer"),
    (ROLE_ADMIN, "Administrator"),
]

ROLES_REQUIRING_2FA = [ROLE_QC_OFFICER, ROLE_FOOD_SAFETY_OFFICER, ROLE_ADMIN]