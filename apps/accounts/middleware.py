import time

from django.conf import settings
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import resolve, reverse
from django.utils.deprecation import MiddlewareMixin


class SessionIdleTimeoutMiddleware(MiddlewareMixin):
    """Auto-logout after SESSION_IDLE_TIMEOUT seconds of inactivity."""

    EXEMPT_URLS = [
        "accounts:login",
        "accounts:locked_out",
    ]

    def process_request(self, request):
        if not request.user.is_authenticated:
            return None

        current_url_name = resolve(request.path_info).url_name
        if current_url_name in [u.split(":")[-1] for u in self.EXEMPT_URLS]:
            return None

        now = time.time()
        last_activity = request.session.get("last_activity")

        if last_activity is not None:
            idle = now - last_activity
            if idle > settings.SESSION_IDLE_TIMEOUT:
                logout(request)
                from django.contrib import messages

                messages.warning(
                    request,
                    "Your session has expired due to inactivity. Please log in again.",
                )
                return redirect(settings.LOGIN_URL)

        request.session["last_activity"] = now
        return None


class TwoFactorEnforcementMiddleware(MiddlewareMixin):
    """
    Force users whose role requires 2FA to set it up before accessing
    any other page. Also verify 2FA on login if device exists.
    """

    EXEMPT_URL_NAMES = [
        "login",
        "logout",
        "locked_out",
        "setup_2fa",
        "verify_2fa",
    ]

    def process_request(self, request):
        if not request.user.is_authenticated:
            return None

        resolved = resolve(request.path_info)
        url_name = resolved.url_name
        if url_name in self.EXEMPT_URL_NAMES:
            return None

        # Serve static files without check
        if request.path.startswith(settings.STATIC_URL):
            return None

        # If user must set up 2FA, redirect them
        if hasattr(request.user, "must_setup_2fa") and request.user.must_setup_2fa:
            return redirect(reverse("accounts:setup_2fa"))

        # If user has a verified device but hasn't verified this session
        if not request.session.get("otp_verified", False):
            from django_otp import devices_for_user

            confirmed_devices = list(devices_for_user(request.user, confirmed=True))
            if confirmed_devices:
                return redirect(reverse("accounts:verify_2fa"))

        return None