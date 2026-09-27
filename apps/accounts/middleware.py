import ipaddress
from datetime import timedelta

from django.conf import settings
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone


def get_client_ip(request):
    """Extract client IP address reliably."""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0].strip()
    else:
        ip = request.META.get("REMOTE_ADDR", "").strip()
    return ip


def is_ip_allowed(client_ip_str, allowed_networks):
    """Verify if a client IP matches any allowed IP or CIDR network range."""
    if not client_ip_str:
        return False
    try:
        client_ip = ipaddress.ip_address(client_ip_str)
    except ValueError:
        return False

    for entry in allowed_networks:
        entry = str(entry).strip()
        if not entry:
            continue
        try:
            network = ipaddress.ip_network(entry, strict=False)
            if client_ip in network:
                return True
        except ValueError:
            if client_ip_str == entry:
                return True
    return False


class IPAllowlistMiddleware:
    """Restricts access to approved IP addresses or subnets."""

    EXEMPT_PATHS = ["/static/", "/favicon.ico"]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info
        if any(path.startswith(exempt) for exempt in self.EXEMPT_PATHS):
            return self.get_response(request)

        try:
            from apps.core.models import flag_enabled
            if not flag_enabled("sec.ip_allowlist"):
                return self.get_response(request)
        except Exception:
            return self.get_response(request)

        client_ip = get_client_ip(request)
        if settings.DEBUG and client_ip in ("127.0.0.1", "::1", "localhost"):
            return self.get_response(request)

        allowed_ips = ["127.0.0.1", "::1"]
        try:
            from apps.core.models import SystemSetting
            sys_settings = SystemSetting.get_settings()
            configured_ips = sys_settings.security_settings.get("allowed_ips", [])
            if isinstance(configured_ips, str):
                configured_ips = [ip.strip() for ip in configured_ips.split(",") if ip.strip()]
            allowed_ips.extend(configured_ips)
        except Exception:
            pass

        if not is_ip_allowed(client_ip, allowed_ips):
            return render(request, "errors/403_ip_restricted.html", {"client_ip": client_ip}, status=403)

        return self.get_response(request)


class SessionIdleTimeoutMiddleware:
    """Automatically log out users after a period of inactivity."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            last_activity = request.session.get("last_activity")
            if last_activity:
                timeout = getattr(settings, "SESSION_IDLE_TIMEOUT", 1800)
                elapsed = timezone.now().timestamp() - last_activity
                if elapsed > timeout:
                    from django.contrib import messages
                    from django.contrib.auth import logout
                    logout(request)
                    messages.warning(request, "Your session has expired due to inactivity. Please log in again.")
                    return redirect(settings.LOGIN_URL)
            request.session["last_activity"] = timezone.now().timestamp()

        return self.get_response(request)


class PasswordExpiryMiddleware:
    """Force users to change their password if it has expired."""

    EXEMPT_URLS = [
        "/accounts/login/",
        "/accounts/logout/",
        "/accounts/password/change/",
        "/accounts/2fa/",
        "/static/",
        "/media/",
        "/favicon.ico",
    ]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated:
            return self.get_response(request)

        try:
            from apps.core.models import flag_enabled
            if not flag_enabled("sec.force_password_expiry"):
                return self.get_response(request)
        except Exception:
            return self.get_response(request)

        path = request.path_info
        if any(path.startswith(url) for url in self.EXEMPT_URLS):
            return self.get_response(request)

        if getattr(request.user, "force_password_change", False):
            return redirect(reverse("accounts:password_change"))

        try:
            from apps.core.models import SystemSetting
            sys_settings = SystemSetting.get_settings()
            expiry_days = sys_settings.security_settings.get("password_expiry_days", 90)
        except Exception:
            expiry_days = 90

        last_change = getattr(request.user, "last_password_change", None)
        if last_change:
            age = timezone.now() - last_change
            if age > timedelta(days=expiry_days):
                request.user.force_password_change = True
                request.user.save(update_fields=["force_password_change"])
                return redirect(reverse("accounts:password_change"))

        return self.get_response(request)