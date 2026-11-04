"""외주 플랫폼 제출용 모드 (#225): 제안서에서 회사명·연락처·우리 도메인을 뺀다.

위시켓·크몽은 지원서·첨부에 회사명·홈페이지·연락처가 들어가면 제재한다. 모드가 켜진 제안서
(`Proposal.platform_mode`, 발행하면 `ProposalRevision.platform_mode`로 고정)는 미리보기·발행
페이지·인쇄·PDF 어디서나 이 모듈을 거친 데이터로 그린다:

- 공급자 칸은 「제안사」만 남긴다 (`SUPPLIER_NAME`).
- 문서 안 링크 중 우리 것(`sandcorp.co.kr`과 하위 도메인, 사이트 상대 경로 `/…`, mailto:·tel:)은
  href를 지운다: 마크다운·HTML 링크는 글자만, CTA 버튼은 항목째 뺀다(남는 항목이 없으면 블록째).
- `embed` 블록(flow.sandcorp.co.kr)은 뺀다. 사례 카드는 주소(slug)를 비운다.

- 렌더되는 글(문서 블록 글, 사례 카드 제목·설명, 탭 제목, 제안서 제목·부제·받는 분)에서
  회사명과 우리 도메인을 가린다 (#229, `mask_text`): 「샌드코프」→「저희」, 「Sandcorp Flow」
  같은 앞머리 「Sandcorp 」는 지우고 홀로 쓰인 「Sandcorp」→「저희」, `sandcorp.co.kr` 주소와
  이메일 주소는 지운다. 저장된 문서는 그대로다(그릴 때만 가린다).

전화번호처럼 가리지 않는 것과 가린 뒤에도 남은 것은 `leaks`가 찾아 작성자에게 알린다.
"""

import re
from collections.abc import Iterator

from documents.validation import JSON

SUPPLIER_NAME = "제안사"
PAGE_TITLE = "제안서"

# Values the server fills with media addresses (storage URLs): not text, never rewritten.
_MEDIA_KEYS = frozenset({"url", "poster_url", "cover_url"})
# Values that are identifiers, not shown as text: never masked.
_ID_KEYS = frozenset(
    {"type", "id", "tab_id", "block_id", "item_id", "kind", "slug", "variant", "href", "src"}
)
# Page-data keys that are routes of this page (not shown as text).
_ROUTE_KEYS = frozenset({"media_endpoint", "tab_endpoint", "pdf_url", "csrf_token"})

_OUR_HOST = re.compile(r"^(?:https?:)?//(?:[a-z0-9-]+\.)*sandcorp\.co\.kr(?:[/:?#]|$)", re.I)

# [text](href) and [text](<href> "title"); images (![...]) are left alone.
_MD_LINK = re.compile(r"(?<!!)\[([^\]]*)\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
# <https://…> autolinks.
_MD_AUTOLINK = re.compile(r"<((?:https?:)?//[^>\s]+|mailto:[^>\s]+|tel:[^>\s]+)>")
_HTML_ANCHOR = re.compile(r"<a\b([^>]*)>(.*?)</a\s*>", re.I | re.S)
_HTML_HREF = re.compile(r"""\bhref\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", re.I)

LEAK_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"샌드\s*코프"),
    re.compile(r"sand\s*corp", re.I),
    re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),
    # 010-1234-5678, 02-123-4567, 031 123 4567, +82-10-1234-5678, (02)1234-5678, 01012345678
    re.compile(
        r"(?<![\w-])(?:\+82[-\s.]?\(?0?\d{1,2}\)?|\(?0\d{1,2}\)?)[-\s.)]?\d{3,4}[-\s.]\d{4}(?!\d)"
    ),
    re.compile(r"(?<!\d)01[016789]\d{7,8}(?!\d)"),
)


_MASK_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_MASK_DOMAIN = re.compile(
    r"(?:https?:)?(?://)?(?:[a-z0-9-]+\.)*sandcorp\.co\.kr(?:/[\w\-./?=&%#~+]*)?", re.I
)
_MASK_KO = re.compile(r"샌드\s*코프(?:\s*\(\s*sand\s*corp\s*\))?", re.I)
_MASK_EN_PREFIX = re.compile(r"(?<![A-Za-z])sand\s*corp(?:-|\s+(?=[A-Za-z0-9가-힣]))", re.I)
_MASK_EN = re.compile(r"(?<![A-Za-z])sand\s*corp(?![A-Za-z])(?:\s*\(\s*샌드\s*코프\s*\))?", re.I)
_EMPTY_PARENS = re.compile(r"[(\[]\s*[)\]]")
_SPACES = re.compile(r"(?<=\S)[ \t]{2,}(?=\S)")


def mask_text(text: str) -> str:
    """Text with our name and our addresses taken out: 「샌드코프」 → 「저희」, a leading
    「Sandcorp 」 (as in 「Sandcorp Flow」) or 「sandcorp-」 dropped, a lone 「Sandcorp」 →
    「저희」, `sandcorp.co.kr` addresses and email addresses removed. Unchanged text is
    returned as is."""
    out = _MASK_EMAIL.sub("", text)
    out = _MASK_DOMAIN.sub("", out)
    out = _MASK_KO.sub("저희", out)
    out = _MASK_EN_PREFIX.sub("", out)
    out = _MASK_EN.sub("저희", out)
    if out == text:
        return text
    out = _EMPTY_PARENS.sub("", out)
    out = _SPACES.sub(" ", out)
    return "\n".join(line.rstrip() if line.strip() else "" for line in out.split("\n")).strip()


def is_ours(href: str) -> bool:
    """Our site, our subdomains, site-relative paths, and contact links (mailto:, tel:)."""
    h = href.strip()
    lowered = h.lower()
    if lowered.startswith(("mailto:", "tel:")):
        return True
    if h.startswith("/") and not h.startswith("//"):
        return True
    return bool(_OUR_HOST.match(h))


def strip_text(text: str) -> str:
    """Markdown / HTML text with links to us turned into their plain words."""

    def md(m: re.Match[str]) -> str:
        return m.group(1) if is_ours(m.group(2)) else m.group(0)

    def auto(m: re.Match[str]) -> str:
        return "" if is_ours(m.group(1)) else m.group(0)

    def anchor(m: re.Match[str]) -> str:
        href = _HTML_HREF.search(m.group(1))
        target = next((g for g in href.groups() if g is not None), "") if href else ""
        return m.group(2) if href and is_ours(target) else m.group(0)

    text = _MD_LINK.sub(md, text)
    text = _MD_AUTOLINK.sub(auto, text)
    return _HTML_ANCHOR.sub(anchor, text)


def _strip(value: JSON, key: str = "") -> JSON:
    if isinstance(value, str):
        if key in _MEDIA_KEYS:
            return value
        stripped = strip_text(value)
        return stripped if key in _ID_KEYS else mask_text(stripped)
    if isinstance(value, list):
        return [_strip(v, key if key in _MEDIA_KEYS else "") for v in value]
    if isinstance(value, dict):
        return {k: _strip(v, k) for k, v in value.items()}
    return value


def _block(block: JSON) -> JSON | None:
    if not isinstance(block, dict):
        return block
    kind = block.get("type")
    if kind == "embed":
        return None
    out = _strip(block)
    assert isinstance(out, dict)
    if kind == "cta":
        items = out.get("items")
        kept = [
            item for item in (items if isinstance(items, list) else []) if not _is_our_cta(item)
        ]
        if not kept:
            return None
        out["items"] = kept
    if kind == "case-ref":
        items = out.get("items")
        for item in items if isinstance(items, list) else []:
            case = item.get("case") if isinstance(item, dict) else None
            if isinstance(case, dict):
                case["slug"] = ""
    return out


def _is_our_cta(item: JSON) -> bool:
    target = item.get("target") if isinstance(item, dict) else None
    if not isinstance(target, dict) or target.get("kind") != "url":
        return False
    href = target.get("href")
    return isinstance(href, str) and is_ours(href)


def strip_document(document: dict[str, JSON]) -> dict[str, JSON]:
    """A copy of a (served) document without links to us, embeds or case addresses."""
    out: dict[str, JSON] = {}
    for key, value in document.items():
        if key != "tabs" or not isinstance(value, list):
            out[key] = _strip(value, key)
            continue
        tabs: list[JSON] = []
        for tab in value:
            if not isinstance(tab, dict):
                tabs.append(tab)
                continue
            new_tab = {k: _strip(v, k) for k, v in tab.items() if k != "blocks"}
            blocks = tab.get("blocks")
            new_tab["blocks"] = [
                b for b in (_block(b) for b in (blocks if isinstance(blocks, list) else [])) if b
            ]
            tabs.append(new_tab)
        out["tabs"] = tabs
    return out


def _texts(value: JSON, key: str = "") -> Iterator[str]:
    if key in _MEDIA_KEYS or key in _ROUTE_KEYS:
        return
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for v in value:
            yield from _texts(v)
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from _texts(v, k)


def leaks(data: JSON) -> list[str]:
    """Pieces of text (title, subtitle, recipient, document) that still name us or carry an
    email or a phone number, each with a little context, in order of appearance, no repeats.
    Media addresses and the page's own routes are not text and are skipped."""
    found: list[str] = []
    for text in _texts(data):
        for pattern in LEAK_PATTERNS:
            for m in pattern.finditer(text):
                start, end = max(0, m.start() - 12), min(len(text), m.end() + 12)
                piece = text[start:end].replace("\n", " ").strip()
                if piece not in found:
                    found.append(piece)
    return found
