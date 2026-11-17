import hashlib
import json
import uuid

from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone


def get_client_ip(request):
    """Safely extract client IP address from request."""
    if not request:
        return None
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "").strip()


def generate_hash(
    previous_hash,
    timestamp,
    user_id,
    ip_address,
    action,
    model_name,
    record_id,
    changes_json,
):
    """Generate SHA-256 hash for the audit record, incorporating IP address."""
    payload = (
        f"{previous_hash}{timestamp}{user_id}{ip_address or 'UNKNOWN'}"
        f"{action}{model_name}{record_id}{changes_json}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get_changes(old_instance, new_instance, fields):
    """Compare fields and return a diff dictionary."""
    changes = {}
    if not old_instance:
        for field in fields:
            val = getattr(new_instance, field, None)
            if val is not None:
                changes[field] = {"old": None, "new": str(val)}
        return changes

    for field in fields:
        old_val = getattr(old_instance, field, None)
        new_val = getattr(new_instance, field, None)
        if old_val != new_val:
            changes[field] = {"old": str(old_val), "new": str(new_val)}
    return changes


@transaction.atomic
def log_audit(
    request=None,
    action=None,
    instance=None,
    changes=None,
    user=None,
    **kwargs,
):
    """
    Append an immutable, hash-chained log entry.
    Locks the latest record to prevent race conditions in the chain.
    Accepts calls from both views (with request) and models (with user keyword).
    """
    from apps.core.models import AuditLog

    if not changes and action not in ("APPROVE", "EXPORT"):
        return None

    changes_json = json.dumps(changes or {}, cls=DjangoJSONEncoder, sort_keys=True)
    timestamp = timezone.now()

    # Resolve user object and IP address safely
    user_obj = None
    ip_addr = None

    actor = user if user is not None else request
    if hasattr(actor, "user"):
        user_obj = (
            actor.user if getattr(actor.user, "is_authenticated", False) else None
        )
        ip_addr = get_client_ip(actor)
    elif getattr(actor, "is_authenticated", False):
        user_obj = actor
        if hasattr(request, "META"):
            ip_addr = get_client_ip(request)
    elif hasattr(request, "META"):
        ip_addr = get_client_ip(request)

    user_id = str(user_obj.pk) if user_obj else "SYSTEM"
    model_name = instance.__class__.__name__ if instance else "Unknown"
    record_id = str(instance.pk) if instance else "0"

    last_log = (
        AuditLog.objects.select_for_update()
        .order_by("-timestamp", "-id")
        .first()
    )
    previous_hash = last_log.hash if last_log else "GENESIS"

    new_hash = generate_hash(
        previous_hash,
        timestamp.isoformat(),
        user_id,
        ip_addr,
        action or "UNKNOWN",
        model_name,
        record_id,
        changes_json,
    )

    return AuditLog.objects.create(
        user=user_obj,
        ip_address=ip_addr,
        action=action or "UNKNOWN",
        model_name=model_name,
        record_id=record_id,
        changes=changes or {},
        previous_hash=previous_hash,
        hash=new_hash,
        timestamp=timestamp,
    )