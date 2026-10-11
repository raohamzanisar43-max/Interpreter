import time

from django.core.management.base import BaseCommand
from django.utils import timezone

from compliance import jobs


class Command(BaseCommand):
    help = "Run scheduled jobs: auto-close, deadline reminders, retention cleanup, token cleanup."

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true", help="keep running (every --interval seconds)")
        parser.add_argument("--interval", type=int, default=300)

    def handle(self, *args, **opts):
        last_daily = None
        while True:
            self.stdout.write(f"[{timezone.now():%H:%M:%S}] {jobs.run_all()}")
            if last_daily != timezone.localdate():
                jobs.cleanup_tokens()
                last_daily = timezone.localdate()
            if not opts["loop"]:
                break
            time.sleep(opts["interval"])
