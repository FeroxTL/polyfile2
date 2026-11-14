from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("storage", "0002_fs_node_deletion_job_root_node"),
    ]

    operations = [
        migrations.AlterField(
            model_name="fsnodearchiveitem",
            name="object_key",
            field=models.CharField(blank=True, max_length=1024),
        ),
    ]
