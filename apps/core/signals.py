from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.core.models import MolecularTest, QcRecord, next_code


@receiver(post_save, sender=MolecularTest)
def create_qc_record_for_test(sender, instance, created, **kwargs):
    """Auto-create a pending QC record when a molecular test is registered."""
    if not created:
        return
    if hasattr(instance, "qc_record"):
        return

    country = None
    if instance.sample_id and instance.sample.client_id:
        country = instance.sample.client.country

    QcRecord.objects.create(
        code=next_code("QC", country),
        test=instance,
        sample=instance.sample,
        decision=QcRecord.Decision.PENDING,
        safety_class=QcRecord.SafetyClass.NOT_APPLICABLE,
    )