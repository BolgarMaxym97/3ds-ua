"""Split and rebuild a CBMD banner (ExeFS:/banner) without touching what we don't edit.

Layout, as HOME Menu reads it (see docs/banner-ua.md for the code that does the reading):

    0x00  'CBMD'
    0x04  version
    0x08  offset -> common CGFX          slot 0
    0x0C  offset -> language CGFX        slot 1, and so on: offset = 8 + slot*4
    0x84  offset -> CWAV                 the sound the banner plays
    0x88  first block

The slot numbering is HOME Menu's own, not the CFG language enum: for a EUR console
slot 1 is EUR_EN and slot 8 is EUR_RU. A zero offset means "no such language" and the
common CGFX is drawn instead - which is why System Settings, whose common block already
carries the English wording, has no slot 1 at all.

Blocks are LZ11-compressed CGFX, packed back to back with no alignment, so rebuilding is
a matter of writing them out in order and recomputing the offsets.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lz11 import compress, decompress  # noqa: E402

MAGIC = b"CBMD"
HEADER_SIZE = 0x88
SLOT_COUNT = 18          # slot 0 (common) plus 17 languages
CWAV_OFFSET = 0x84
CWAV_ALIGNMENT = 32   # where Nintendo puts it, and where its parser needs it

# Slot numbers worth naming, from the jump table at .text 0x145560 of HOME Menu EUR v29.
EUR_EN = 1
EUR_RU = 8


class Banner:
    """A parsed banner: the header words, the CGFX blocks, and the CWAV tail."""

    def __init__(self, version: int, blocks: dict[int, bytes], cwav: bytes) -> None:
        self.version = version
        self.blocks = blocks          # slot -> LZ11-compressed CGFX
        self.cwav = cwav

    def slots(self) -> list[int]:
        return sorted(self.blocks)

    def cgfx(self, slot: int) -> bytes:
        """The decompressed CGFX of one slot."""
        return decompress(self.blocks[slot])

    def set_cgfx(self, slot: int, data: bytes) -> None:
        """Replace one slot's CGFX. The block is recompressed; every other block is kept
        byte for byte, so a rebuild without this call reproduces the input exactly."""
        if data[:4] != b"CGFX":
            raise ValueError(f"slot {slot}: not a CGFX ({data[:4]!r})")
        self.blocks[slot] = compress(data)


def parse(data: bytes) -> Banner:
    if data[:4] != MAGIC:
        raise ValueError(f"not a CBMD: {data[:4]!r}")
    version = struct.unpack_from("<I", data, 4)[0]
    offsets = {
        slot: struct.unpack_from("<I", data, 8 + slot * 4)[0] for slot in range(SLOT_COUNT)
    }
    cwav_at = struct.unpack_from("<I", data, CWAV_OFFSET)[0]

    bounds = sorted({off for off in offsets.values() if off} | {cwav_at or len(data)})
    blocks: dict[int, bytes] = {}
    for slot, off in offsets.items():
        if not off:
            continue
        end = min(b for b in bounds if b > off)
        # The block that runs up to the CWAV keeps whatever alignment padding sits in front
        # of it - the slice cannot tell the two apart, and trimming zeros would eat real
        # stream bytes. It does not accumulate: build() pads to the boundary, so a block
        # that already ends on one gets nothing added.
        block = data[off:end]
        if block[0] != 0x11:
            raise ValueError(f"slot {slot}: expected LZ11, got {block[:4].hex()}")
        blocks[slot] = block
    return Banner(version, blocks, data[cwav_at:] if cwav_at else b"")


def build(banner: Banner) -> bytes:
    header = bytearray(HEADER_SIZE)
    header[0:4] = MAGIC
    struct.pack_into("<I", header, 4, banner.version)

    body = bytearray()
    for slot in banner.slots():
        struct.pack_into("<I", header, 8 + slot * 4, HEADER_SIZE + len(body))
        body += banner.blocks[slot]
    if banner.cwav:
        # The CGFX blocks sit wherever they land - Nintendo's own are on odd offsets, and
        # they are only ever read a byte at a time by the LZ11 decompressor. The CWAV is
        # not: whoever parses the banner sound reads words out of it in place, so a start
        # that is not 32-byte aligned earns an alignment data abort the moment the banner
        # is drawn. Nintendo aligns it; so do we.
        body += b"\0" * (-(HEADER_SIZE + len(body)) % CWAV_ALIGNMENT)
        struct.pack_into("<I", header, CWAV_OFFSET, HEADER_SIZE + len(body))
        body += banner.cwav
    return bytes(header) + bytes(body)


def _report(path: Path) -> None:
    banner = parse(path.read_bytes())
    print(f"{path}: version {banner.version}, {len(banner.blocks)} blocks")
    for slot in banner.slots():
        raw = banner.cgfx(slot)
        name = {0: "common", EUR_EN: "EUR_EN", EUR_RU: "EUR_RU"}.get(slot, "")
        print(
            f"  slot {slot:2d} {name:7s} {len(banner.blocks[slot]):7d} packed"
            f" -> {len(raw):7d} raw  {raw[:4]!r}"
        )
    print(f"  cwav {len(banner.cwav)} bytes")
    rebuilt = build(banner)
    print("  round-trip:", "byte for byte" if rebuilt == path.read_bytes() else "DIFFERS")


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        _report(Path(arg))
