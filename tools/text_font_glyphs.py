"""The Ukrainian letters for a game's own text fonts, drawn from glyphs the font already has.

Some titles draw their big captions with bitmap fonts of their own instead of the system
font. The plaza's MEET_edge and the eight LA4 fonts of its update carry the Russian
Cyrillic only, so a `real` build (tools/variant.py), whose text keeps the real letters,
loses them there: "Вітаємо!" comes out as "В та мо!".

Every one of these fonts is a European font too, so the shapes are already in it:

    і І ї Ї    the cells of Latin i I ï Ï - the same letters, drawn once more
    є Є        the cells of э Э, mirrored - є is a reversed э in every Cyrillic typeface
    ґ Ґ        the cells of г Г - no upturn: an outlined bitmap gives nothing to draw it
               from, and the default build prints these two as г Г anyway

Mirroring keeps the advance and moves the ink: the glyph's columns run from 0 to its
width (see bcfnt.Sheets.cell_origin), so they are reversed in place and the left bearing
becomes what was on the right, char width - left - glyph width.

Usage:
    python3 tools/text_font_glyphs.py FONT [OUT]   # .lz77 is LZ11, as the plaza ships it
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import bcfnt  # noqa: E402
import lz11  # noqa: E402

# Ukrainian letter -> (the glyph it is drawn from, mirrored)
DONORS: dict[str, tuple[str, bool]] = {
    "і": ("i", False),
    "І": ("I", False),
    "ї": ("ï", False),
    "Ї": ("Ï", False),
    "є": ("э", True),
    "Є": ("Э", True),
    "ґ": ("г", False),
    "Ґ": ("Г", False),
}


def mirrored(rows: list[list], glyph_width: int) -> list[list]:
    return [row[:glyph_width][::-1] + row[glyph_width:] for row in rows]


def patch(font_data: bytes) -> tuple[bytes, list[str]]:
    """The font with the letters it lacks added; a font that has them all comes back as is."""
    font = bcfnt.parse(font_data)
    glyphs = {}
    for letter, (donor, mirror) in DONORS.items():
        if ord(letter) in font.cmap:
            continue
        if ord(donor) not in font.cmap:
            raise SystemExit(f"text font has neither {letter} nor its donor {donor}")
        rows = bcfnt.glyph_rows(font, ord(donor))
        left, glyph_width, char_width = font.widths[font.cmap[ord(donor)]]
        if mirror:
            rows = mirrored(rows, glyph_width)
            left = char_width - left - glyph_width
        glyphs[ord(letter)] = (rows, left, glyph_width, char_width)
    if not glyphs:
        return font_data, []
    bcfnt.add_glyphs(font, glyphs, grow=True)
    return bcfnt.build(font), [chr(code) for code in sorted(glyphs)]


def patch_file(data: bytes, compressed: bool) -> tuple[bytes, list[str]]:
    plain = lz11.decompress(data) if compressed else data
    out, added = patch(plain)
    if not added:
        return data, []
    return (lz11.compress(out) if compressed else out), added


def main() -> None:
    if len(sys.argv) not in (2, 3):
        raise SystemExit(__doc__)
    src = Path(sys.argv[1])
    out, added = patch_file(src.read_bytes(), src.suffix == ".lz77")
    print(f"{src.name}: + {' '.join(added) or 'nothing'}")
    if len(sys.argv) == 3:
        Path(sys.argv[2]).write_bytes(out)


if __name__ == "__main__":
    main()
