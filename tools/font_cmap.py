"""Extract the code point list and glyph widths from a BCFNT (3DS system font).

Usage:
    python3 tools/font_cmap.py work/0004009B00014002/cbf_std.bcfnt.lz assets/font_charset.txt
"""

from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lz11 import decompress  # noqa: E402

UA_CHECK = "АаБбВвГгҐґДдЕеЄєЖжЗзИиІіЇїЙйКкЛлМмНнОоПпРрСсТтУуФфХхЦцЧчШшЩщЬьЮюЯя"


def parse_bcfnt(data: bytes) -> tuple[dict[int, int], dict[int, int]]:
    """-> ({code point: glyph index}, {glyph index: advance width in pixels})"""
    if data[:4] != b"CFNT":
        raise ValueError(f"not a BCFNT file: {data[:4]!r}")

    header_size = struct.unpack_from("<H", data, 6)[0]
    num_blocks = struct.unpack_from("<I", data, 0x10)[0]

    codes: dict[int, int] = {}
    widths: dict[int, int] = {}
    offset = header_size
    for _ in range(num_blocks):
        magic = data[offset : offset + 4]
        section_size = struct.unpack_from("<I", data, offset + 4)[0]
        if magic == b"CMAP":
            codes.update(_parse_cmap(data, offset + 8))
        elif magic == b"CWDH":
            widths.update(_parse_cwdh(data, offset + 8))
        if section_size <= 0:
            break
        offset += section_size

    return codes, widths


def _parse_cwdh(data: bytes, pos: int) -> dict[int, int]:
    """CWDH: startIndex u16, endIndex u16, next u32, then (left i8, glyphWidth u8, charWidth u8)."""
    start, end = struct.unpack_from("<HH", data, pos)
    body = pos + 8
    return {start + i: data[body + i * 3 + 2] for i in range(end - start + 1)}


def _parse_cmap(data: bytes, pos: int) -> dict[int, int]:
    """CMAP: code_begin u16, code_end u16, method u16, pad u16, next u32, then the mapping data."""
    code_begin, code_end, method = struct.unpack_from("<HHH", data, pos)
    body = pos + 12
    codes: dict[int, int] = {}

    if method == 0:  # direct
        index_offset = struct.unpack_from("<H", data, body)[0]
        if index_offset != 0xFFFF:
            for i, code in enumerate(range(code_begin, code_end + 1)):
                codes[code] = index_offset + i
    elif method == 1:  # table
        for i in range(code_end - code_begin + 1):
            index = struct.unpack_from("<H", data, body + i * 2)[0]
            if index != 0xFFFF:
                codes[code_begin + i] = index
    elif method == 2:  # scan
        count = struct.unpack_from("<H", data, body)[0]
        for i in range(count):
            code, index = struct.unpack_from("<HH", data, body + 2 + i * 4)
            if index != 0xFFFF:
                codes[code] = index
    else:
        raise ValueError(f"unknown CMAP mapping method: {method}")

    return codes


def main() -> None:
    src = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else None

    raw = src.read_bytes()
    data = decompress(raw) if src.suffix == ".lz" else raw
    code_map, glyph_widths = parse_bcfnt(data)
    codes = set(code_map)

    print(f"{src.name}: {len(codes)} code points, {len(glyph_widths)} glyph widths")

    missing = [c for c in UA_CHECK if ord(c) not in codes]
    print("\nUkrainian alphabet:")
    if missing:
        print(f"  MISSING ({len(missing)}): " + " ".join(f"{c} U+{ord(c):04X}" for c in missing))
    else:
        print("  fully present")

    extras = {
        "quotes": "«»",
        "em dash": "—",
        "ellipsis": "…",
        "apostrophes": "ʼ'",
        "latin i I": "iI",
        "ï Ï": "ïÏ",
        "greek epsilon": "εΕ",
    }
    print("\nExtra characters:")
    for label, chars in extras.items():
        state = {c: ("+" if ord(c) in codes else "−") for c in chars}
        print(f"  {label}: " + " ".join(f"{c}{v}" for c, v in state.items()))

    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"U+{c:04X}\t{chr(c) if c >= 0x20 else ''}" for c in sorted(codes)]
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"\n-> {out} ({len(lines)} lines)")

        widths = {c: glyph_widths[i] for c, i in code_map.items() if i in glyph_widths}
        widths_file = out.parent / "font_widths.json"
        widths_file.write_text(
            json.dumps({f"{c:04X}": w for c, w in sorted(widths.items())}, indent=0),
            encoding="utf-8",
        )
        print(f"-> {widths_file} ({len(widths)} widths)")


if __name__ == "__main__":
    main()
