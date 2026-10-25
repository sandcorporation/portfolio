"""Header parsing for og:image:width/height (#123): fixed small byte strings per format."""

import struct

import pytest

from adapters.image_size import image_size

PNG = (
    b"\x89PNG\r\n\x1a\n"
    + struct.pack(">I", 13)
    + b"IHDR"
    + struct.pack(">II", 640, 480)
    + b"\x08\x06"
)
GIF = b"GIF89a" + struct.pack("<HH", 320, 200) + b"\x00\x00\x00"
JPEG = (
    b"\xff\xd8"
    + b"\xff\xe1"
    + struct.pack(">H", 8)
    + b"Exif\x00\x00"  # an APP1 segment to skip
    + b"\xff\xc4"
    + struct.pack(">H", 4)
    + b"\x00\x00"  # DHT looks like SOF but is not
    + b"\xff\xc0"
    + struct.pack(">HBHH", 17, 8, 600, 800)
    + b"\x03\x01\x22\x00"
)
WEBP_LOSSY = b"RIFF\x00\x00\x00\x00WEBPVP8 \x00\x00\x00\x00\x00\x00\x00\x9d\x01\x2a" + struct.pack(
    "<HH", 1200, 630
)
WEBP_X = (
    b"RIFF\x00\x00\x00\x00WEBPVP8X\x0a\x00\x00\x00\x00\x00\x00\x00"
    + (1920 - 1).to_bytes(3, "little")
    + (1080 - 1).to_bytes(3, "little")
)


def _lossless(width: int, height: int) -> bytes:
    bits = (width - 1) | (height - 1) << 14
    return (
        b"RIFF\x00\x00\x00\x00WEBPVP8L\x00\x00\x00\x00\x2f" + bits.to_bytes(4, "little") + bytes(8)
    )


@pytest.mark.parametrize(
    ("data", "size"),
    [
        (PNG, (640, 480)),
        (GIF, (320, 200)),
        (JPEG, (800, 600)),
        (WEBP_LOSSY, (1200, 630)),
        (WEBP_X, (1920, 1080)),
        (_lossless(1000, 500), (1000, 500)),
    ],
)
def test_each_format_gives_width_and_height(data: bytes, size: tuple[int, int]) -> None:
    assert image_size(data) == size


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"not an image",
        PNG[:20],
        JPEG[:22],
        WEBP_LOSSY[:20],
        b"\xff\xd8\xff",
        b"BM" + bytes(40),
    ],
)
def test_unknown_or_cut_off_headers_give_none(data: bytes) -> None:
    assert image_size(data) is None
