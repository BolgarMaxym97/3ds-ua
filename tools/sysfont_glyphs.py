"""Give the shared system font real Ukrainian letters - і ї є ґ І Ї Є Ґ and ʼ.

Opt-in, and the one part of the project that is not served from the SD card: the font is
system data (archive 0004009B00014002, `cbf_std.bcfnt.lz`), not part of any title Luma can
redirect. See docs/internals.en.md, "Real Ukrainian letters in the system font".

Development-time tool, like tools/hud_glyphs.py: it needs Pillow and fontTools, the main
build does not. It reads two of your own dumps at run time and writes nothing that is
Nintendo's into the repository:

    work/0004009B00014002/cbf_std.bcfnt.lz        the shared font (docs/dumping.en.md, step 4)
    work/0004003000009D02/romfs/font/nintendo.ttf the outline font the bitmaps were made from
                                                  (the Internet Browser's romfs, as for the HUD)

The font is 24x30 cells of A4 - plain 4-bit alpha - and lacks exactly the eight Ukrainian
letters plus the modifier apostrophe. Each new glyph is made from a letter the font already
has, so it is drawn by the same hand:

    і І ї Ї ʼ   the cell of i I ï Ï ’ copied as it is - same shape, same pixels, same widths
                (U+02BC and U+2019 are one outline in the TTF)
    є Є         the cell of э Э mirrored left to right; the two side bearings swap places
    ґ Ґ         г Г with an upturn: a stem as thick as the letter's own, standing on the right
                end of the top bar. Its height is the median of seven common sans fonts
                (Arial, Segoe UI, Tahoma, Verdana, Calibri, Arial Bold, Segoe UI Bold):
                0.26 of the x-height above ґ, 0.22 of the cap height above Ґ.

Copies and mirrors need no rasteriser: the stored pixels are already the best possible
rendering. The two upturned letters do. Their outline is the TTF's г/Г with the stem added,
rasterised with parameters fitted - not guessed - to redraw the font's own straight-stemmed
Cyrillic (`FIT_REFERENCES`): pixel size, baseline, coverage gamma, and per glyph the
sub-pixel phase. The fit is reported, and the donor letter itself is redrawn with the same
parameters as a check. Only what the new outline adds over the donor's is taken from the
rasteriser and laid over the donor's stored pixels, so everything the two letters share stays
exactly as Nintendo rendered it. The new glyph keeps the donor's CWDH entry - the upturn
stands inside the bar, so neither the advance nor the ink width changes.

The font then gets one more 2 KiB sheet (it had four free cells, and nine glyphs are added),
which keeps it far below the 0x332000-byte shared-memory block the system loads it into.

Usage:
    python3 tools/sysfont_glyphs.py                      # -> dist_sysfont/cbf_std.bcfnt.lz
    python3 tools/sysfont_glyphs.py --report             # also the fit and an ASCII preview
    python3 tools/sysfont_glyphs.py --png preview.png    # glyph sheet at 1x and 4x
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import bcfnt  # noqa: E402
import lz11  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "work" / "0004009B00014002" / "cbf_std.bcfnt.lz"
TTF = ROOT / "work" / "0004003000009D02" / "romfs" / "font" / "nintendo.ttf"
OUTPUT = ROOT / "dist_sysfont" / "cbf_std.bcfnt.lz"

# What the system gives the font to live in: a 0x332000-byte block, 0x80 of it a header.
SHARED_FONT_LIMIT = 0x332000 - 0x80

COPY = {0x0456: 0x0069, 0x0406: 0x0049, 0x0457: 0x00EF, 0x0407: 0x00CF, 0x02BC: 0x2019}
MIRROR = {0x0454: 0x044D, 0x0404: 0x042D}
# letter -> (donor, upturn height as a share of the donor's height)
UPTURN = {0x0491: (0x0433, 0.26), 0x0490: (0x0413, 0.22)}
# Every added code point and the glyph whose advance it has. validate.py reads this.
DONORS = COPY | MIRROR | {code: donor for code, (donor, _) in UPTURN.items()}

# Straight-stemmed letters of the same design: Г г П п Н н Т т Ш ш, and Latin I.
FIT_REFERENCES = [0x0413, 0x0433, 0x041F, 0x043F, 0x041D, 0x043D, 0x0422, 0x0442, 0x0428, 0x0448, 0x0049]
SIZES = [22 + i * 0.25 for i in range(17)]  # em in pixels
GAMMAS = (0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.25)
SUPER = 16  # supersampling per pixel, also the step of phase and baseline: 1/16 px
RAMP = "0123456789ABCDEF"


def load_source() -> bcfnt.Font:
    if not SOURCE.exists():
        raise SystemExit(f"{SOURCE.relative_to(ROOT)} is missing - dump it first (docs/dumping.en.md, step 4)")
    return bcfnt.parse(lz11.decompress(SOURCE.read_bytes()))


# ---------------------------------------------------------------- outlines


def outline(ttf, code: int) -> list[list[tuple[float, float]]]:
    """The glyph's contours in font units, curves flattened to short lines."""
    from fontTools.pens.basePen import BasePen

    class Flatten(BasePen):
        def __init__(self, glyphset):
            super().__init__(glyphset)
            self.contours: list[list[tuple[float, float]]] = []

        def _moveTo(self, p):
            self.contours.append([p])

        def _lineTo(self, p):
            self.contours[-1].append(p)

        def _curveToOne(self, p1, p2, p3):
            (x0, y0) = self.contours[-1][-1]
            for i in range(1, 9):
                t = i / 8
                a, b, c, d = (1 - t) ** 3, 3 * t * (1 - t) ** 2, 3 * t * t * (1 - t), t**3
                self.contours[-1].append(
                    (a * x0 + b * p1[0] + c * p2[0] + d * p3[0], a * y0 + b * p1[1] + c * p2[1] + d * p3[1])
                )

        def _qCurveToOne(self, p1, p2):
            (x0, y0) = self.contours[-1][-1]
            for i in range(1, 9):
                t = i / 8
                a, b, c = (1 - t) ** 2, 2 * t * (1 - t), t * t
                self.contours[-1].append((a * x0 + b * p1[0] + c * p2[0], a * y0 + b * p1[1] + c * p2[1]))

    glyphset = ttf.getGlyphSet()
    pen = Flatten(glyphset)
    glyphset[ttf.getBestCmap()[code]].draw(pen)
    return pen.contours


def with_upturn(contours: list[list[tuple[float, float]]], share: float) -> list[list[tuple[float, float]]]:
    """г/Г -> ґ/Ґ: the stem, measured off the letter itself, raised on the bar's right end.

    The letter is one contour: the stem on the left, the bar on top. The stem's width is the
    distance between its two vertical edges; the upturn is a rectangle that wide, flush with
    the bar's right end, from the bar's bottom edge up to `share` of the letter's height
    above its top. It overlaps the bar rather than touching it, so the union has no seam.
    """
    if len(contours) != 1:
        raise SystemExit("the donor letter was expected to be a single contour")
    points = contours[0]
    xs = sorted({round(x) for x, _ in points})
    top = max(y for _, y in points)
    right = max(x for x, _ in points)
    stem = xs[1] - xs[0]
    bar_bottom = max(y for x, y in points if round(x) == right and y < top)
    rise = top * (1 + share)
    upturn = [(right - stem, bar_bottom), (right - stem, rise), (right, rise), (right, bar_bottom)]
    if (_area(upturn) > 0) != (_area(points) > 0):
        upturn.reverse()  # same winding as the letter, or the filler takes it for a hole
    return [points, upturn]


def _area(points: list[tuple[float, float]]) -> float:
    return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1])) / 2


# ---------------------------------------------------------------- rasterising


def supersampled(contours, scale: float, cell: tuple[int, int], baseline: int):
    """Coverage at SUPER x SUPER per pixel, with room for SUPER sub-pixel shifts each way.

    Non-zero filling the simple way: outer contours (one orientation) are unioned, holes
    (the other) cut out of them. The letters drawn here have no overlapping holes.
    """
    from PIL import Image, ImageChops, ImageDraw

    width, height = cell
    size = ((width + 2) * SUPER, (height + 2) * SUPER)
    origin_x, origin_y = SUPER, (baseline + 1) * SUPER
    outer = Image.new("1", size, 0)
    holes = Image.new("1", size, 0)
    sign = None
    for points in contours:
        area = _area(points)
        sign = sign if sign is not None else area > 0
        target = outer if (area > 0) == sign else holes
        ImageDraw.Draw(target).polygon(
            [(origin_x + x * scale * SUPER, origin_y - y * scale * SUPER) for x, y in points], fill=1
        )
    return ImageChops.subtract(outer.convert("L"), holes.convert("L"))


def place(big, phase: int, lift: int, cell: tuple[int, int], gamma: float):
    """Shift by (phase, lift) sixteenths, average down to pixels, quantise to 0-15, crop flush left."""
    from PIL import Image

    width, height = cell
    x0, y0 = SUPER - phase, SUPER + lift
    pixels = big.crop((x0, y0, x0 + (width + 1) * SUPER, y0 + height * SUPER)).reduce(SUPER)
    levels = pixels.point(_levels(gamma))
    box = levels.getbbox()
    left = box[0] if box else 0
    out = Image.new("L", cell, 0)
    out.paste(levels.crop((left, 0, left + width, height)), (0, 0))
    return out


@functools.cache
def _levels(gamma: float) -> list[int]:
    """Coverage 0-255 -> the 0-15 alpha an A4 cell stores."""
    return [min(15, round(15 * (v / 255) ** gamma)) for v in range(256)]


def cell_image(rows: list[list[int]]):
    from PIL import Image

    image = Image.new("L", (len(rows[0]), len(rows)))
    image.putdata([v for row in rows for v in row])
    return image


def difference(a, b) -> int:
    from PIL import ImageChops, ImageStat

    return int(ImageStat.Stat(ImageChops.difference(a, b)).sum[0])


def calibrate(source: bcfnt.Font, ttf) -> dict:
    """Pixel size, baseline offset and gamma shared by all references; phase per glyph."""
    cell = bcfnt.cell_size(source)
    baseline = source.sheets.baseline
    upm = ttf["head"].unitsPerEm
    targets = {code: cell_image(bcfnt.glyph_rows(source, code)) for code in FIT_REFERENCES}
    shapes = {code: outline(ttf, code) for code in FIT_REFERENCES}

    best = None
    for size in SIZES:
        bigs = {code: supersampled(shapes[code], size / upm, cell, baseline) for code in FIT_REFERENCES}
        for lift in range(-SUPER, SUPER + 1, 2):
            for gamma in GAMMAS:
                total, phases = 0, {}
                for code in FIT_REFERENCES:
                    error, phase = min(
                        (difference(place(bigs[code], p, lift, cell, gamma), targets[code]), p)
                        for p in range(0, SUPER, 2)
                    )
                    total += error
                    phases[code] = phase
                    if best and total >= best["error"]:
                        break
                else:
                    if best is None or total < best["error"]:
                        best = {"size": size, "lift": lift, "gamma": gamma, "error": total, "phases": phases}
    best["pixels"] = len(FIT_REFERENCES) * cell[0] * cell[1]
    return best


def fine_phase(big, target, lift: int, cell, gamma: float) -> tuple[int, int]:
    return min((difference(place(big, p, lift, cell, gamma), target), p) for p in range(SUPER))


# ---------------------------------------------------------------- the glyphs


def make_glyphs(source: bcfnt.Font, ttf, fit: dict) -> tuple[dict, dict]:
    """{code: (rows, left, glyph width, char width)} for bcfnt.add_glyphs, plus a report."""
    glyphs, report = {}, {}
    for code, donor in COPY.items():
        glyphs[code] = (bcfnt.glyph_rows(source, donor), *source.widths[source.cmap[donor]])
    for code, donor in MIRROR.items():
        left, ink, advance = source.widths[source.cmap[donor]]
        rows = bcfnt.glyph_rows(source, donor)
        mirrored = [row[:ink][::-1] + row[ink:] for row in rows]
        glyphs[code] = (mirrored, advance - left - ink, ink, advance)

    cell = bcfnt.cell_size(source)
    upm = ttf["head"].unitsPerEm
    for code, (donor, share) in UPTURN.items():
        scale = fit["size"] / upm
        target = cell_image(bcfnt.glyph_rows(source, donor))
        donor_big = supersampled(outline(ttf, donor), scale, cell, source.sheets.baseline)
        error, phase = fine_phase(donor_big, target, fit["lift"], cell, fit["gamma"])
        big = supersampled(with_upturn(outline(ttf, donor), share), scale, cell, source.sheets.baseline)
        # The upturn is what the new outline adds over the donor's, both drawn alike; it goes
        # on top of the donor's stored pixels, so everything the two letters share stays
        # exactly as Nintendo rendered it rather than as the fit approximates it.
        new = place(big, phase, fit["lift"], cell, fit["gamma"]).tobytes()
        old = place(donor_big, phase, fit["lift"], cell, fit["gamma"]).tobytes()
        stored = [v for row in bcfnt.glyph_rows(source, donor) for v in row]
        merged = [min(15, s + max(0, n - o)) for s, n, o in zip(stored, new, old)]
        rows = [merged[y * cell[0] : (y + 1) * cell[0]] for y in range(cell[1])]
        left, ink, advance = source.widths[source.cmap[donor]]
        inked = max(x for row in rows for x, v in enumerate(row) if v) + 1
        if inked > ink:
            raise SystemExit(f"U+{code:04X}: the upturn widened the glyph ({inked} > {ink})")
        if any(rows[0]):
            raise SystemExit(f"U+{code:04X}: the upturn reaches the top of the cell")
        glyphs[code] = (rows, left, ink, advance)
        report[code] = {"donor_error": error, "phase": phase}
    return glyphs, report


def build_font(report_fit: bool = False) -> tuple[bytes, bcfnt.Font, bcfnt.Font, dict, dict]:
    from fontTools.ttLib import TTFont

    if not TTF.exists():
        raise SystemExit(f"{TTF.relative_to(ROOT)} is missing - copy romfs/font/nintendo.ttf of the "
                         "Internet Browser (0004003000009D02) there")
    source = load_source()
    ttf = TTFont(str(TTF))
    fit = calibrate(source, ttf)
    glyphs, report = make_glyphs(source, ttf, fit)

    patched = bcfnt.parse(bcfnt.build(source))
    bcfnt.add_glyphs(patched, glyphs, grow=True)
    data = bcfnt.build(patched)
    if len(data) > SHARED_FONT_LIMIT:
        raise SystemExit(f"{len(data)} bytes do not fit the {SHARED_FONT_LIMIT}-byte shared font block")
    return data, source, patched, fit, report


# ---------------------------------------------------------------- output


def side_by_side(left: list[list[int]], right: list[list[int]], width: int) -> list[str]:
    """Two cells as hex levels, the rows where either has ink."""
    def text(row: list[int]) -> str:
        return "".join(RAMP[v] if v else "." for v in row[: width + 1])

    return [f"  {text(a)}   {text(b)}" for a, b in zip(left, right) if any(a) or any(b)]


def write_png(font: bcfnt.Font, path: Path) -> None:
    """Every added glyph next to its donor, at 1x and 4x, black on white."""
    from PIL import Image, ImageOps

    pairs = [(code, donor) for code, donor in DONORS.items()]
    w, h = bcfnt.cell_size(font)
    sheet = Image.new("L", ((w + 4) * len(pairs), (h + 4) * 2), 255)
    for i, (code, donor) in enumerate(pairs):
        for j, which in enumerate((donor, code)):
            alpha = cell_image([[v * 17 for v in row] for row in bcfnt.glyph_rows(font, which)])
            sheet.paste(ImageOps.invert(alpha), (i * (w + 4) + 2, j * (h + 4) + 2))
    big = sheet.resize((sheet.width * 4, sheet.height * 4), Image.NEAREST)
    canvas = Image.new("L", (big.width, sheet.height + 8 + big.height), 255)
    canvas.paste(sheet, (0, 0))
    canvas.paste(big, (0, sheet.height + 8))
    canvas.save(path)


def write_upturn(source: bcfnt.Font, patched: bcfnt.Font, packed: bytes, path: Path) -> int:
    """The installer's half of the job: only the pixels the upturn adds, nothing of Nintendo's.

    The installer app rebuilds the patched font on the console from the console's own font
    (copies and mirrors need no data), so the one thing it has to be given is the upturn of
    ґ Ґ - what the new outline adds over the donor's stored pixels. Layout, little-endian:

        "UAUP" u8 version=1, u8 glyph count
        sha256 of the source font file (.lz), sha256 of the patched font file (.lz)
        per glyph: u16 code, u16 donor, u16 pixel count, then (u8 x, u8 y, u8 alpha) each

    The two hashes let the app refuse a font it was not made for and check what it built.
    """
    out = bytearray(b"UAUP" + bytes((1, len(UPTURN))))
    out += hashlib.sha256(SOURCE.read_bytes()).digest() + hashlib.sha256(packed).digest()
    total = 0
    for code, (donor, _) in sorted(UPTURN.items()):
        old, new = bcfnt.glyph_rows(source, donor), bcfnt.glyph_rows(patched, code)
        changed = [(x, y, v) for y, row in enumerate(new) for x, v in enumerate(row) if v != old[y][x]]
        out += struct.pack("<HHH", code, donor, len(changed))
        out += b"".join(bytes(pixel) for pixel in changed)
        total += len(changed)
    path.write_bytes(bytes(out))
    return total


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", action="store_true", help="print the fit and the new glyphs")
    parser.add_argument("--png", type=Path, help="also write a donor/new glyph sheet")
    parser.add_argument("--out", type=Path, default=OUTPUT, help="where the patched font goes")
    args = parser.parse_args()

    data, source, patched, fit, report = build_font()
    packed = lz11.compress(data)
    if lz11.decompress(packed) != data:
        raise SystemExit("LZ11 round trip failed")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(packed)
    print(f"-> {args.out} ({len(packed)} bytes packed, {len(data)} unpacked, "
          f"{len(patched.sheets.planes) - len(source.sheets.planes)} sheet added, {len(DONORS)} glyphs)")
    upturn = args.out.with_name("upturn.bin")
    pixels = write_upturn(source, patched, packed, upturn)
    print(f"-> {upturn} ({pixels} upturn pixels, the installer's input)")

    if args.png:
        write_png(patched, args.png)
        print(f"-> {args.png}")
    if not args.report:
        return

    print(f"\nfit: {fit['size']}px em, baseline {fit['lift']:+d}/16 px, gamma {fit['gamma']}, "
          f"error {fit['error']} levels over {fit['pixels']} pixels of {len(FIT_REFERENCES)} reference glyphs "
          f"({fit['error'] / fit['pixels']:.3f} per pixel)")
    for code, info in report.items():
        print(f"U+{code:04X}: donor redrawn with error {info['donor_error']}, phase {info['phase']}/16")
    for code, donor in DONORS.items():
        index = patched.cmap[code]
        left, ink, advance = patched.widths[index]
        print(f"\nU+{code:04X} {chr(code)} from U+{donor:04X} {chr(donor)}: left {left}, ink {ink}, advance {advance}")
        print("\n".join(side_by_side(bcfnt.glyph_rows(patched, donor), bcfnt.glyph_rows(patched, code), ink)))


if __name__ == "__main__":
    main()
