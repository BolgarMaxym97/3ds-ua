"""Read and patch the title strings of an SMDH.

A few titles carry a full SMDH inside their romfs - Mii Maker's icn/EU_appEdit.icn,
Nintendo Zone's saveicon_EU.icn - and unlike the SMDH in ExeFS, LayeredFS can replace
those. The system renders their text with the system font, so the same homoglyph rules as
everywhere else apply.

Layout (see 3dbrew "SMDH"): 8-byte header, then 16 application-title structures of 0x200
bytes each, one per language, in a fixed order. Each holds three UTF-16LE strings:

    +0x000  short description   0x40 chars (0x80 bytes)
    +0x080  long description    0x80 chars (0x100 bytes)
    +0x180  publisher           0x40 chars (0x80 bytes)

Everything after the titles - the icon bitmaps included - is left untouched, which is why
the original file has to be the starting point: the bitmaps cannot be regenerated.
"""

from __future__ import annotations

MAGIC = b"SMDH"
TITLES_OFFSET = 0x08
TITLE_SIZE = 0x200
SHORT_SIZE = 0x80
LONG_SIZE = 0x100
PUBLISHER_SIZE = 0x80

# Language order of the application-title array. The last four slots are reserved and
# unused, but they are still present in the file.
LANGUAGES = [
    "Japanese",
    "English",
    "French",
    "German",
    "Italian",
    "Spanish",
    "SimplifiedChinese",
    "Korean",
    "Dutch",
    "Portuguese",
    "Russian",
    "TraditionalChinese",
]

# Our language-folder names -> index in the array above.
LANG_INDEX = {
    "EU_English": 1,
    "EU_French": 2,
    "EU_German": 3,
    "EU_Italian": 4,
    "EU_Spanish": 5,
    "EU_Dutch": 8,
    "EU_Portuguese": 9,
    "EU_Russian": 10,
    "EU_Russia": 10,
}


def _decode(data: bytes) -> str:
    return data.decode("utf-16-le").split("\0")[0]


def _encode(text: str, size: int) -> bytes:
    encoded = text.encode("utf-16-le")
    if len(encoded) > size - 2:
        raise ValueError(f"{text!r} is {len(encoded)} bytes, the field holds {size - 2}")
    return encoded.ljust(size, b"\0")


def read(data: bytes, index: int) -> dict[str, str]:
    """The three strings of one language slot."""
    if data[: len(MAGIC)] != MAGIC:
        raise ValueError(f"not an SMDH: magic is {data[:4]!r}")
    base = TITLES_OFFSET + index * TITLE_SIZE
    return {
        "short": _decode(data[base : base + SHORT_SIZE]),
        "long": _decode(data[base + SHORT_SIZE : base + SHORT_SIZE + LONG_SIZE]),
        "publisher": _decode(data[base + SHORT_SIZE + LONG_SIZE : base + TITLE_SIZE]),
    }


def patch(data: bytes, index: int, short: str, long: str) -> bytes:
    """The same SMDH with one language slot's short and long description replaced."""
    if data[: len(MAGIC)] != MAGIC:
        raise ValueError(f"not an SMDH: magic is {data[:4]!r}")
    base = TITLES_OFFSET + index * TITLE_SIZE
    out = bytearray(data)
    out[base : base + SHORT_SIZE] = _encode(short, SHORT_SIZE)
    out[base + SHORT_SIZE : base + SHORT_SIZE + LONG_SIZE] = _encode(long, LONG_SIZE)
    return bytes(out)
