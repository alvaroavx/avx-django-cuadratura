import uuid
from django.db import models
from organizations.models import TaxpayerOrganization
from sales.models import Sale

class Payment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(TaxpayerOrganization, on_delete=models.PROTECT, related_name="payments")
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name="payments")
    payment_date = models.DateField()
    amount = models.PositiveBigIntegerField()
    transfer_reference = models.CharField(max_length=160, blank=True)
    registered_at = models.DateTimeField(auto_now_add=True)
    reconciled_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT)
    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(amount__gt=0), name="payment_amount_positive")]
