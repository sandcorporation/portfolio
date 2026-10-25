"""Per-item link-preview cards (#125): a 1200x630 PNG with the brand frame, the title and the
cover fitted whole (contain) so no platform crops it.

The card is composed on the first request and cached as a file; the cache key hashes everything
the picture depends on (kind, slug, cover, timestamps, title, `CARD_VERSION`), and the same hash
(`?v=`) goes into the meta tags so platforms fetch a new card when the content changes.
The cache directory may vanish on redeploy: a missing file is simply composed again."""

import hashlib
import io
import logging
import os
import re
import tempfile
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from django.conf import settings
from PIL import Image, ImageDraw, ImageFont

from adapters.storage import Bucket, ObjectStorage, get_storage
from content.models import BlogPost, Media, PortfolioItem

log = logging.getLogger(__name__)

Kind = Literal["work", "blog"]
CARD_VERSION = 2  # bump when the drawing changes
WIDTH, HEIGHT = 1200, 630
MAX_BYTES = 280 * 1024
COVER_READ_SECONDS = 5
MAX_COVER_BYTES = 20 * 1024 * 1024
FONT_DIR = Path(__file__).resolve().parent.parent / "core" / "og" / "fonts"

INK = (27, 29, 36)
GOLD_DARK = (138, 98, 20)
GOLD = (217, 173, 76)
NAVY = (30, 58, 138)
LINE = (226, 228, 234)
WHITE = (255, 255, 255)
Point = tuple[float, float]


@dataclass(frozen=True)
class CardSource:
    kind: Kind
    slug: str
    title: str
    cover: Media
    key: str  # hash of everything the picture depends on

    @property
    def version(self) -> str:
        return self.key[:10]


def card_path(kind: Kind, slug: str) -> str:
    return f"/og/{kind}/{slug}.png"


def source_of(kind: Kind, slug: str) -> CardSource | None:
    """The public item or post with a cover, else None (no card: the default image is used)."""
    owner: PortfolioItem | BlogPost | None
    if kind == "work":
        owner = (
            PortfolioItem.objects.select_related("cover").filter(slug=slug, is_public=True).first()
        )
    else:
        owner = (
            BlogPost.objects.select_related("cover")
            .filter(slug=slug, status=BlogPost.Status.PUBLISHED, published_at__isnull=False)
            .first()
        )
    if owner is None or owner.cover is None:
        return None
    cover = owner.cover
    parts = [
        kind,
        slug,
        str(cover.pk),
        cover.object_key,
        str(cover.size),
        owner.updated_at.isoformat(),
        owner.title,
        str(CARD_VERSION),
    ]
    key = hashlib.sha256("\x1f".join(parts).encode()).hexdigest()
    return CardSource(kind, slug, owner.title, cover, key)


def preview_path(kind: Kind, slug: str) -> str | None:
    """`/og/<kind>/<slug>.png?v=<hash>` for a page with a cover, else None."""
    source = source_of(kind, slug)
    return None if source is None else f"{card_path(kind, slug)}?v={source.version}"


# --- cache ---


def cache_dir() -> Path:
    configured = getattr(settings, "OG_CACHE_DIR", "")
    return Path(configured) if configured else Path(tempfile.gettempdir()) / "portfolio-og"


def _file(source: CardSource) -> Path:
    return cache_dir() / f"{source.kind}-{source.slug}-{source.key[:32]}.png"


def cached(source: CardSource) -> bytes | None:
    try:
        return _file(source).read_bytes()
    except OSError:
        return None


def _store(source: CardSource, png: bytes) -> None:
    """Write atomically (two workers may race) and drop this item's older cards."""
    directory = cache_dir()
    try:
        directory.mkdir(parents=True, exist_ok=True)
        target = _file(source)
        tmp = target.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_bytes(png)
        tmp.replace(target)
        for old in directory.glob(f"{source.kind}-{source.slug}-*.png"):
            if old != target:
                old.unlink(missing_ok=True)
    except OSError as exc:
        log.warning("og card not cached: %r", exc)


class CardFailed(Exception):
    pass


def card_png(source: CardSource, *, storage: ObjectStorage | None = None) -> bytes:
    """The cached card, composed (and cached) when missing. Raises CardFailed."""
    found = cached(source)
    if found is not None:
        return found
    cover = _read_cover(source.cover, storage)
    try:
        png = compose(source.title, cover)
    except Exception as exc:  # Pillow raises many kinds for bad images
        raise CardFailed(f"compose failed: {exc!r}") from exc
    _store(source, png)
    return png


def _read_cover(media: Media, storage: ObjectStorage | None) -> bytes:
    if media.size > MAX_COVER_BYTES:
        raise CardFailed("cover too large")
    pool = ThreadPoolExecutor(max_workers=1)

    def fetch() -> bytes:
        store = storage or get_storage()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cover"
            store.download_file(Bucket.PUBLIC, media.object_key, path)
            return path.read_bytes()

    try:
        return pool.submit(fetch).result(timeout=COVER_READ_SECONDS)
    except Exception as exc:  # includes the timeout
        raise CardFailed(f"cover not read: {exc!r}") from exc
    finally:
        pool.shutdown(wait=False)


# --- drawing ---


def _font(weight: Literal["Bold", "SemiBold"], size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / f"Pretendard-{weight}.otf"), size)


def _bezier(p0: Point, p1: Point, p2: Point, p3: Point, steps: int = 24) -> list[Point]:
    out: list[Point] = []
    for i in range(1, steps + 1):
        t = i / steps
        u = 1 - t
        out.append(
            (
                u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0],
                u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1],
            )
        )
    return out


def _hill(start: Point, curves: Sequence[tuple[Point, Point, Point]]) -> list[Point]:
    points = [start]
    here = start
    for c1, c2, end in curves:
        points += _bezier(here, c1, c2, end)
        here = end
    return points + [(32, 32), (0, 32)]


def _mark(size: int) -> Image.Image:
    """The Sandcorp mark (og-default.svg: 32x32 ink tile, two hills), supersampled 4x."""
    scale = size * 4 / 32

    def scaled(points: list[Point]) -> list[Point]:
        return [(x * scale, y * scale) for x, y in points]

    big = Image.new("RGB", (size * 4, size * 4), INK)
    draw = ImageDraw.Draw(big)
    draw.polygon(
        scaled(_hill((0, 21), [((5, 13), (10, 12), (15, 16)), ((20, 20), (25, 19), (32, 12))])),
        fill=GOLD_DARK,
    )
    draw.polygon(
        scaled(_hill((0, 26), [((6, 20), (11, 20), (16, 24)), ((21, 28), (26, 26), (32, 21))])),
        fill=GOLD,
    )
    mask = Image.new("L", big.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, big.size[0] - 1, big.size[1] - 1), 2 * scale, 255)
    tile = big.resize((size, size), Image.Resampling.LANCZOS)
    tile.putalpha(mask.resize((size, size), Image.Resampling.LANCZOS))
    return tile


_DASHES = frozenset("—–-·:|/")


def _pieces(text: str) -> list[tuple[str, str]]:
    """(separator, piece) pairs: a line may break at a space or before an opening parenthesis.
    A lone dash-like word stays glued to the word before it, never heading a line."""
    out: list[tuple[str, str]] = []
    for word in text.split():
        if out and all(ch in _DASHES for ch in word):
            sep, prev = out[-1]
            out[-1] = (sep, f"{prev} {word}")
            continue
        parts = re.split(r"(?=\()", word)
        for i, part in enumerate(p for p in parts if p):
            out.append((" " if i == 0 else "", part))
    return out


def _wrap(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, width: int, max_lines: int
) -> list[str]:
    """Break at spaces and before `(`, never inside a word; only a word wider than the line is
    cut between characters. The last line ends in an ellipsis when the text does not fit."""
    lines: list[str] = []
    current = ""
    overflow = False

    def fits(s: str) -> bool:
        return draw.textlength(s, font=font) <= width

    for sep, piece in _pieces(text):
        trial = f"{current}{sep}{piece}" if current else piece
        if fits(trial):
            current = trial
            continue
        if current:
            lines.append(current)
            current = ""
        word = piece
        while not fits(word):
            cut = len(word)
            while cut > 1 and not fits(word[:cut]):
                cut -= 1
            lines.append(word[:cut])
            word = word[cut:]
        current = word
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        overflow = True
        lines = lines[:max_lines]
    if overflow:
        last = lines[-1]
        while last and not fits(last + "…"):
            last = last[:-1]
        lines[-1] = last.rstrip() + "…"
    return lines


def compose(title: str, cover_bytes: bytes) -> bytes:
    """Brand frame on the left (mark, title, domain), the cover contained on the right."""
    card = Image.new("RGB", (WIDTH, HEIGHT), WHITE)
    draw = ImageDraw.Draw(card)
    draw.rectangle((0, 606, WIDTH, HEIGHT), fill=NAVY)
    card.paste(_mark(96), (72, 64), _mark(96))

    text_width = 420
    font = _font("Bold", 54)
    lines = _wrap(draw, title.strip() or "Sandcorp", font, text_width, 4)
    y = 200
    for line in lines:
        draw.text((72, y), line, font=font, fill=INK)
        y += 70
    draw.text((72, 540), "sandcorp.co.kr", font=_font("SemiBold", 28), fill=NAVY)

    box = (556, 56, 1128, 550)  # x0, y0, x1, y1 of the cover area
    with Image.open(io.BytesIO(cover_bytes)) as opened:
        opened.draft("RGB", (2 * (box[2] - box[0]), 2 * (box[3] - box[1])))
        image = opened.convert("RGBA")
    flat = Image.new("RGBA", image.size, WHITE + (255,))
    flat.alpha_composite(image)
    fitted = flat.convert("RGB")
    fitted.thumbnail((box[2] - box[0] - 2, box[3] - box[1] - 2), Image.Resampling.LANCZOS)
    x = box[0] + (box[2] - box[0] - fitted.width) // 2
    top = box[1] + (box[3] - box[1] - fitted.height) // 2
    card.paste(fitted, (x, top))
    draw.rectangle((x - 1, top - 1, x + fitted.width, top + fitted.height), outline=LINE)

    return _encode(card)


def _encode(card: Image.Image) -> bytes:
    out = io.BytesIO()
    card.save(out, "PNG", optimize=True)
    if out.tell() > MAX_BYTES:  # a photographic cover: fewer colours keeps previews light
        out = io.BytesIO()
        card.quantize(256, dither=Image.Dither.FLOYDSTEINBERG).save(out, "PNG", optimize=True)
    return out.getvalue()
