"""`manage.py sync_shorts`: register the YouTube channel's new Shorts now (issue 211).

The compose `worker` loop does this every 30 minutes (services/shorts.sync_if_due); this runs
`shorts.sync_channel()` once by hand, without waiting for the schedule.
"""

from django.core.management.base import BaseCommand

from services import shorts


class Command(BaseCommand):
    help = "YouTube 채널의 새 쇼츠를 지금 등록한다"

    def handle(self, *args: object, **options: object) -> None:
        result = shorts.sync_channel()
        self.stdout.write(f"원천: {result.source}, 새 쇼츠 {result.created}개")
