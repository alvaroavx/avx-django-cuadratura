from .models import AuditEvent

def record_event(*, organization, actor, action, target, metadata=None):
    return AuditEvent.objects.create(
        organization=organization, actor=actor, action=action,
        target_type=target._meta.label, target_id=target.pk, metadata=metadata or {},
    )

