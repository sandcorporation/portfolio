"""`manage.py prune_personal_data`: drop what the privacy policy keeps for a year (issue 201).

The compose `worker` already does this once a day (services/retention.py `prune_if_due`); this
command runs it now, for a manual check or a one-off cleanup.
"""

from django.core.management.base import BaseCommand

from services import retention


class Command(BaseCommand):
    help = "보유 기간(1년)이 지난 문의를 지우고 제안서 열람 기록의 IP·User-Agent를 비운다"

    def handle(self, *args: object, **options: object) -> None:
        pruned = retention.prune()
        self.stdout.write(
            f"문의 {pruned.inquiries}건 삭제, "
            f"제안서 열람 기록 {pruned.proposal_events}건 IP·UA 삭제"
        )
