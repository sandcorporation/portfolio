"""GitHub profile READMEs (farrar142 and sandcorporation/.github), generated from the site data.

The site is the source: profile tagline, the `ceo_intro`/`company_intro` block documents, the
`SiteProfile.github` extras and the public portfolio items that have a `service_url`. This module
owns only the frame (section titles, emoji, footer); every sentence comes from the data.
Blocks turn into GitHub-flavoured Markdown; block types it does not know are skipped.
"""

import re
from collections.abc import Callable
from typing import Literal
from urllib.parse import quote

from django.conf import settings

from content.github_profile import PublicProject
from content.models import PortfolioItem
from documents.blocks import (
    Block,
    CtaBlock,
    CtaTargetUrl,
    KpiBlock,
    MarkdownBlock,
    StepsBlock,
    TableBlock,
    TableCell,
)
from documents.validation import JSON, InvalidDocument, validate_document
from services import portfolio, profile

Kind = Literal["personal", "org"]

GENERATED_NOTE = "<!-- generated from https://sandcorp.co.kr — 손으로 고치지 마세요 -->"
GITHUB_OWNER = "farrar142"  # the README owner shown in the org footer
SERVICE_TITLE_SEPARATOR = " — "
KEYWORD_COUNT = 4

# name (lower-case) -> (label, shields.io colour, simple-icons logo or "", logo colour)
BADGES: dict[str, tuple[str, str, str, str]] = {
    "python": ("Python", "3776AB", "python", "white"),
    "django": ("Django", "092E20", "django", "white"),
    "kotlin": ("Kotlin", "7F52FF", "kotlin", "white"),
    "java": ("Java", "ED8B00", "openjdk", "white"),
    "spring boot": ("Spring Boot", "6DB33F", "springboot", "white"),
    "typescript": ("TypeScript", "3178C6", "typescript", "white"),
    "javascript": ("JavaScript", "F7DF1E", "javascript", "black"),
    "react": ("React", "20232A", "react", "61DAFB"),
    "next.js": ("Next.js", "000000", "nextdotjs", "white"),
    "react native": ("React Native", "20232A", "react", "61DAFB"),
    "node.js": ("Node.js", "339933", "nodedotjs", "white"),
    "postgresql": ("PostgreSQL", "4169E1", "postgresql", "white"),
    "mariadb": ("MariaDB", "003545", "mariadb", "white"),
    "redis": ("Redis", "DC382D", "redis", "white"),
    "kafka": ("Kafka", "231F20", "apachekafka", "white"),
    "elasticsearch": ("Elasticsearch", "005571", "elasticsearch", "white"),
    "celery": ("Celery", "37814A", "celery", "white"),
    "docker": ("Docker", "2496ED", "docker", "white"),
    "kubernetes": ("Kubernetes", "326CE5", "kubernetes", "white"),
    "jenkins": ("Jenkins", "D24939", "jenkins", "white"),
    "github actions": ("GitHub Actions", "2088FF", "githubactions", "white"),
    "aws": ("AWS", "232F3E", "amazonwebservices", "white"),
    "claude": ("Claude Code", "D97757", "anthropic", "white"),
}
UNKNOWN_BADGE_COLOR = "555555"


# --- site links: every link to the site carries the tracking query ---


def _tag_one(campaign: str) -> Callable[[re.Match[str]], str]:
    query = f"utm_source=github&utm_medium=readme&utm_campaign={campaign}"

    def tag(match: re.Match[str]) -> str:
        base, rest = match.group(1), match.group(2)
        fragment = ""
        if "#" in rest:
            rest, fragment = rest.split("#", 1)
            fragment = "#" + fragment
        if "utm_source=" in rest:
            return match.group(0)
        joiner = "&" if "?" in rest else "?"
        return f"{base}{rest}{joiner}{query}{fragment}"

    return tag


def tag_site_links(text: str, campaign: Kind) -> str:
    site = re.escape(settings.SITE_URL)
    pattern = re.compile(rf"({site})((?:[/?#][^\s)<>\"']*)?)(?=[\s)<>\"']|$)")
    return pattern.sub(_tag_one(campaign), text)


# --- small Markdown helpers ---


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\r", "").replace("\n", "<br>").strip()


def _line(text: str) -> str:
    return " ".join(text.split())


def table(columns: list[str], rows: list[list[str]]) -> str:
    head = "| " + " | ".join(_cell(c) for c in columns) + " |"
    rule = "|" + "|".join("---" for _ in columns) + "|"
    body = ["| " + " | ".join(_cell(c) for c in row) + " |" for row in rows]
    return "\n".join([head, rule, *body])


def _grid(block: TableBlock) -> list[list[str]]:
    """Rows as a plain grid: merged cells keep their text in the first slot, empty after."""
    width = len(block.columns)
    carried: dict[int, int] = {}  # column -> rows still covered by a rowspan above
    grid: list[list[str]] = []
    for row in block.rows:
        out: list[str] = []
        cells = iter(row)
        pending: dict[int, int] = {}
        while len(out) < width:
            column = len(out)
            if carried.get(column, 0) > 0:
                out.append("")
                continue
            cell = next(cells, None)
            if cell is None:
                out.append("")
                continue
            text, colspan, rowspan = (
                (cell.text, cell.colspan, cell.rowspan)
                if isinstance(cell, TableCell)
                else (cell, 1, 1)
            )
            out.append(text)
            for extra in range(colspan):
                if extra:
                    out.append("")
                if rowspan > 1:
                    pending[column + extra] = rowspan - 1
        carried = {c: n - 1 for c, n in carried.items() if n > 1}
        carried.update(pending)
        grid.append(out[:width])
    return grid


def _heading(title: str | None, level: int) -> str:
    return f"{'#' * level} {_line(title)}\n\n" if title else ""


# --- blocks -> GFM ---


def render_block(block: Block, heading_level: int = 3) -> str:
    """One block as Markdown, or "" for a block type the README has no form for."""
    if isinstance(block, MarkdownBlock):
        return (_heading(block.title, heading_level) + block.body.strip()).strip()
    if isinstance(block, TableBlock):
        parts = [_heading(block.title, heading_level) + table(block.columns, _grid(block))]
        if block.unit:
            parts.append(f"<sub>{block.unit}</sub>")
        parts += [f"<sub>{note}</sub>" for note in block.footnotes]
        return "\n\n".join(parts)
    if isinstance(block, KpiBlock):
        line = " · ".join(f"**{_line(i.value)}** {_line(i.label)}" for i in block.items)
        return _heading(block.title, heading_level) + line
    if isinstance(block, StepsBlock):
        lines = []
        for number, step in enumerate(block.items, 1):
            text = f"**{_line(step.title)}**" + (f" — {_line(step.body)}" if step.body else "")
            lines.append(f"{number}. {text}")
        return _heading(block.title, heading_level) + "\n".join(lines)
    if isinstance(block, CtaBlock):
        links = [
            f"[{_line(item.label)}]({item.target.href})"
            for item in block.items
            if isinstance(item.target, CtaTargetUrl)
        ]
        return " · ".join(links)
    return ""


def _blocks(document: dict[str, JSON]) -> list[Block]:
    try:
        parsed = validate_document(document)
    except InvalidDocument:
        return []
    return [block for tab in parsed.tabs for block in tab.blocks]


def _join(parts: list[str]) -> str:
    return "\n\n".join(part for part in parts if part.strip())


# --- site data ---


def ceo_name(ceo_intro: dict[str, JSON]) -> str:
    """The first Markdown block's title without 「대표」, e.g. '김한얼 대표' -> '김한얼'."""
    for block in _blocks(ceo_intro):
        if isinstance(block, MarkdownBlock):
            return _line((block.title or "").replace("대표", ""))
    return ""


def _service_rows(items: list[PortfolioItem]) -> list[tuple[str, str, str, list[str]]]:
    """(name, url, one-liner, keywords) for public items with a service address, in order."""
    rows = []
    for item in items:
        if not (item.is_public and item.service_url):
            continue
        name, separator, rest = item.title.partition(SERVICE_TITLE_SEPARATOR)
        rows.append(
            (
                _line(name),
                item.service_url,
                _line(rest) if separator else _line(item.summary),
                item.tag_list()[:KEYWORD_COUNT],
            )
        )
    return rows


def badge(name: str) -> str:
    label, color, logo, logo_color = BADGES.get(
        name.lower(), (name, UNKNOWN_BADGE_COLOR, "", "white")
    )
    text = quote(label.replace("-", "--").replace("_", "__").replace(" ", "_"), safe="_.")
    query = "style=flat-square" + (f"&logo={logo}&logoColor={logo_color}" if logo else "")
    return f"![{name}](https://img.shields.io/badge/{text}-{color}?{query})"


def _projects(projects: list[PublicProject], kind: Kind) -> list[PublicProject]:
    return [p for p in projects if p.scope in (kind, "both")]


def _project_lines(projects: list[PublicProject]) -> str:
    return "\n".join(
        f"- [**{_line(p.name)}**]({p.url})"
        + (f" — {_line(p.description)}" if p.description else "")
        for p in projects
    )


def _site_host() -> str:
    return re.sub(r"^https?://", "", settings.SITE_URL)


def _site_link(text: str) -> str:
    return f"[{text}]({settings.SITE_URL})"


# --- the two documents ---


def _finish(parts: list[str], kind: Kind) -> str:
    # The note is fixed text: only the body gets the tracking query.
    return GENERATED_NOTE + "\n\n" + tag_site_links(_join(parts), kind) + "\n"


def render_personal() -> str:
    data = profile.get_profile()
    github = data.github
    services = _service_rows(portfolio.public_items())
    parts: list[str] = []
    name = ceo_name(data.ceo_intro)
    if name:
        parts.append(f"### 안녕하세요, {name}입니다 👋")
    if data.tagline:
        parts.append(f"**{_line(data.tagline)}**")
    parts += [github.personal_intro.strip(), "---"]
    if services:
        parts.append("#### 🚀 지금 운영 중인 서비스")
        parts.append(
            table(
                ["서비스", "한 줄 소개", "키워드"],
                [
                    [f"[**{n}**]({url})", desc, " · ".join(keywords)]
                    for n, url, desc, keywords in services
                ],
            )
        )
        parts.append(
            f"👉 프로젝트 상세는 {_site_link(_site_host())}의 포트폴리오에 정리해 두었습니다."
        )
    projects = _projects(github.public_projects, "personal")
    if projects:
        parts += ["#### 🧪 공개 프로젝트", _project_lines(projects)]
    if github.stack_badges:
        parts += ["#### 🛠️ 기술 스택", "\n".join(badge(n) for n in github.stack_badges)]
    if github.contact_note.strip():
        parts += ["#### 📫 연락", github.contact_note.strip()]
    return _finish(parts, "personal")


def render_org() -> str:
    data = profile.get_profile()
    github = data.github
    services = _service_rows(portfolio.public_items())
    blocks = _blocks(data.company_intro)
    links = " · ".join(_site_link(label) for label in ("웹사이트", "포트폴리오", "문의하기"))
    head = ['<div align="center">', "## Sandcorp"]
    if data.tagline:
        head.append(f"**{_line(data.tagline)}**")
    head.append(links)
    parts = ["\n\n".join(head) + "\n\n</div>", "---"]
    parts += [render_block(b) for b in blocks if isinstance(b, MarkdownBlock)]
    if services:
        parts.append("### 🚀 운영 중인 서비스")
        parts.append(
            table(
                ["서비스", "소개"],
                [[f"[**{n}**]({url})", desc] for n, url, desc, _ in services],
            )
        )
    parts += [render_block(b) for b in blocks if isinstance(b, TableBlock)]
    projects = _projects(github.public_projects, "org")
    if projects:
        parts += ["### 📂 공개 저장소", _project_lines(projects)]
    parts += [
        "---",
        '<div align="center">\n'
        f'대표 <a href="https://github.com/{GITHUB_OWNER}">@{GITHUB_OWNER}</a> · '
        f'프로젝트 문의는 <a href="{settings.SITE_URL}">{_site_host()}</a>\n'
        "</div>",
    ]
    return _finish(parts, "org")


def render(kind: Kind) -> str:
    return render_personal() if kind == "personal" else render_org()
