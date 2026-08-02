"""Render the HUD-font glyphs Ukrainian needs and write them to assets/hud_glyphs.json.

Development-time tool, not part of `make build`: it needs Pillow, the build does not. The
build reads the JSON this writes.

The HUD font is a 15x17-cell bitmap subset carrying only what the console's clock line
draws, and its Cyrillic stops at the Russian weekday abbreviations - `В П С Ч б н р с т`,
enough for `Вс Пн Вт Ср Чт Пт Сб` and nothing more. Ukrainian `Нд` needs `Н` and `д`,
which is why Sunday shows as empty parentheses. Both letters are in `nintendo_NTLG-DB_001`,
the outline font these bitmaps were rasterised from, and a copy of it ships inside the
browser's romfs - so the new cells come from the same typeface as the old ones.

Nothing here is guessed. Every parameter is fitted against the glyphs the HUD font already
has and the fit is reported:

    pixel size, stroke, gamma  calibrate() tries each combination and keeps whichever
                               redraws the nine existing Cyrillic glyphs most closely
    vertical placement         the same fit, so a new glyph sits on their baseline
    advance (charWidth)        round(outline advance * scale), scale fitted over all 66
                               glyphs of the font - it reproduces 65 of them exactly
    bearing (left)             floor of the unhinted left side bearing, which reproduces
                               61 of 66

Usage:
    python3 tools/hud_glyphs.py                 # write the asset
    python3 tools/hud_glyphs.py --report        # calibration fit + ASCII preview
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
import bcfnt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

# The outline font, and one of the nine identical copies of the bitmap font to match.
TTF = ROOT / "work" / "0004003000009D02" / "romfs" / "font" / "nintendo.ttf"
REFERENCE_FONT = ROOT / "work" / "0004003000009802" / "romfs" / "font" / "Hud_JP.bcfnt"
ASSET = ROOT / "assets" / "hud_glyphs.json"

WANTED = [0x041D, 0x0434]  # Н д
# Every Cyrillic glyph already in the font: same script and weight as what we are adding.
REFERENCES = [0x0412, 0x041F, 0x0421, 0x0427, 0x0431, 0x043D, 0x0440, 0x0441, 0x0442]

SIZES = range(12, 19)
STROKES = (0, 1, 2)
GAMMAS = (0.45, 0.55, 0.65, 0.8, 1.0)
OFFSETS = range(-4, 5)

# Room around the cell while rasterising, so nothing is clipped before it is positioned.
MARGIN = 8
RAMP = " .:-=+*#%@"


def rasterise(font: ImageFont.FreeTypeFont, char: str, cell: tuple[int, int], dy: int, stroke: int) -> list[list[int]]:
    """Grey levels 0-255 for one cell, ink flush against the left edge.

    Cells store their glyph left-aligned - the side bearing lives in CWDH, not in the
    pixels - so the horizontal position is not a free parameter to fit.
    """
    width, height = cell
    canvas = Image.new("L", (width + 2 * MARGIN, height + 2 * MARGIN), 0)
    draw = ImageDraw.Draw(canvas)
    draw.text((MARGIN, MARGIN + dy), char, font=font, fill=255, stroke_width=stroke, stroke_fill=255)
    box = canvas.getbbox()
    if box is None:
        raise SystemExit(f"{char!r} rendered as nothing at all")
    pixels = canvas.load()
    return [
        [pixels[box[0] + x, MARGIN + y] if box[0] + x < canvas.width else 0 for x in range(width)]
        for y in range(height)
    ]


def quantise(grey: list[list[int]], gamma: float) -> list[list[int]]:
    """Grey levels to the 4-bit alpha a LA4 cell stores."""
    return [[min(15, round(15 * (value / 255) ** gamma)) for value in row] for row in grey]


def difference(a: list[list[int]], b: list[list[int]]) -> int:
    return sum(abs(p - q) for row_a, row_b in zip(a, b) for p, q in zip(row_a, row_b))


def calibrate(source: bcfnt.Font) -> dict:
    """Fit size, stroke, vertical offset and gamma against the font's own glyphs.

    The stroke matters: this is a demi-bold cut rasterised heavier still, and without a
    one-pixel pen the stems come out half the weight of Nintendo's.
    """
    cell = bcfnt.cell_size(source)
    targets = {code: bcfnt.glyph_rows(source, code) for code in REFERENCES}

    best: tuple[int, dict] | None = None
    for size in SIZES:
        font = ImageFont.truetype(str(TTF), size)
        for stroke in STROKES:
            greys = {
                (code, dy): rasterise(font, chr(code), cell, dy, stroke)
                for code in REFERENCES
                for dy in OFFSETS
            }
            for dy in OFFSETS:
                for gamma in GAMMAS:
                    per_glyph = {
                        code: difference(quantise(greys[code, dy], gamma), targets[code])
                        for code in REFERENCES
                    }
                    total = sum(per_glyph.values())
                    if best is None or total < best[0]:
                        best = (total, {
                            "pixel_size": size,
                            "stroke": stroke,
                            "y_offset": dy,
                            "gamma": gamma,
                            "error": total,
                            "per_glyph": {f"{code:04X}": value for code, value in per_glyph.items()},
                        })
    return best[1]


def advance_scale(source: bcfnt.Font, font: ImageFont.FreeTypeFont) -> tuple[float, int]:
    """Outline advance -> stored charWidth, fitted over every glyph in the font."""
    pairs = [
        (font.getlength(chr(code)), source.widths[index][2])
        for code, index in source.cmap.items()
        if code > 0x20
    ]
    candidates = [1 + i * 0.005 for i in range(0, 21)]
    scored = [
        (sum(abs(round(advance * scale) - stored) for advance, stored in pairs), scale)
        for scale in candidates
    ]
    error, scale = min(scored)
    exact = sum(1 for advance, stored in pairs if round(advance * scale) == stored)
    del error
    return scale, exact


def side_bearing(font_path: Path, char: str, size: int, oversample: int = 100) -> float:
    """Left side bearing in pixels at `size`, measured off an unhinted rasterisation.

    Read at the target size the hinter has already snapped it to whole pixels, which loses
    exactly the distinction - flat-sided letters carry a bearing of one, round ones of
    none - that decides the value CWDH stores.
    """
    big = ImageFont.truetype(str(font_path), size * oversample)
    pen = 2 * size * oversample
    canvas = Image.new("L", (pen * 2, 3 * size * oversample), 0)
    ImageDraw.Draw(canvas).text((pen, size * oversample), char, font=big, fill=255)
    box = canvas.getbbox()
    if box is None:
        raise SystemExit(f"{char!r} rendered as nothing at all")
    return (box[0] - pen) / oversample


def bearing_fit(source: bcfnt.Font, size: int) -> int:
    """How many of the font's own glyphs floor(side bearing) reproduces."""
    return sum(
        1
        for code, index in source.cmap.items()
        if code > 0x20 and math.floor(side_bearing(TTF, chr(code), size)) == source.widths[index][0]
    )


def generate(check_bearings: bool = False) -> dict:
    source = bcfnt.parse(REFERENCE_FONT.read_bytes())
    cell = bcfnt.cell_size(source)
    fit = calibrate(source)
    font = ImageFont.truetype(str(TTF), fit["pixel_size"])
    scale, exact = advance_scale(source, font)

    glyphs = {}
    for code in WANTED:
        char = chr(code)
        rows = quantise(rasterise(font, char, cell, fit["y_offset"], fit["stroke"]), fit["gamma"])
        inked = [x for row in rows for x, value in enumerate(row) if value]
        glyphs[f"{code:04X}"] = {
            "char": char,
            "left": math.floor(side_bearing(TTF, char, fit["pixel_size"])),
            "glyph_width": max(inked) + 1,
            "char_width": round(font.getlength(char) * scale),
            "rows": ["".join(f"{value:X}" for value in row) for row in rows],
        }

    source_info = {
        "font": "nintendo_NTLG-DB_001 (0004003000009D02 romfs/font/nintendo.ttf)",
        "cell": list(cell),
        "advance_scale": round(scale, 3),
        "advance_exact": f"{exact}/{len(source.cmap) - 1}",
        **fit,
    }
    if check_bearings:
        source_info["bearing_exact"] = f"{bearing_fit(source, fit['pixel_size'])}/{len(source.cmap) - 1}"

    return {
        "_comment": (
            "Glyphs added to the HUD font (Hud.bcfnt / Hud_JP.bcfnt) so the Ukrainian "
            "weekday Нд has letters to draw with. Written by tools/hud_glyphs.py; `rows` "
            "is one hex alpha nibble per pixel, ink flush left as the cells store it."
        ),
        "_source": source_info,
        "glyphs": glyphs,
    }


def preview(rows: list[str]) -> str:
    return "\n".join("|" + "".join(RAMP[int(c, 16) * 9 // 15] for c in row) + "|" for row in rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", action="store_true", help="print the calibration fit and a preview")
    args = parser.parse_args()

    asset = generate(check_bearings=args.report)
    ASSET.write_text(json.dumps(asset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"-> {ASSET.relative_to(ROOT)} ({len(asset['glyphs'])} glyphs)")

    if not args.report:
        return

    info = asset["_source"]
    print(
        f"\nfit: {info['pixel_size']}px stroke={info['stroke']} dy={info['y_offset']} "
        f"gamma={info['gamma']}, error {info['error']} over {len(REFERENCES)} reference glyphs"
    )
    print(f"     advance scale {info['advance_scale']} exact for {info['advance_exact']}, "
          f"bearing exact for {info['bearing_exact']}")

    source = bcfnt.parse(REFERENCE_FONT.read_bytes())
    font = ImageFont.truetype(str(TTF), info["pixel_size"])
    for code in REFERENCES[:3]:
        rendered = quantise(
            rasterise(font, chr(code), bcfnt.cell_size(source), info["y_offset"], info["stroke"]),
            info["gamma"],
        )
        original = bcfnt.glyph_rows(source, code)
        print(f"\nU+{code:04X} {chr(code)}  rendered | original   (error {info['per_glyph'][f'{code:04X}']})")
        for a, b in zip(rendered, original):
            left = "".join(RAMP[v * 9 // 15] for v in a)
            right = "".join(RAMP[v * 9 // 15] for v in b)
            print(f"|{left}|  |{right}|")

    for code, glyph in asset["glyphs"].items():
        print(f"\nU+{code} {glyph['char']}  left={glyph['left']} glyph_width={glyph['glyph_width']} "
              f"char_width={glyph['char_width']}")
        print(preview(glyph["rows"]))


if __name__ == "__main__":
    main()
