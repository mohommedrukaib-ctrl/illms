from django.contrib.auth import get_user_model
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.utils import timezone

User = get_user_model()


@receiver(pre_save, sender=User)
def track_password_change(sender, instance, **kwargs):
    """Record password history when password changes."""
    if not instance.pk:
        return

    try:
        old_user = User.objects.get(pk=instance.pk)
    except User.DoesNotExist:
        return

    if old_user.password != instance.password:
        instance.last_password_change = timezone.now()

        from .models import PasswordHistory

        PasswordHistory.objects.create(
            user=instance,
            password_hash=PasswordHistory.make_hash(instance.password),
        )

        # Keep only last 10 entries
        old_entries = (
            PasswordHistory.objects.filter(user=instance)
            .order_by("-created_at")[10:]
            .values_list("pk", flat=True)
        )
        PasswordHistory.objects.filter(pk__in=list(old_entries)).delete()