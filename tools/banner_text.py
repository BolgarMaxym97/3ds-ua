"""Render a banner title texture the way Nintendo encodes it.

    python3 tools/banner_text.py 0004001000022000
    python3 tools/banner_text.py --all

Development tool, not part of the build: it needs Pillow, while everything the build runs
is standard library only. It writes assets/banner/<TID>_<texture>.la4 - the raw pixels that
tools/banner.py drops into the banner's Russian slot - plus a .png to look at.

**Encoding.** The texture is 8 bits per pixel, but it is not greyscale: it is LA4,
luminance in the high nibble and alpha in the low one. Read as dark glyphs inside an opaque
white outline that fades out - System Settings, Russian slot:

    0xF0  L15 A0   background, transparent white      21553 px
    0xFF  L15 A15  the outline, opaque white            880 px
    0x3F  L3  A15  the glyph body, opaque dark         1750 px
    0xF3..0xF1     the outline fading into nothing    ~5000 px

Written as plain 8-bit grey - which is what the first attempt did - every antialiased pixel
comes out as some middling L and a low A, and the caption renders washed out on hardware.

**Layout.** Measured per title off the other language slots, because the two banners we
dumped do not agree:

  System Settings fits every language into the same 352-pixel-wide box and lets the height
  fall where it may - 33 in Russian, 37 in German, 34 in Portuguese. So: scale to width.

  Activity Log keeps the type size instead and lets the width vary - 354 for "Activity Log",
  366 for "Aktivitätslog", both 62 tall - and breaks into two lines when a name is too long
  for one. So: fixed size, and the baseline is taken from a reference string whose box was
  measured in the original texture, which keeps our line sitting exactly where Nintendo's
  sat.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent

HELVETICA = "/System/Library/Fonts/HelveticaNeue.ttc"
RENDER_SIZE = 140        # for scale-to-width: rendered large, then scaled into the box

# One entry per texture we replace. `reference` is a string that is actually in the original
# texture of another language slot, with the ink box it occupies there - that is what pins
# the baseline. Fonts were picked by rendering the reference and scoring the ink overlap
# against the real thing: Helvetica Neue regular 57.4% mismatch (next best 57.9), bold
# 16.8% (next best 20.8).
TEXTURES = {
    "0004001000022000": {
        "text": "Налаштування системи",
        "texture": "COMMON1",
        "size": (512, 64),
        "font": (HELVETICA, 0),
        "layout": "width",
        "ink_width": 352,          # x = 80..432 in every language slot
        "centre": (256, 24.5),
        "glyph_luma": 3,           # 0x3F is the glyph body here
        "alpha": {"mode": "outline", "dilate": 3, "blur": 0.8},
    },
    "0004001000022200": {
        "text": "Журнал дій",
        "texture": "TEX1",
        "size": (512, 128),
        "font": (HELVETICA, 1),    # bold, as this banner is set
        "layout": "fixed",
        "font_size": 67,           # reproduces the 62-pixel ink height of the original
        "reference": ("Activity Log", (80, 40, 434, 102)),  # the English slot, measured
        "centre_x": 257,
        "glyph_luma": 0,           # 0x0F: this banner sets its text in black, not dark grey
        # Alpha is not an outline here but a hard-edged white plate behind the line, the
        # same one in every single-line slot (English and German are identical), with
        # notches where descenders drop out of it. Ours is the plate plus our own glyphs.
        "alpha": {"mode": "plate", "rect": (37, 37, 483, 104), "dilate": 3},
    },
}


def _font(spec: dict, size: int) -> ImageFont.FreeTypeFont:
    path, index = spec["font"]
    return ImageFont.truetype(path, size, index=index)


def _draw(text: str, font: ImageFont.FreeTypeFont) -> tuple[Image.Image, tuple[int, int, int, int]]:
    canvas = Image.new("L", (4000, 400), 0)
    ImageDraw.Draw(canvas).text((100, 100), text, font=font, fill=255)
    box = canvas.getbbox()
    if box is None:
        raise SystemExit(f"nothing rendered for {text!r}")
    return canvas, box


def coverage(spec: dict) -> Image.Image:
    """The glyph mask, placed the way this banner places its text."""
    width, height = spec["size"]
    out = Image.new("L", (width, height), 0)

    if spec["layout"] == "width":
        canvas, box = _draw(spec["text"], _font(spec, RENDER_SIZE))
        ink = canvas.crop(box)
        ink_height = round(ink.size[1] * spec["ink_width"] / ink.size[0])
        ink = ink.resize((spec["ink_width"], ink_height), Image.LANCZOS)
        centre_x, centre_y = spec["centre"]
        out.paste(ink, (centre_x - spec["ink_width"] // 2, round(centre_y - ink_height / 2)))
    else:
        font = _font(spec, spec["font_size"])
        # Where the reference string lands when drawn at the same origin, against where it
        # really sits in the original: the difference is the baseline offset to apply.
        _, reference_box = _draw(spec["reference"][0], font)
        target = spec["reference"][1]
        canvas, box = _draw(spec["text"], font)
        ink = canvas.crop(box)
        top = target[1] + (box[1] - reference_box[1])
        out.paste(ink, (spec["centre_x"] - ink.size[0] // 2, top))

    if out.getbbox()[3] > height or out.getbbox()[2] > width:
        raise SystemExit(f"the text does not fit in {width}x{height}")
    return out


def alpha_mask(mask: Image.Image, spec: dict) -> Image.Image:
    """What the texture is opaque over: a fading outline, or a flat plate."""
    alpha = spec["alpha"]
    grown = mask.filter(ImageFilter.MaxFilter(alpha["dilate"]))
    if alpha["mode"] == "outline":
        return grown.filter(ImageFilter.GaussianBlur(alpha["blur"]))
    plate = Image.new("L", mask.size, 0)
    ImageDraw.Draw(plate).rectangle(alpha["rect"], fill=255)
    return ImageChops.lighter(plate, grown)


def encode_la4(mask: Image.Image, spec: dict) -> bytes:
    """Glyph mask -> LA4: luminance falls where the glyph is, alpha where the plate is."""
    glyph, opaque = mask.load(), alpha_mask(mask, spec).load()
    width, height = mask.size
    body = spec["glyph_luma"]

    out = bytearray(width * height)
    for y in range(height):
        for x in range(width):
            ink = min(1.0, glyph[x, y] / 255)
            around = min(1.0, opaque[x, y] / 255)
            luma = round(15 - (15 - body) * ink)
            alpha = round(15 * around)
            out[y * width + x] = (luma << 4) | alpha
    return bytes(out)


def preview(pixels: bytes, size: tuple[int, int], background: int = 255) -> Image.Image:
    """What the texture looks like composited over a flat background."""
    width, height = size
    image = Image.new("L", size)
    put = image.load()
    for index, value in enumerate(pixels):
        luma, alpha = (value >> 4) * 17, (value & 0xF) / 15
        put[index % width, index // width] = round(luma * alpha + background * (1 - alpha))
    return image


def render(tid: str) -> Path:
    spec = TEXTURES[tid]
    pixels = encode_la4(coverage(spec), spec)
    asset = ROOT / "assets" / "banner" / f"{tid}_{spec['texture']}.la4"
    asset.parent.mkdir(parents=True, exist_ok=True)
    asset.write_bytes(pixels)
    preview(pixels, spec["size"]).save(asset.with_suffix(".png"))
    print(
        f"{asset.relative_to(ROOT)} ({len(pixels)} bytes) - {spec['text']!r}, "
        f"{spec['size'][0]}x{spec['size'][1]} {spec['texture']}"
    )
    return asset


def main(argv: list[str]) -> None:
    if not argv or (argv[0] not in TEXTURES and argv[0] != "--all"):
        raise SystemExit(f"usage: banner_text.py <{'|'.join(TEXTURES)}|--all>")
    for tid in TEXTURES if argv[0] == "--all" else [argv[0]]:
        render(tid)


if __name__ == "__main__":
    main(sys.argv[1:])
