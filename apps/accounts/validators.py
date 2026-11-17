
import re

from django.core.exceptions import ValidationError

import os
import re
import uuid
from django.core.exceptions import ValidationError
from django.utils.deconstruct import deconstructible

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

        if user is None or not getattr(user, "pk", None):
            return

        from apps.accounts.models import PasswordHistory


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

        return _("Your password cannot be the same as any of your last 5 passwords.")


def sniff_mime_type(header_bytes):
    """
    Pure Python header signature sniffing.
    Works natively on Windows, Linux, and macOS without requiring C libmagic DLLs.
    """
    if header_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    elif header_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    elif header_bytes.startswith(b"%PDF-"):
        return "application/pdf"
    elif header_bytes.startswith(b"GIF87a") or header_bytes.startswith(b"GIF89a"):
        return "image/gif"
    elif header_bytes.startswith(b"RIFF") and len(header_bytes) >= 12 and header_bytes[8:12] == b"WEBP":
        return "image/webp"

    # Optional fallback if libmagic C library is available
    try:
        import magic
        detector = magic.Magic(mime=True)
        return detector.from_buffer(header_bytes).lower()
    except Exception:
        return "application/octet-stream"


@deconstructible
class SecureFileUploadValidator:
    """
    Validates files by checking allowed extensions and sniffing header bytes.
    Enforces maximum size to prevent denial-of-service (DoS) attacks.
    """
    def __init__(self, allowed_extensions, allowed_mimetypes, max_size_mb=10):
        self.allowed_extensions = [ext.lower() for ext in allowed_extensions]
        self.allowed_mimetypes = [m.lower() for m in allowed_mimetypes]
        self.max_size_mb = max_size_mb

    def __call__(self, file):
        # 1. Size Validation
        max_size = self.max_size_mb * 1024 * 1024
        if file.size > max_size:
            raise ValidationError(f"File size exceeds limit of {self.max_size_mb} MB.")

        # 2. Extension Validation
        ext = os.path.splitext(file.name)[1].lower().replace(".", "")
        if ext not in self.allowed_extensions:
            raise ValidationError(f"Unsupported file extension: .{ext}.")

        # 3. Magic Header Byte Sniffing (MIME validation)
        file.seek(0)
        file_header = file.read(2048)
        file.seek(0)

        detected_mime = sniff_mime_type(file_header)

        # Standard JPEG alias handling
        if detected_mime == "image/jpeg" and "image/pjpeg" in self.allowed_mimetypes:
            detected_mime = "image/jpeg"

        if detected_mime not in self.allowed_mimetypes:
            # Secondary check with PIL if image mime
            if any(m.startswith("image/") for m in self.allowed_mimetypes):
                try:
                    from PIL import Image
                    file.seek(0)
                    img = Image.open(file)
                    img.verify()
                    file.seek(0)
                    return
                except Exception:
                    pass
            raise ValidationError(f"File contents do not match allowed formats. Detected: {detected_mime}")


def randomize_upload_filename(instance, filename):
    """Randomize the file name to prevent directory traversal and overwrite attacks."""
    ext = os.path.splitext(filename)[1].lower()
    random_name = f"{uuid.uuid4()}{ext}"
    folder_name = instance.__class__.__name__.lower()
    return os.path.join(folder_name, random_name)

