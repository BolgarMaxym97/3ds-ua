"""LZ10 (`0x10`) decompressor and compressor — the codec inside a BCMA manual.

The manual container is an uncompressed DARC whose members are LZ10-compressed DARCs,
which is one level shallower than the LZ11 used by the message archives (see `lz11.py`).

Header: type byte 0x10, then the decompressed size as u24 little-endian. If that size is 0
an extended u32 size follows, which no manual seen so far uses.

Flag byte, MSB first: 0 = literal byte, 1 = a two-byte back reference
`(len - 3) << 12 | (disp - 1)`, so 3..18 bytes from up to 4096 back.

Usage:
    python3 tools/lz10.py <file>     # decompress, recompress and compare
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

MAGIC = 0x10
MIN_MATCH = 3
MAX_MATCH = 18
MAX_DISP = 0x1000


def decompress(data: bytes) -> bytes:
    if not data or data[0] != MAGIC:
        raise ValueError(f"not LZ10: first byte {data[:1].hex()}")

    size = int.from_bytes(data[1:4], "little")
    pos = 4
    if size == 0:
        size = struct.unpack_from("<I", data, pos)[0]
        pos += 4

    out = bytearray()
    while len(out) < size:
        flags = data[pos]
        pos += 1
        for bit in range(8):
            if len(out) >= size:
                break
            if flags & (0x80 >> bit):
                pair = struct.unpack_from(">H", data, pos)[0]
                pos += 2
                length = (pair >> 12) + MIN_MATCH
                disp = (pair & 0xFFF) + 1
                if disp > len(out):
                    raise ValueError(f"back reference {disp} past the start at {pos}")
                for _ in range(length):
                    out.append(out[-disp])
            else:
                out.append(data[pos])
                pos += 1

    return bytes(out)


def compress(data: bytes) -> bytes:
    """Greedy LZ10. The output is not byte-identical to Nintendo's encoder - only the
    archives being retranslated are recompressed, the rest are copied through untouched."""
    out = bytearray(struct.pack("<I", MAGIC | (len(data) << 8)))
    # A back reference may not start further than MAX_DISP behind, so the index only ever
    # holds positions inside that window - older ones are useless and slow the search down.
    index: dict[bytes, list[int]] = {}
    pos = 0
    while pos < len(data):
        flags_at = len(out)
        out.append(0)
        flags = 0
        for bit in range(8):
            if pos >= len(data):
                break
            length, disp = _find_match(data, pos, index)
            if length >= MIN_MATCH:
                flags |= 0x80 >> bit
                out += struct.pack(">H", (length - MIN_MATCH) << 12 | (disp - 1))
            else:
                length = 1
                out.append(data[pos])
            for _ in range(length):
                _index_add(data, pos, index)
                pos += 1
        out[flags_at] = flags

    return bytes(out)


def _index_add(data: bytes, pos: int, index: dict[bytes, list[int]]) -> None:
    key = data[pos : pos + MIN_MATCH]
    if len(key) == MIN_MATCH:
        index.setdefault(key, []).append(pos)


def _find_match(data: bytes, pos: int, index: dict[bytes, list[int]]) -> tuple[int, int]:
    key = data[pos : pos + MIN_MATCH]
    if len(key) < MIN_MATCH:
        return 0, 0

    limit = min(MAX_MATCH, len(data) - pos)
    best_len, best_disp = 0, 0
    candidates = index.get(key, ())
    # Newest first: a shorter displacement is no worse for the same length, and the scan
    # can stop as soon as the window runs out.
    for start in reversed(candidates):
        disp = pos - start
        if disp > MAX_DISP:
            break
        length = MIN_MATCH
        while length < limit and data[start + length] == data[pos + length]:
            length += 1
        if length > best_len:
            best_len, best_disp = length, disp
            if length == limit:
                break

    return best_len, best_disp


def main() -> None:
    raw = Path(sys.argv[1]).read_bytes()
    plain = decompress(raw)
    packed = compress(plain)
    again = decompress(packed)
    status = "ok" if again == plain else "MISMATCH"
    print(f"{len(raw)} -> {len(plain)} bytes; recompressed {len(packed)} bytes; round-trip {status}")
    if again != plain:
        sys.exit(1)


if __name__ == "__main__":
    main()
