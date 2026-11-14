import uuid

from django.db import migrations, models


def clear_deletion_jobs(apps, schema_editor):
    """Drop stale deletion jobs: they predate UUID identity and have no usable root reference."""
    apps.get_model("storage", "FsNodeDeletionJob").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("storage", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(clear_deletion_jobs, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="fsnodedeletionjob",
            name="root_path",
        ),
        migrations.AddField(
            model_name="fsnodedeletionjob",
            name="root_node_uuid",
            field=models.UUIDField(db_index=True, default=uuid.uuid4),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="fsnodedeletionjob",
            name="root_node_name",
            field=models.CharField(default="", max_length=255),
            preserve_default=False,
        ),
    ]
