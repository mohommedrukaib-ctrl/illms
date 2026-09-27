"""
Helper to push in-app notifications to users.
"""
from apps.core.models import Notification


def push_notification(user, title, message="", level="info", url=""):
    """Create a notification for a specific user."""
    if not user:
        return None
    # Allow both authenticated users and plain User instances from ORM
    if hasattr(user, "is_authenticated") and not user.is_authenticated:
        return None
    return Notification.objects.create(
        user=user,
        level=level,
        title=title,
        message=message,
        url=url or "",
    )


def notify_self(user, title, message="", level="success", url=""):
    """Confirmation notification for the user who just saved something."""
    return push_notification(user, title, message=message, level=level, url=url)


def push_to_role(role, title, message="", level="info", url=""):
    """Push a notification to all active users with a given role."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    users = User.objects.filter(role=role, is_active=True, is_deleted=False)
    notifications = [
        Notification(user=user, level=level, title=title, message=message, url=url or "")
        for user in users
    ]
    if notifications:
        Notification.objects.bulk_create(notifications)
    return len(notifications)