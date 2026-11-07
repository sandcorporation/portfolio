"""`manage.py glitchtip_test [message]`: send one test error to GlitchTip (issue 235).

Raises and captures `GlitchTipOnboardingTest`, flushes, and prints the event id, so the
`portfolio-backend` project shows an issue with the deployed release and environment. Without a
DSN (the SDK is off) it says so. Always exits 0.
"""

from argparse import ArgumentParser

import sentry_sdk
from django.core.management.base import BaseCommand


class GlitchTipOnboardingTest(Exception):
    """The one exception this command sends on purpose."""


class Command(BaseCommand):
    help = "GlitchTip에 시험 오류 하나를 보낸다"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("message", nargs="?", default="portfolio GlitchTip 연동 시험")

    def handle(self, *args: object, **options: object) -> None:
        if not sentry_sdk.get_client().dsn:
            self.stdout.write("DSN 없음 — 보내지 않았다")
            return
        try:
            raise GlitchTipOnboardingTest(str(options["message"]))
        except GlitchTipOnboardingTest as exc:
            event_id = sentry_sdk.capture_exception(exc)
        sentry_sdk.flush(timeout=10)
        self.stdout.write(f"보냄: event_id={event_id}")
