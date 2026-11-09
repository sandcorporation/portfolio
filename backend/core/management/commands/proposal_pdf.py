"""`manage.py proposal_pdf <slug> [--platform|--no-platform] [--out -]` (#225).

Renders the proposal's current document through the draft print link and writes the PDF bytes to
stdout (or a file). Nothing is written to the database or the bucket and the proposal's
`platform_mode` stays as it is: `--platform` / `--no-platform` only choose the mode of this PDF.
For checking a live draft without touching it; text leftovers go to stderr.
"""

import sys
from argparse import ArgumentParser
from typing import TypedDict

from django.core.management.base import BaseCommand, CommandError

from services import pdf, proposals
from services.errors import ServiceError


class Options(TypedDict):
    slug: str
    platform: bool | None
    out: str


class Command(BaseCommand):
    help = "제안서 지금 문서를 PDF로 렌더해 stdout(또는 파일)에 낸다. DB·버킷에 쓰지 않는다"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "slug", help="제안서 slug. 「-」로 시작하는 옛 slug는 `-- <slug>`로 넘긴다"
        )
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--platform", dest="platform", action="store_true", default=None)
        mode.add_argument("--no-platform", dest="platform", action="store_false")
        parser.add_argument("--out", default="-", help="파일 경로, '-'면 stdout (기본)")

    def handle(self, *args: object, **options: object) -> None:
        opts = Options(
            slug=str(options["slug"]),
            platform=options["platform"] if isinstance(options["platform"], bool) else None,
            out=str(options["out"]),
        )
        try:
            p, mode, data = pdf.render_draft(opts["slug"], opts["platform"])
        except ServiceError as exc:
            raise CommandError(str(exc)) from None
        if opts["out"] == "-":
            sys.stdout.buffer.write(data)
            sys.stdout.buffer.flush()
        else:
            with open(opts["out"], "wb") as f:
                f.write(data)
        found = proposals.leaks_of(p, mode)
        self.stderr.write(f"platform_mode={mode} bytes={len(data)} leaks={len(found)}")
        for piece in found:
            self.stderr.write(f"  leak: {piece}")
