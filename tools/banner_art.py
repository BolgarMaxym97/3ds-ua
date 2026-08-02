"""Derive a banner texture from the title's own artwork, for the two banners whose Russian
slot is a drawing rather than a line of type.

    python3 tools/banner_art.py 0004001000022800     # cut the word down to ПЛОЩА
    python3 tools/banner_art.py 0004001000022E00     # reset the subtitle under the logo
    python3 tools/banner_art.py --all

Development tool, like tools/banner_text.py: it needs Pillow, writes
assets/banner/<TID>_<texture>.rgba4444 plus a .png to look at, and takes no part in the
build. Both textures here are RGBA4444, 512x128 - see tools/cgfx.py for the container side.

**StreetPass Mii Plaza.** The Russian slot is a logotype: `ПЛОЩАДЬ` in bevelled green caps
whose letters merge into one mass at the base, over `StreetPass Mii`. Ukrainian needs
`ПЛОЩА` - the same five letters that open the Russian word - so the drawing is cut rather
than redrawn. Above the base the letters are separated by transparent pixels and the cut
follows that gap; through the base they share their fill but keep their own dark outlines,
so the cut follows the A's outline instead, and the white halo the D used to stand in for is
grown back along it. The result is recentred on the axis the Russian word sat on.

**AR Games.** The logo is a row of cubes, identical in every language slot; only the
subtitle under it changes (rows 94-114, `Расширенная реальность`). So the whole slot is
kept and only that band is redrawn: black caps with a one-pixel white outline, letterspaced.
Nintendo's face is a squarish grotesque no macOS font matches; Arial Black scores closest
(14.0% ink mismatch against the Russian line, next best 13.8% was Gill Sans, a different
look entirely) and carries the same weight.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
import cbmd  # noqa: E402
import cgfx  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

ARIAL_BLACK = "/Library/Fonts/Arial Black.ttf"

PLAZA = {
    "title": "StreetPass Mii Plaza EUR",
    "texture": "COMMON1",
    "band": 60,            # rows 0..59 carry the word, descenders included
    "base": 38,            # where the letters stop being separate shapes
    "base_cut": 314,       # the D's leftmost pixel at the baseline, so: everything before it
    "notch": (295, 320),   # where to look for the transparent gap between А and Д
    # Below the baseline the word is three separate pieces: the Щ's tail (x 252..275) and
    # the D's two feet (302..325 and 345..367), all of them rows 53..59. The tail has to
    # travel with the word and the feet have to go, so these rows are cut short of them -
    # and only their span is cleared, because the leaf and the dots of Mii live past it.
    "tail_row": 53,
    "tail_cut": 290,
    "tail_span": (240, 377),
    "seam": (297, 316),    # where to look for the stroke that separates the A from the D
    "halo": 3,             # how far the white halo reaches past a letter, as Nintendo draws it
    "centre": 249,         # the axis the Russian word is centred on
}

AR_GAMES = {
    "title": "AR Games EUR",
    "texture": "COMMON1",
    "text": "Розширена реальність",
    "band": (88, 128),     # the subtitle's rows; the cubes end at 86
    "font": (ARIAL_BLACK, 0),
    "font_size": 21,       # matches the 17-pixel ink height of the Russian subtitle
    "tracking": 7.6,       # its letterspacing, measured off the same line
    "top": 96,             # where the caps start
    "centre_x": 254,       # the centre both the Russian and the English subtitle sit on
    "outline": 3,          # dilation of the white outline around the glyphs, in pixels
}


def source(tid: str) -> Image.Image:
    """The title's own Russian slot, decoded to RGBA."""
    banner = cbmd.parse((ROOT / "work" / tid / "banner").read_bytes())
    raw = banner.cgfx(cbmd.EUR_RU)
    texture = cgfx.find(raw, "COMMON1")
    if texture.pica_format != cgfx.FORMAT_RGBA4444:
        raise SystemExit(f"{tid}: COMMON1 is PICA format {texture.pica_format}, expected 4")
    pixels = cgfx.unswizzle(raw, texture)
    image = Image.new("RGBA", (texture.width, texture.height))
    put = image.load()
    for at in range(0, len(pixels), 2):
        value = pixels[at] | (pixels[at + 1] << 8)
        index = at // 2
        put[index % texture.width, index // texture.width] = (
            (value >> 12) * 17,
            ((value >> 8) & 0xF) * 17,
            ((value >> 4) & 0xF) * 17,
            (value & 0xF) * 17,
        )
    return image


def encode(image: Image.Image) -> bytes:
    """RGBA back to RGBA4444, one little-endian half-word per pixel."""
    data = image.tobytes()
    out = bytearray()
    for at in range(0, len(data), 4):
        r, g, b, a = data[at : at + 4]
        value = (
            (round(r / 17) << 12) | (round(g / 17) << 8) | (round(b / 17) << 4) | round(a / 17)
        )
        out += struct.pack("<H", value)
    return bytes(out)


def _dark(pixel) -> bool:
    """A pixel of the dark green the letters are outlined in."""
    r, g, b, a = pixel
    return a > 128 and g < 200 and r < 150


def _notch(pixels, y: int, spec: dict) -> int | None:
    """The first transparent column between the А and the Д on this row."""
    for x in range(*spec["notch"]):
        if pixels[x, y][3] == 0:
            return x
    return None


def _seam(pixels, y: int, spec: dict) -> int | None:
    """Where to cut once the letters have merged: past the A's own dark outline.

    Merging costs the letters their white halo, not their outlines - between the A and the D
    there are still two dark strokes with the green fill of the base between them. So the
    scan skips the fill, takes the first dark run, and cuts right after it: the A keeps a
    complete outline and nothing of the D comes along.
    """
    start, stop = spec["seam"]
    x = start
    while x < stop and not _dark(pixels[x, y]):
        x += 1
    if x >= stop:
        return None
    while x < stop and _dark(pixels[x, y]):
        x += 1
    return x


def plaza(spec: dict = PLAZA, tid: str = "0004001000022800") -> Image.Image:
    image = source(tid)
    px = image.load()
    band, base, halo = spec["band"], spec["base"], spec["halo"]

    # Where each row of the word ends. Above the base it is the gap between the letters -
    # which closes a row or two before they actually merge, so those rows keep the last
    # value it gave, the column the A's own halo ends on. Through the base it is the seam.
    # Row 39 or so runs along the horizontal stroke where the letters join and the scan
    # comes back with the far side of it, hence the one-pixel-per-row ceiling.
    cuts: dict[int, int] = {}
    last = None
    for y in range(band):
        if y >= spec["tail_row"]:
            cuts[y] = spec["tail_cut"]
            continue
        if y < base:
            found = _notch(px, y, spec)
        else:
            found = _seam(px, y, spec)
            if found is not None and last is not None:
                found = min(found, last + 1)
        last = cuts[y] = found or last or spec["base_cut"]

    word = Image.new("RGBA", (image.width, band), (0, 0, 0, 0))
    put = word.load()
    for y in range(band):
        for x in range(cuts[y]):
            if px[x, y][3]:
                put[x, y] = px[x, y]

    # The cut edge is a bare outline: the halo that used to be there belonged to the D.
    # Growing the silhouette by the halo width and painting what appears in the strip along
    # the seam puts it back, and rounds the corner where the base ends the way Nintendo's
    # own word ends are rounded.
    alpha = word.split()[3].point(lambda v: 255 if v else 0)
    grown = ImageChops.subtract(alpha.filter(ImageFilter.MaxFilter(2 * halo + 1)), alpha)
    edge = grown.load()
    for y in range(base, spec["tail_row"]):
        for x in range(cuts[y] - 1, cuts[y] + halo + 1):
            if edge[x, y]:
                put[x, y] = (255, 255, 255, 255)

    box = word.getbbox()
    piece = word.crop(box)
    out = image.copy()
    blank = (0, 0, 0, 0)
    out.paste(Image.new("RGBA", (image.width, spec["tail_row"]), blank), (0, 0))
    span = spec["tail_span"]
    out.paste(
        Image.new("RGBA", (span[1] - span[0], band - spec["tail_row"]), blank),
        (span[0], spec["tail_row"]),
    )
    out.alpha_composite(piece, (round(spec["centre"] - piece.width / 2), box[1]))
    return out


def _letterspaced(spec: dict) -> Image.Image:
    path, index = spec["font"]
    font = ImageFont.truetype(path, spec["font_size"], index=index)
    canvas = Image.new("L", (2400, 200), 0)
    draw = ImageDraw.Draw(canvas)
    x = 100.0
    for char in spec["text"]:
        draw.text((x, 60), char, font=font, fill=255)
        x += font.getlength(char) + spec["tracking"]
    box = canvas.getbbox()
    if box is None:
        raise SystemExit(f"nothing rendered for {spec['text']!r}")
    return canvas.crop(box)


def ar_games(spec: dict = AR_GAMES, tid: str = "0004001000022E00") -> Image.Image:
    image = source(tid)
    top, bottom = spec["band"]
    image.paste(Image.new("RGBA", (image.width, bottom - top), (0, 0, 0, 0)), (0, top))

    glyphs = _letterspaced(spec)
    mask = Image.new("L", image.size, 0)
    mask.paste(glyphs, (round(spec["centre_x"] - glyphs.width / 2), spec["top"]))
    if mask.getbbox()[3] > bottom:
        raise SystemExit(f"the subtitle runs past row {bottom}")
    outline = mask.filter(ImageFilter.MaxFilter(spec["outline"]))

    # Black glyphs on a white outline: the colour is the glyph mask inverted, the alpha is
    # the outline. Where the two overlap the antialiasing greys out on its own.
    body = Image.merge(
        "RGBA",
        (
            Image.eval(mask, lambda v: 255 - v),
            Image.eval(mask, lambda v: 255 - v),
            Image.eval(mask, lambda v: 255 - v),
            outline,
        ),
    )
    image.alpha_composite(body)
    return image


def render(tid: str) -> Path:
    builder, spec = TITLES[tid]
    image = builder(spec, tid)
    asset = ROOT / "assets" / "banner" / f"{tid}_{spec['texture']}.rgba4444"
    asset.parent.mkdir(parents=True, exist_ok=True)
    asset.write_bytes(encode(image))
    flat = Image.new("RGB", image.size, (190, 190, 190))
    flat.paste(image, (0, 0), image)
    flat.save(asset.with_suffix(".png"))
    print(f"{asset.relative_to(ROOT)} ({asset.stat().st_size} bytes) - {spec['title']}")
    return asset


TITLES = {
    "0004001000022800": (plaza, PLAZA),
    "0004001000022E00": (ar_games, AR_GAMES),
}


def main(argv: list[str]) -> None:
    if not argv or (argv[0] not in TITLES and argv[0] != "--all"):
        raise SystemExit(f"usage: banner_art.py <{'|'.join(TITLES)}|--all>")
    for tid in TITLES if argv[0] == "--all" else [argv[0]]:
        render(tid)


if __name__ == "__main__":
    main(sys.argv[1:])
