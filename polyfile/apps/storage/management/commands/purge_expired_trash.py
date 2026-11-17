"""Purge expired trash entries and clean up retained scaffolding.

Intended for cron-like deployments that do not run the long-lived deletion
worker. The deletion worker performs the same sweep inline (see
``run_deletion_worker --trash-sweep-interval``).

This command only *marks* expired entries for deletion (creates
``FsNodeDeletionJob`` rows). The physical removal is done by
``run_deletion_worker``.
"""

from django.core.management.base import BaseCommand

from polyfile.apps.storage.trash_service import (
    enqueue_expired_trash_purges,
    reap_trash_scaffolding,
)


class Command(BaseCommand):
    help = "Create deletion jobs for trash entries past their TTL and clean up scaffolding"

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--no-reap",
            action="store_true",
            help="Do not remove childless retained scaffolding directories",
        )

    def handle(self, *args, **options):
        created = enqueue_expired_trash_purges()
        self.stdout.write(f"Enqueued {created} trash purge job(s)")

        if not options["no_reap"]:
            reaped = reap_trash_scaffolding()
            self.stdout.write(f"Removed {reaped} retained scaffolding node(s)")
