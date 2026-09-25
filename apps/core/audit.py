import hashlib
import json
import uuid
from django.db import transaction
from django.utils import timezone
from django.core.serializers.json import DjangoJSONEncoder


def generate_hash(previous_hash, timestamp, user_id, action, model_name, record_id, changes_json):
    """Generate SHA-256 hash for the audit record."""
    payload = f"{previous_hash}{timestamp}{user_id}{action}{model_name}{record_id}{changes_json}"
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
def log_audit(user, action, instance, changes):
    """
    Append an immutable, hash-chained log entry.
    Locks the latest record to prevent race conditions in the chain.
    """
    from apps.core.models import AuditLog

    if not changes and action not in ("APPROVE", "EXPORT"):
        return None

    changes_json = json.dumps(changes, cls=DjangoJSONEncoder, sort_keys=True)
    timestamp = timezone.now()
    
    user_obj = user if getattr(user, "is_authenticated", False) else None
    user_id = str(user_obj.pk) if user_obj else "SYSTEM"
    model_name = instance.__class__.__name__
    record_id = str(instance.pk)

    last_log = AuditLog.objects.select_for_update().order_by("-timestamp", "-id").first()
    previous_hash = last_log.hash if last_log else "GENESIS"

    new_hash = generate_hash(
        previous_hash,
        timestamp.isoformat(),
        user_id,
        action,
        model_name,
        record_id,
        changes_json,
    )

    return AuditLog.objects.create(
        user=user_obj,
        action=action,
        model_name=model_name,
        record_id=record_id,
        changes=changes,
        previous_hash=previous_hash,
        hash=new_hash,
        timestamp=timestamp,
    )