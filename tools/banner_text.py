"""Render a banner title texture the way Nintendo encodes it.

    python3 tools/banner_text.py 0004001000022000 "Налаштування системи"

Development tool, not part of the build: it needs Pillow, while everything the build runs
is standard library only. It writes assets/banner/<TID>_COMMON1.la4 - the raw pixels that
tools/banner.py drops into the banner's Russian slot - plus a .png to look at.

Two things have to match the original or the result looks wrong on hardware:

**Layout.** Every language slot of both banners we dumped fits its title into exactly the
same box: 352 pixels wide, x = 80..432, centred vertically on y = 24.5. The height is
whatever that scaling gives - 33 in Russian, 37 in German, 34 in Portuguese. So the text is
scaled to the box, not set at a fixed point size.

**Encoding.** The texture is 512x64 at 8 bits per pixel, but it is not greyscale: it is
LA4, luminance in the high nibble and alpha in the low one. The original reads as dark
glyphs inside an opaque white outline that fades out:

    0xF0  L15 A0   background, transparent white      21553 px
    0xFF  L15 A15  the outline, opaque white            880 px
    0x3F  L3  A15  the glyph body, opaque dark         1750 px
    0xF3..0xF1     the outline fading into nothing    ~5000 px

Written as plain 8-bit grey - which is what the first attempt did - every antialiased
pixel comes out as some middling L and a low A, and the whole caption renders washed out
and semi-transparent.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent

WIDTH, HEIGHT = 512, 64
INK_WIDTH = 352          # the box Nintendo fits every language into
CENTRE_X, CENTRE_Y = 256, 24.5
FONT = "/System/Library/Fonts/HelveticaNeue.ttc"  # closest match to Nintendo's own
RENDER_SIZE = 140        # rendered large, then scaled to the box

GLYPH_LUMA = 3           # L of the glyph body, as in the original
OUTLINE_DILATE = 3       # MaxFilter window: one pixel of outline around the glyph
OUTLINE_BLUR = 0.8       # how fast the outline fades out


def coverage(text: str, font_path: str) -> Image.Image:
    """The glyph mask, scaled into Nintendo's box and placed where Nintendo places it."""
    font = ImageFont.truetype(font_path, RENDER_SIZE)
    canvas = Image.new("L", (4000, 400), 0)
    ImageDraw.Draw(canvas).text((100, 100), text, font=font, fill=255)
    box = canvas.getbbox()
    if box is None:
        raise SystemExit("nothing rendered")
    ink = canvas.crop(box)
    height = round(ink.size[1] * INK_WIDTH / ink.size[0])
    if height > HEIGHT:
        raise SystemExit(f"the text is {height} pixels tall, the texture is {HEIGHT}")
    ink = ink.resize((INK_WIDTH, height), Image.LANCZOS)

    out = Image.new("L", (WIDTH, HEIGHT), 0)
    out.paste(ink, (CENTRE_X - INK_WIDTH // 2, round(CENTRE_Y - height / 2)))
    return out


def encode_la4(mask: Image.Image) -> bytes:
    """Glyph mask -> LA4: luminance falls where the glyph is, alpha where its outline is."""
    outline = mask.filter(ImageFilter.MaxFilter(OUTLINE_DILATE))
    outline = outline.filter(ImageFilter.GaussianBlur(OUTLINE_BLUR))
    glyph, halo = mask.load(), outline.load()

    out = bytearray(WIDTH * HEIGHT)
    for y in range(HEIGHT):
        for x in range(WIDTH):
            ink = min(1.0, glyph[x, y] / 255)
            around = min(1.0, halo[x, y] / 255)
            luma = round(15 - (15 - GLYPH_LUMA) * ink)
            alpha = round(15 * around)
            out[y * WIDTH + x] = (luma << 4) | alpha
    return bytes(out)


def preview(pixels: bytes, background: int = 255) -> Image.Image:
    """What the texture looks like composited over a flat background."""
    image = Image.new("L", (WIDTH, HEIGHT))
    put = image.load()
    for index, value in enumerate(pixels):
        luma, alpha = (value >> 4) * 17, (value & 0xF) / 15
        put[index % WIDTH, index // WIDTH] = round(luma * alpha + background * (1 - alpha))
    return image


def main(argv: list[str]) -> None:
    if len(argv) < 2:
        raise SystemExit('usage: banner_text.py <TID> "<text>" [font]')
    tid, text = argv[0], argv[1]
    font_path = argv[2] if len(argv) > 2 else FONT

    pixels = encode_la4(coverage(text, font_path))
    asset = ROOT / "assets" / "banner" / f"{tid}_COMMON1.la4"
    asset.parent.mkdir(parents=True, exist_ok=True)
    asset.write_bytes(pixels)
    preview(pixels).save(asset.with_suffix(".png"))
    print(f"{asset.relative_to(ROOT)} ({len(pixels)} bytes) - {text!r} in {Path(font_path).name}")


if __name__ == "__main__":
    main(sys.argv[1:])
