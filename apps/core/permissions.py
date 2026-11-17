from django.contrib.auth.mixins import AccessMixin
from django.core.exceptions import PermissionDenied


class LaboratoryScopedPermissionMixin(AccessMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)

    def scope_queryset(self, queryset, user, lab_field_path="laboratory"):
        if user.is_superuser or user.has_role_perm("global_scope"):
            return queryset
        if hasattr(user, "laboratory") and user.laboratory:
            return queryset.filter(**{lab_field_path: user.laboratory})
        return queryset.none()

    def check_object_permission(self, request, obj, lab_attr="laboratory"):
        user = request.user
        if user.is_superuser or user.has_role_perm("global_scope"):
            return True
        obj_lab = getattr(obj, lab_attr, None)
        user_lab = getattr(user, "laboratory", None)
        if obj_lab and user_lab and obj_lab == user_lab:
            return True
        raise PermissionDenied("Access Denied: You do not have permission to view or manage this record.")