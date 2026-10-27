"""Resolve the script and stylesheet tags the HTML shell needs from Vite."""

import json
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

from django.conf import settings

# Font files the first screen of nearly every public page uses (#133): the Latin + common Hangul
# Pretendard subsets (the 92 dynamic subsets are loaded by unicode-range, so most are not needed
# up front) and JetBrains Mono's Latin face for the mono labels. Matched by file name in the Vite
# manifest, so the hashed build path is resolved at render time.
PRELOAD_FONTS = (
    "PretendardVariable.subset.91.woff2",
    "PretendardVariable.subset.90.woff2",
    "PretendardVariable.subset.89.woff2",
    "PretendardVariable.subset.88.woff2",
    "PretendardVariable.subset.86.woff2",
    "PretendardVariable.subset.81.woff2",
    "jetbrains-mono-latin-wght-normal.woff2",
)


@dataclass(frozen=True)
class Assets:
    scripts: list[str] = field(default_factory=list)
    fonts: list[str] = field(default_factory=list)
    styles: list[str] = field(default_factory=list)
    dev_server: str = ""


@cache
def _read_manifest(path: Path) -> dict[str, dict[str, object]]:
    with path.open(encoding="utf-8") as fh:
        data: dict[str, dict[str, object]] = json.load(fh)
    return data


def entry_assets() -> Assets:
    if settings.VITE_DEV_SERVER_URL:
        base = settings.VITE_DEV_SERVER_URL
        return Assets(
            scripts=[f"{base}/@vite/client", f"{base}/{settings.VITE_ENTRY}"],
            dev_server=base,
        )
    manifest = _read_manifest(Path(settings.VITE_MANIFEST_PATH))
    chunk = manifest[settings.VITE_ENTRY]
    static = settings.STATIC_URL
    css = chunk.get("css", [])
    fonts = [
        f"{static}{manifest[key]['file']}"
        for name in PRELOAD_FONTS
        for key in manifest
        if key.rsplit("/", 1)[-1] == name
    ]
    return Assets(
        scripts=[f"{static}{chunk['file']}"],
        fonts=fonts,
        styles=[f"{static}{name}" for name in css] if isinstance(css, list) else [],
    )
