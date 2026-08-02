"""Render the HUD-font glyphs Ukrainian needs and write them to assets/hud_glyphs.json.

Development-time tool, not part of `make build`: it needs Pillow, the build does not. The
build reads the JSON this writes.

The HUD font is a 15x17-cell bitmap subset carrying only what the console's clock line
draws, and its Cyrillic stops at the Russian weekday abbreviations - `В П С Ч б н р с т`,
enough for `Вс Пн Вт Ср Чт Пт Сб` and nothing more. Ukrainian `Нд` needs `Н` and `д`,
which is why Sunday shows as empty parentheses. Both letters are in `nintendo_NTLG-DB_001`,
the outline font these bitmaps were rasterised from, and a copy of it ships inside the
browser's romfs - so the new cells come from the same typeface as the old ones.

The glyphs are white with a one-pixel black outline, stored in the two nibbles of LA4:
alpha is the whole silhouette, outline included, and luminance is the white core inside it.
So each letter is rasterised twice - once with a one-pixel pen for the silhouette, once
without for the core - and the two are fitted against the two channels separately.

Nothing here is guessed. Every parameter is fitted against the glyphs the HUD font already
has and the fit is reported:

    pixel size, pen, gammas     calibrate() tries each combination and keeps whichever
                                redraws the nine existing Cyrillic glyphs most closely,
                                scoring both channels
    vertical placement          the same fit, so a new glyph sits on their baseline
    advance (charWidth)         round(outline advance * scale), scale fitted over all 66
                                glyphs of the font - it reproduces 65 of them exactly
    bearing (left)              floor of the unhinted left side bearing, 61 of 66

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
PENS = (1, 2)  # how far the outline grows past the core, in pixels
GAMMAS = (0.45, 0.55, 0.65, 0.8, 1.0)
OFFSETS = range(-4, 5)

# Room around the cell while rasterising, so nothing is clipped before it is positioned.
MARGIN = 8
RAMP = " .:-=+*#%@"


def rasterise(
    font: ImageFont.FreeTypeFont, char: str, cell: tuple[int, int], dy: int, pen: int
) -> tuple[list[list[int]], list[list[int]]]:
    """(core, silhouette) grey levels 0-255 for one cell, ink flush against the left edge.

    Both channels are cropped at the same column - the silhouette's - so the core keeps its
    one-pixel inset instead of being shoved against the edge on its own.

    Cells store their glyph left-aligned, the side bearing living in CWDH rather than in
    the pixels, so the horizontal position is not a free parameter to fit.
    """
    width, height = cell
    size = (width + 2 * MARGIN, height + 2 * MARGIN)

    def draw(stroke: int) -> Image.Image:
        canvas = Image.new("L", size, 0)
        ImageDraw.Draw(canvas).text(
            (MARGIN, MARGIN + dy), char, font=font, fill=255, stroke_width=stroke, stroke_fill=255
        )
        return canvas

    silhouette = draw(pen)
    core = draw(0)
    box = silhouette.getbbox()
    if box is None:
        raise SystemExit(f"{char!r} rendered as nothing at all")

    def crop(canvas: Image.Image) -> list[list[int]]:
        pixels = canvas.load()
        return [
            [pixels[box[0] + x, MARGIN + y] if box[0] + x < canvas.width else 0 for x in range(width)]
            for y in range(height)
        ]

    return crop(core), crop(silhouette)


def quantise(grey: list[list[int]], gamma: float) -> list[list[int]]:
    """Grey levels to the 4-bit nibble a LA4 cell stores."""
    return [[min(15, round(15 * (value / 255) ** gamma)) for value in row] for row in grey]


def cell_difference(
    core: list[list[int]], silhouette: list[list[int]], target: list[list[tuple[int, int]]]
) -> int:
    return sum(
        abs(l - want_l) + abs(a - want_a)
        for row_l, row_a, row_t in zip(core, silhouette, target)
        for l, a, (want_l, want_a) in zip(row_l, row_a, row_t)
    )


def calibrate(source: bcfnt.Font) -> dict:
    """Fit size, pen, vertical offset and the two gammas against the font's own glyphs."""
    cell = bcfnt.cell_size(source)
    targets = {code: bcfnt.glyph_rows(source, code) for code in REFERENCES}

    best: tuple[int, dict] | None = None
    for size in SIZES:
        font = ImageFont.truetype(str(TTF), size)
        for pen in PENS:
            greys = {
                (code, dy): rasterise(font, chr(code), cell, dy, pen)
                for code in REFERENCES
                for dy in OFFSETS
            }
            for dy in OFFSETS:
                for core_gamma in GAMMAS:
                    for alpha_gamma in GAMMAS:
                        per_glyph = {
                            code: cell_difference(
                                quantise(greys[code, dy][0], core_gamma),
                                quantise(greys[code, dy][1], alpha_gamma),
                                targets[code],
                            )
                            for code in REFERENCES
                        }
                        total = sum(per_glyph.values())
                        if best is None or total < best[0]:
                            best = (total, {
                                "pixel_size": size,
                                "pen": pen,
                                "y_offset": dy,
                                "core_gamma": core_gamma,
                                "alpha_gamma": alpha_gamma,
                                "error": total,
                                "per_glyph": {f"{c:04X}": v for c, v in per_glyph.items()},
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
    _, scale = min(
        (sum(abs(round(advance * s) - stored) for advance, stored in pairs), s) for s in candidates
    )
    exact = sum(1 for advance, stored in pairs if round(advance * scale) == stored)
    return scale, exact


def side_bearing(char: str, size: int, oversample: int = 100) -> float:
    """Left side bearing in pixels at `size`, measured off an unhinted rasterisation.

    Read at the target size the hinter has already snapped it to whole pixels, which loses
    exactly the distinction - flat-sided letters carry a bearing of one, round ones of
    none - that decides the value CWDH stores.
    """
    big = ImageFont.truetype(str(TTF), size * oversample)
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
        if code > 0x20 and math.floor(side_bearing(chr(code), size)) == source.widths[index][0]
    )


def render_glyph(font: ImageFont.FreeTypeFont, char: str, cell: tuple[int, int], fit: dict):
    core, silhouette = rasterise(font, char, cell, fit["y_offset"], fit["pen"])
    return quantise(core, fit["core_gamma"]), quantise(silhouette, fit["alpha_gamma"])


def generate(check_bearings: bool = False) -> dict:
    source = bcfnt.parse(REFERENCE_FONT.read_bytes())
    cell = bcfnt.cell_size(source)
    fit = calibrate(source)
    font = ImageFont.truetype(str(TTF), fit["pixel_size"])
    scale, exact = advance_scale(source, font)

    glyphs = {}
    for code in WANTED:
        char = chr(code)
        core, silhouette = render_glyph(font, char, cell, fit)
        inked = [x for row in silhouette for x, value in enumerate(row) if value]
        glyphs[f"{code:04X}"] = {
            "char": char,
            "left": math.floor(side_bearing(char, fit["pixel_size"])),
            "glyph_width": max(inked) + 1,
            "char_width": round(font.getlength(char) * scale),
            # alpha is the whole silhouette, luminance the white core inside it.
            "alpha": ["".join(f"{value:X}" for value in row) for row in silhouette],
            "luminance": ["".join(f"{value:X}" for value in row) for row in core],
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
            "weekday Нд has letters to draw with. Written by tools/hud_glyphs.py. One hex "
            "nibble per pixel, ink flush left as the cells store it: `alpha` is the whole "
            "silhouette including the one-pixel black outline, `luminance` the white core."
        ),
        "_source": source_info,
        "glyphs": glyphs,
    }


def side_by_side(left: list[list[int]], right: list[list[int]], caption: str) -> None:
    print(caption)
    for row_l, row_r in zip(left, right):
        a = "".join(RAMP[v * 9 // 15] for v in row_l)
        b = "".join(RAMP[v * 9 // 15] for v in row_r)
        print(f"  |{a}|  |{b}|")


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
        f"\nfit: {info['pixel_size']}px pen={info['pen']} dy={info['y_offset']} "
        f"gamma core={info['core_gamma']} alpha={info['alpha_gamma']}, "
        f"error {info['error']} over {len(REFERENCES)} reference glyphs"
    )
    print(f"     advance scale {info['advance_scale']} exact for {info['advance_exact']}, "
          f"bearing exact for {info['bearing_exact']}")

    source = bcfnt.parse(REFERENCE_FONT.read_bytes())
    cell = bcfnt.cell_size(source)
    font = ImageFont.truetype(str(TTF), info["pixel_size"])
    for code in REFERENCES[:2]:
        core, silhouette = render_glyph(font, chr(code), cell, info)
        original = bcfnt.glyph_rows(source, code)
        error = info["per_glyph"][f"{code:04X}"]
        side_by_side(core, [[l for l, _ in row] for row in original],
                     f"\nU+{code:04X} {chr(code)} core: rendered | original   (error {error})")
        side_by_side(silhouette, [[a for _, a in row] for row in original],
                     f"U+{code:04X} {chr(code)} silhouette: rendered | original")

    for code, glyph in asset["glyphs"].items():
        print(f"\nU+{code} {glyph['char']}  left={glyph['left']} glyph_width={glyph['glyph_width']} "
              f"char_width={glyph['char_width']}   core | silhouette")
        side_by_side(
            [[int(c, 16) for c in row] for row in glyph["luminance"]],
            [[int(c, 16) for c in row] for row in glyph["alpha"]],
            "",
        )


if __name__ == "__main__":
    main()
