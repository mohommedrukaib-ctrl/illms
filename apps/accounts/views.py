import io
import logging

import qrcode
import qrcode.image.svg
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.generic import FormView
from django_otp.plugins.otp_totp.models import TOTPDevice

from .forms import ILIMSLoginForm, ILIMSPasswordChangeForm, ProfileForm, TOTPVerifyForm

logger = logging.getLogger(__name__)


@method_decorator([csrf_protect, never_cache], name="dispatch")
class ILIMSLoginView(LoginView):
    """Custom login view with rate limiting handled by Axes."""

    template_name = "accounts/login.html"
    form_class = ILIMSLoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        user = form.get_user()
        login(self.request, user)
        self.request.session["last_activity"] = __import__("time").time()

        # Check if 2FA is needed
        from django_otp import devices_for_user

        confirmed_devices = list(devices_for_user(user, confirmed=True))
        if confirmed_devices:
            self.request.session["otp_verified"] = False
            return redirect(reverse("accounts:verify_2fa"))

        if user.must_setup_2fa:
            return redirect(reverse("accounts:setup_2fa"))

        self.request.session["otp_verified"] = True
        messages.success(self.request, f"Welcome back, {user.get_short_name()}!")
        return redirect(self.get_success_url())


class LogoutConfirmView(View):
    """Show a confirmation page (GET) and perform logout (POST)."""

    def get(self, request):
        return render(request, "accounts/logout_confirm.html")

    def post(self, request):
        logout(request)
        messages.info(request, "You have been logged out.")
        return redirect(reverse("accounts:login"))


@method_decorator([login_required, never_cache], name="dispatch")
class Setup2FAView(View):
    """Set up TOTP two-factor authentication."""

    def get(self, request):
        device, created = TOTPDevice.objects.get_or_create(
            user=request.user,
            confirmed=False,
            defaults={"name": "ILIMS Authenticator"},
        )
        qr_svg = self._generate_qr_svg(device)
        return render(request, "accounts/setup_2fa.html", {
            "device": device,
            "qr_svg": qr_svg,
            "form": TOTPVerifyForm(),
        })

    def post(self, request):
        form = TOTPVerifyForm(request.POST)
        if not form.is_valid():
            return self._render_with_error(request, form, "Invalid code format.")

        token = form.cleaned_data["otp_token"]
        try:
            device = TOTPDevice.objects.get(user=request.user, confirmed=False)
        except TOTPDevice.DoesNotExist:
            messages.error(request, "No pending 2FA device found. Please start again.")
            return redirect(reverse("accounts:setup_2fa"))

        if device.verify_token(token):
            device.confirmed = True
            device.save()
            request.session["otp_verified"] = True
            messages.success(request, "Two-factor authentication has been enabled!")
            return redirect(reverse("accounts:profile"))

        return self._render_with_error(request, form, "Invalid code. Please try again.")

    def _render_with_error(self, request, form, error_msg):
        try:
            device = TOTPDevice.objects.get(user=request.user, confirmed=False)
        except TOTPDevice.DoesNotExist:
            device = TOTPDevice.objects.create(
                user=request.user, confirmed=False, name="ILIMS Authenticator"
            )
        qr_svg = self._generate_qr_svg(device)
        messages.error(request, error_msg)
        return render(request, "accounts/setup_2fa.html", {
            "device": device,
            "qr_svg": qr_svg,
            "form": form,
        })

    @staticmethod
    def _generate_qr_svg(device):
        url = device.config_url
        factory = qrcode.image.svg.SvgPathImage
        img = qrcode.make(url, image_factory=factory, box_size=8)
        buf = io.BytesIO()
        img.save(buf)
        return buf.getvalue().decode("utf-8")


@method_decorator([login_required, never_cache], name="dispatch")
class Verify2FAView(View):
    """Verify TOTP code for authenticated user who has a confirmed device."""

    def get(self, request):
        return render(request, "accounts/login_2fa.html", {"form": TOTPVerifyForm()})

    def post(self, request):
        form = TOTPVerifyForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Please enter a valid 6-digit code.")
            return render(request, "accounts/login_2fa.html", {"form": form})

        token = form.cleaned_data["otp_token"]
        from django_otp import devices_for_user

        for device in devices_for_user(request.user, confirmed=True):
            if device.verify_token(token):
                request.session["otp_verified"] = True
                messages.success(request, f"Welcome back, {request.user.get_short_name()}!")
                next_url = request.GET.get("next", reverse("core:dashboard"))
                return redirect(next_url)

        messages.error(request, "Invalid authentication code. Please try again.")
        return render(request, "accounts/login_2fa.html", {"form": form})


@method_decorator([login_required, csrf_protect], name="dispatch")
class PasswordChangeView(FormView):
    """Password change with history check."""

    template_name = "accounts/password_change.html"
    form_class = ILIMSPasswordChangeForm
    success_url = reverse_lazy("accounts:profile")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.save()
        from django.contrib.auth import update_session_auth_hash

        update_session_auth_hash(self.request, form.user)
        messages.success(self.request, "Your password has been changed.")
        return super().form_valid(form)


@login_required
def profile_view(request):
    """User profile page."""
    if request.method == "POST":
        form = ProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated.")
            return redirect(reverse("accounts:profile"))
    else:
        form = ProfileForm(instance=request.user)

    has_2fa = False
    from django_otp import devices_for_user

    has_2fa = any(d.confirmed for d in devices_for_user(request.user, confirmed=True))

    return render(request, "accounts/profile.html", {
        "form": form,
        "has_2fa": has_2fa,
        "page_title": "Profile",
    })


def locked_out_view(request):
    """Custom Axes lockout page."""
    return render(request, "accounts/locked_out.html", status=403)