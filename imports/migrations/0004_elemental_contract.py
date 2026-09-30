from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("imports", "0003_import_batch_hash_per_period"), ("payments", "0003_payment_external_identity")]
    operations = [
        migrations.AddField(model_name="importbatch", name="source_metadata", field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(
            model_name="importrow", name="payment",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="import_rows", to="payments.payment"),
        ),
    ]
