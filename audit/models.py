import uuid
from django.db import models
from organizations.models import TaxpayerOrganization

class AuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(TaxpayerOrganization, on_delete=models.PROTECT, related_name="audit_events")
    actor = models.ForeignKey("accounts.User", on_delete=models.PROTECT, null=True)
    action = models.CharField(max_length=100)
    target_type = models.CharField(max_length=100)
    target_id = models.UUIDField(null=True)
    occurred_at = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict, blank=True)
    class Meta:
        ordering = ["-occurred_at"]

