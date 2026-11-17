from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import ListView

from apps.accounts.models import Role
from apps.core.audit import get_changes, log_audit
from apps.core.forms_users import UserForm, AdminPasswordResetForm, RoleForm
from apps.core.mixins import HtmxModalMixin, ILIMSViewMixin

User = get_user_model()


def _full_reload(url):
    """
    Return an HTMX redirect with an OOB modal clear and meta-refresh fallback.
    Guarantees page lists auto-refresh even if HX-Redirect is swallowed.
    """
    body = (
        f'<div id="modal-host" hx-swap-oob="innerHTML"></div>'
        f'<meta http-equiv="refresh" content="0;url={url}">'
    )
    response = HttpResponse(body, status=200)
    response["HX-Redirect"] = url
    response["HX-Trigger"] = "ilims:refresh"
    return response


def _require_user_admin(user):
    """Check if the current user is allowed to access User/Role management views."""
    if user.is_superuser or user.has_role_perm("manage_users") or user.has_role_perm("manage_roles") or user.role == "ADMIN":
        return
    raise PermissionDenied("You do not have permission to manage users or roles.")


# ══════════════════════════════════════════════════════════════════
# USER MANAGEMENT VIEWS
# ══════════════════════════════════════════════════════════════════

class UserListView(ILIMSViewMixin, ListView):
    model = User
    template_name = "users/user_list.html"
    context_object_name = "users"
    paginate_by = 50
    page_title = "User Directory"
    page_subtitle = "Manage portal user credentials, active statuses, and facility assignments"
    page_icon = "users"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        _require_user_admin(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = User.objects.select_related("laboratory").order_by("last_name", "first_name")
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(username__icontains=q)
                | Q(email__icontains=q)
                | Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
            )
        role = self.request.GET.get("role", "").strip()
        if role:
            qs = qs.filter(role=role)
        status = self.request.GET.get("status", "").strip()
        if status == "active":
            qs = qs.filter(is_active=True, is_deleted=False)
        elif status == "inactive":
            qs = qs.filter(is_active=False, is_deleted=False)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        # Load dynamic roles for the dropdown filter
        roles = list(Role.objects.filter(is_active=True).order_by("name").values_list("code", "name"))
        ctx["role_choices"] = roles or list(User.Role.choices)
        
        ctx["current_q"] = self.request.GET.get("q", "")
        ctx["current_role"] = self.request.GET.get("role", "")
        ctx["current_status"] = self.request.GET.get("status", "")
        ctx["counts"] = {
            "total": User.objects.filter(is_deleted=False).count(),
            "active": User.objects.filter(is_active=True, is_deleted=False).count(),
            "inactive": User.objects.filter(is_active=False, is_deleted=False).count(),
        }
        return ctx

    def get_template_names(self):
        if getattr(self.request, "htmx", False) and not getattr(
            self.request.htmx, "boosted", False
        ):
            return ["users/partials/_user_list_rows.html"]
        return [self.template_name]


class UserCreateView(HtmxModalMixin, LoginRequiredMixin, View):
    modal_template = "users/partials/_modal_user_form.html"
    page_template = "users/user_form_page.html"
    modal_title = "Register New User"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            _require_user_admin(request.user)
        return super().dispatch(request, *args, **kwargs)

    def _get_instance(self, request):
        edit_pk = request.GET.get("edit") or request.POST.get("edit")
        if edit_pk:
            try:
                return User.objects.get(pk=edit_pk, is_deleted=False)
            except (User.DoesNotExist, ValueError):
                pass
        return None

    def get(self, request):
        instance = self._get_instance(request)
        title = "Edit User Settings" if instance else "Register New User"
        form = UserForm(instance=instance, is_create=(instance is None))
        return self.render_modal_or_page(request, {
            "form": form,
            "instance": instance,
            "modal_title": title,
            "edit_pk": str(instance.pk) if instance else "",
        })

    def post(self, request):
        instance = self._get_instance(request)
        title = "Edit User Settings" if instance else "Register New User"
        form = UserForm(request.POST, instance=instance, is_create=(instance is None))

        if form.is_valid():
            user = form.save(commit=False)
            raw_password = form.cleaned_data.get("password")
            if raw_password:
                user.set_password(raw_password)

            # Assign superuser/staff status automatically if role is ADMIN
            user.is_staff = (user.role == "ADMIN")
            user.is_superuser = (user.role == "ADMIN")

            user.save()

            action = "UPDATE" if instance else "CREATE"
            changes = get_changes(instance, user, ["email", "username", "role", "laboratory_id", "is_active"])
            log_audit(request.user, action, user, changes)

            messages.success(request, f"User '{user.username}' has been successfully saved.")
            if self._is_modal(request):
                return _full_reload(reverse("core:users_list"))
            return redirect("core:users_list")

        return self.render_modal_or_page(request, {
            "form": form,
            "instance": instance,
            "modal_title": title,
            "edit_pk": str(instance.pk) if instance else "",
        }, status=400)


class UserToggleActiveView(LoginRequiredMixin, View):
    """Deactivate or activate an existing user account."""

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            _require_user_admin(request.user)
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk, is_deleted=False)
        if user.pk == request.user.pk:
            messages.error(request, "You cannot deactivate your own account.")
            return redirect("core:users_list")

        user.is_active = not user.is_active
        user.save(update_fields=["is_active"])
        
        status_text = "activated" if user.is_active else "deactivated"
        log_audit(request.user, "UPDATE", user, {
            "is_active": {"old": not user.is_active, "new": user.is_active}
        })
        
        messages.success(request, f"User '{user.username}' has been successfully {status_text}.")
        return redirect("core:users_list")


class UserResetPasswordView(HtmxModalMixin, LoginRequiredMixin, View):
    """Admin-only reset interface enforcing full complexity rules and password change triggers."""
    modal_template = "users/partials/_modal_reset_password.html"
    page_template = "users/reset_password_page.html"
    modal_title = "Reset Password"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            _require_user_admin(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, pk):
        user = get_object_or_404(User, pk=pk, is_deleted=False)
        form = AdminPasswordResetForm()
        return self.render_modal_or_page(request, {
            "form": form,
            "user_instance": user,
            "modal_title": f"Reset Password · {user.username}",
        })

    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk, is_deleted=False)
        form = AdminPasswordResetForm(request.POST, user_instance=user)

        if form.is_valid():
            new_password = form.cleaned_data["new_password"]
            user.set_password(new_password)
            user.force_password_change = True
            user.save(update_fields=["password", "force_password_change"])

            log_audit(request.user, "UPDATE", user, {"action": "administrative_password_reset"})
            messages.success(request, f"Password successfully reset for {user.username}. Password change will be forced on next login.")
            
            if self._is_modal(request):
                return _full_reload(reverse("core:users_list"))
            return redirect("core:users_list")

        return self.render_modal_or_page(request, {
            "form": form,
            "user_instance": user,
            "modal_title": f"Reset Password · {user.username}",
        }, status=400)


# ══════════════════════════════════════════════════════════════════
# DYNAMIC ROLES & ACCESS VIEWS
# ══════════════════════════════════════════════════════════════════

class RoleListView(ILIMSViewMixin, ListView):
    model = Role
    template_name = "users/role_list.html"
    context_object_name = "roles"
    paginate_by = 50
    page_title = "Roles & Access"
    page_subtitle = "Define roles and choose which modules each role can open"
    page_icon = "users"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        _require_user_admin(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        # Sort system roles first, then custom roles alphabetically
        return Role.objects.all().order_by("-is_system", "name")


class RoleCreateView(HtmxModalMixin, LoginRequiredMixin, View):
    modal_template = "users/partials/_modal_role_form.html"
    page_template = "users/role_form_page.html"
    modal_title = "Create Role"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            _require_user_admin(request.user)
        return super().dispatch(request, *args, **kwargs)

    def _get_instance(self, request):
        edit_pk = request.GET.get("edit") or request.POST.get("edit")
        if edit_pk:
            try:
                return Role.objects.get(pk=edit_pk)
            except (Role.DoesNotExist, ValueError):
                pass
        return None

    def get(self, request):
        instance = self._get_instance(request)
        title = f"Edit Role · {instance.name}" if instance else "Create Role"
        form = RoleForm(instance=instance)
        return self.render_modal_or_page(request, {
            "form": form,
            "instance": instance,
            "modal_title": title,
            "edit_pk": str(instance.pk) if instance else "",
            "module_fields": [f for f in form if f.name.startswith("mod__")],
        })

    def post(self, request):
        instance = self._get_instance(request)
        title = f"Edit Role · {instance.name}" if instance else "Create Role"
        form = RoleForm(request.POST, instance=instance)
        
        if form.is_valid():
            role = form.save()
            action = "UPDATE" if instance else "CREATE"
            log_audit(request.user, action, role, {
                "code": {"old": None, "new": role.code},
                "name": {"old": None, "new": role.name},
            })
            
            messages.success(request, f"Role '{role.name}' saved successfully.")
            if self._is_modal(request):
                return _full_reload(reverse("core:roles_list"))
            return redirect("core:roles_list")
            
        return self.render_modal_or_page(request, {
            "form": form,
            "instance": instance,
            "modal_title": title,
            "edit_pk": str(instance.pk) if instance else "",
            "module_fields": [f for f in form if f.name.startswith("mod__")],
        }, status=400)


class RoleDeleteView(LoginRequiredMixin, View):
    """Deletes a custom role, provided it is not a system role and has no active users."""
    
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            _require_user_admin(request.user)
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, pk):
        role = get_object_or_404(Role, pk=pk)
        
        if role.is_system:
            messages.error(request, "System roles are protected and cannot be deleted.")
            return redirect("core:roles_list")
            
        if User.objects.filter(role=role.code, is_deleted=False).exists():
            messages.error(request, f"Cannot delete '{role.name}' because it is still assigned to active users.")
            return redirect("core:roles_list")
            
        code = role.code
        role.delete()
        
        # Log the deletion using the current user as the "instance" placeholder, 
        # since the role object is now deleted from DB.
        log_audit(request.user, "DELETE", request.user, {"role_deleted": {"old": code, "new": None}})
        
        messages.success(request, f"Role '{code}' deleted successfully.")
        return redirect("core:roles_list")