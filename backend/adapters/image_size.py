"""Image dimensions from the first bytes of a file (#123): PNG, JPEG, WebP and GIF.

No decoding and no Pillow: only the header fields that hold the size. Anything unknown,
truncated or malformed gives None, never an exception.
"""


def _le16(data: bytes, at: int) -> int:
    return data[at] | data[at + 1] << 8


def _be16(data: bytes, at: int) -> int:
    return data[at] << 8 | data[at + 1]


def _png(data: bytes) -> tuple[int, int] | None:
    if len(data) < 24 or data[12:16] != b"IHDR":
        return None
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def _gif(data: bytes) -> tuple[int, int] | None:
    if len(data) < 10:
        return None
    return _le16(data, 6), _le16(data, 8)


def _webp(data: bytes) -> tuple[int, int] | None:
    if len(data) < 30:
        return None
    kind = data[12:16]
    if kind == b"VP8 " and data[23:26] == b"\x9d\x01\x2a":
        return _le16(data, 26) & 0x3FFF, _le16(data, 28) & 0x3FFF
    if kind == b"VP8L" and data[20] == 0x2F:
        width = 1 + (data[21] | (data[22] & 0x3F) << 8)
        height = 1 + (data[22] >> 6 | data[23] << 2 | (data[24] & 0x0F) << 10)
        return width, height
    if kind == b"VP8X":
        width = 1 + int.from_bytes(data[24:27], "little")
        height = 1 + int.from_bytes(data[27:30], "little")
        return width, height
    return None


_NO_SIZE_MARKERS = {0xC4, 0xC8, 0xCC}  # inside the SOF range but not frame headers


def _jpeg(data: bytes) -> tuple[int, int] | None:
    at = 2
    while at + 4 <= len(data):
        if data[at] != 0xFF:
            return None
        marker = data[at + 1]
        if marker == 0xFF:  # fill byte
            at += 1
            continue
        if 0xC0 <= marker <= 0xCF and marker not in _NO_SIZE_MARKERS:
            if at + 9 > len(data):
                return None
            return _be16(data, at + 7), _be16(data, at + 5)
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:  # no length
            at += 2
            continue
        at += 2 + _be16(data, at + 2)
    return None


def image_size(data: bytes) -> tuple[int, int] | None:
    """(width, height) in pixels, or None when the format is unknown or the header is cut off."""
    found: tuple[int, int] | None = None
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        found = _png(data)
    elif data.startswith((b"GIF87a", b"GIF89a")):
        found = _gif(data)
    elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        found = _webp(data)
    elif data.startswith(b"\xff\xd8"):
        found = _jpeg(data)
    return found if found and found[0] > 0 and found[1] > 0 else None
