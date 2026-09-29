from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("imports", "0002_confirmed_imports_append_only")]

    operations = [
        migrations.RemoveConstraint(
            model_name="importbatch",
            name="uq_import_batch_org_hash",
        ),
        migrations.AddConstraint(
            model_name="importbatch",
            constraint=models.UniqueConstraint(
                fields=("organization", "period", "file_hash"),
                name="uq_import_batch_org_period_hash",
            ),
        ),
    ]
