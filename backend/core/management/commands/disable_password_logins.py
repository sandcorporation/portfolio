"""Make password logins impossible (issue #29): the admin signs in through sandcorp-auth only.

`manage.py disable_password_logins` empties the password of every user (hash becomes unusable,
so no password verifies); `--username NAME` (repeatable) limits it to those users. Sessions and
the staff flag stay as they are. Safe to run again.
"""

from argparse import ArgumentParser
from typing import Any

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Set an unusable password on all users (or only --username ones)."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--username", action="append", default=[], help="repeatable")

    def handle(self, *args: Any, **options: Any) -> None:  # noqa: ANN401 - Django command signature
        names: list[str] = options["username"]
        users = User.objects.filter(username__in=names) if names else User.objects.all()
        missing = set(names) - set(users.values_list("username", flat=True))
        if missing:
            raise CommandError(f"no such user: {', '.join(sorted(missing))}")
        count = 0
        for user in users:
            user.set_unusable_password()
            user.save(update_fields=["password"])
            count += 1
        self.stdout.write(f"password logins disabled for {count} user(s)")
