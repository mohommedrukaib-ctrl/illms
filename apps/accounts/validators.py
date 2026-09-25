import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


class ComplexityValidator:
    """Require at least one uppercase, one lowercase, one digit, one special character."""

    def validate(self, password, user=None):
        if not re.search(r"[A-Z]", password):
            raise ValidationError(
                _("Password must contain at least one uppercase letter."),
                code="password_no_upper",
            )
        if not re.search(r"[a-z]", password):
            raise ValidationError(
                _("Password must contain at least one lowercase letter."),
                code="password_no_lower",
            )
        if not re.search(r"\d", password):
            raise ValidationError(
                _("Password must contain at least one digit."),
                code="password_no_digit",
            )
        if not re.search(r"[!@#$%^&*()_+\-=\[\]{}|;:'\",.<>?/`~\\]", password):
            raise ValidationError(
                _("Password must contain at least one special character."),
                code="password_no_special",
            )

    def get_help_text(self):
        return _(
            "Your password must contain at least one uppercase letter, "
            "one lowercase letter, one digit, and one special character."
        )


class PasswordHistoryValidator:
    """Prevent reuse of the last 5 passwords."""

    HISTORY_DEPTH = 5

    def validate(self, password, user=None):
        if user is None:
            return

        from .models import PasswordHistory

        current_hash = PasswordHistory.make_hash(password)
        recent = PasswordHistory.objects.filter(user=user).order_by("-created_at")[: self.HISTORY_DEPTH]
        for entry in recent:
            if entry.password_hash == current_hash:
                raise ValidationError(
                    _("You cannot reuse any of your last %(depth)s passwords."),
                    code="password_reused",
                    params={"depth": self.HISTORY_DEPTH},
                )

    def get_help_text(self):
        return _("Your password cannot be the same as any of your last 5 passwords.")