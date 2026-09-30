from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("payments", "0002_payment_payment_amount_positive")]
    operations = [
        migrations.AddField(model_name="payment", name="origin_system", field=models.CharField(blank=True, max_length=80)),
        migrations.AddField(model_name="payment", name="external_id", field=models.CharField(blank=True, max_length=160)),
        migrations.AddConstraint(
            model_name="payment",
            constraint=models.UniqueConstraint(
                fields=("organization", "origin_system", "external_id"),
                condition=~models.Q(external_id=""),
                name="uq_payment_org_origin_external",
            ),
        ),
    ]
