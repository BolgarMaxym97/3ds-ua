"""The installer's splash screen: makerom's homebrew logo, in the colours of the flag.

The splash a CIA shows while it starts is a small LZ11 DARC of layouts, animations and four
ETC1 textures, followed by an HMAC-SHA256 of the archive that the HOME Menu checks - with a
key of its own (yellows8/ctr-logobuilder; GBAtemp "Create your own app logo"). A logo whose
HMAC does not match takes the HOME Menu down (svcBreak, Old 3DS 2026-10-22).

This keeps makerom's homebrew logo - layouts and animations - and swaps two textures of the
same size and format, so nothing else in the archive moves:

    timg/waves.bclim  the animated wave behind both screens: blue above, yellow below,
                      the wave line lowered so the name sits on the blue
    timg/logo.bclim   the word over it: "Українізатор 3DS" instead of "homebrew"

then signs it again. The key is not in this repository: it is read from the console's own
HOME Menu code (work/0004003000009802/code.bin, from `make extract`), found by its SHA-256
and checked against the stock logo's HMAC before use. No dump - no custom splash (the
Makefile falls back to the stock logo).

The logo is drawn additively (black is see-through, white stays white), so the name is
white on black. ETC1 is encoded by devkitARM's tex3ds (3DS tiling), between the two steps:

    python3 tools/installer_logo.py render <cia built with the stock logo> <font> <dir>
    tex3ds -f etc1 -q high -z none -r -o <dir>/waves.etc1 <dir>/waves.png   (and logo)
    python3 tools/installer_logo.py pack <dir> <HOME Menu code.bin>   -> <dir>/logo.bcma.lz
"""

from __future__ import annotations

import hashlib
import hmac
import struct
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
import darc  # noqa: E402
import lz11  # noqa: E402

BLUE = (0x14, 0x58, 0xC7)
YELLOW = (0xF5, 0xC4, 0x00)
CREST = (0xFF, 0xE2, 0x6A)  # the wave line
TEXTURES = {"waves": "./timg/waves.bclim", "logo": "./timg/logo.bclim"}
LOGO_SIZE = (225, 40)  # the drawn part of logo.bclim; the texture is 256x64
WAVE_LEVEL = 0.86  # where the wave line sits, as a share of the texture's height
LOGO_MAX = 0x2000  # the logo region: the file is always exactly this long, zero-padded
MAC_SIZE = 32
# SHA-256 of the HOME Menu's logo HMAC key (public, ctr-logobuilder / GBAtemp tutorial)
KEY_SHA256 = bytes.fromhex("001ECEFBF56F3614A21532391A7E303CC62A054F5C7BBBF92A97F9C62443AD15")


def cia_logo(cia: bytes) -> bytes:
    """The ExeFS `logo` of the first content of a CIA built with -exefslogo."""
    header, _, _, cert, ticket, tmd = struct.unpack_from("<IHHIII", cia, 0)
    align = lambda x: (x + 63) // 64 * 64  # noqa: E731
    ncch = cia[align(header) + align(cert) + align(ticket) + align(tmd) :]
    if ncch[0x100:0x104] != b"NCCH":
        raise SystemExit("not a CIA with an NCCH first content")
    exefs = ncch[struct.unpack_from("<I", ncch, 0x1A0)[0] * 0x200 :]
    for i in range(10):
        name, offset, size = struct.unpack_from("<8sII", exefs, i * 16)
        if name.rstrip(b"\0") == b"logo":
            return exefs[0x200 + offset : 0x200 + offset + size]
    raise SystemExit("the CIA has no ExeFS logo (build it with -exefslogo)")


def find_key(code: bytes, stock: bytes) -> bytes:
    """The HMAC key in the HOME Menu code, proven on the stock logo's own HMAC."""
    body, mac = stock[:-MAC_SIZE], stock[-MAC_SIZE:]
    for i in range(len(code) - MAC_SIZE):
        key = code[i : i + MAC_SIZE]
        if hashlib.sha256(key).digest() == KEY_SHA256:
            if hmac.new(key, body, hashlib.sha256).digest() != mac:
                raise SystemExit("the HOME Menu key does not sign the stock logo")
            return key
    raise SystemExit("no logo key in this HOME Menu code")


# ETC1 (as the 3DS lays it out), decode only: enough to find the wave line in the original.
_TABLES = [(2, 8), (5, 17), (9, 29), (13, 42), (18, 60), (24, 80), (33, 106), (47, 183)]


def _etc1_block(block: bytes) -> list[list[tuple[int, int, int]]]:
    value = struct.unpack("<Q", block)[0]
    hi, lo = value >> 32, value & 0xFFFFFFFF
    flip, table1, table2 = hi & 1, (hi >> 5) & 7, (hi >> 2) & 7
    if (hi >> 1) & 1:
        five = lambda v: (v << 3) | (v >> 2)  # noqa: E731
        signed = lambda v: v - 8 if v > 3 else v  # noqa: E731
        r, g, b = (hi >> 27) & 31, (hi >> 19) & 31, (hi >> 11) & 31
        dr, dg, db = signed((hi >> 24) & 7), signed((hi >> 16) & 7), signed((hi >> 8) & 7)
        base1, base2 = (five(r), five(g), five(b)), (five(r + dr), five(g + dg), five(b + db))
    else:
        four = lambda v: (v << 4) | v  # noqa: E731
        base1 = tuple(four((hi >> s) & 15) for s in (28, 20, 12))
        base2 = tuple(four((hi >> s) & 15) for s in (24, 16, 8))
    out = [[(0, 0, 0)] * 4 for _ in range(4)]
    for x in range(4):
        for y in range(4):
            i = x * 4 + y
            second = (y >= 2) if flip else (x >= 2)
            near, far = _TABLES[table2 if second else table1]
            mod = (near, far, -near, -far)[((lo >> (16 + i)) & 1) << 1 | ((lo >> i) & 1)]
            out[y][x] = tuple(max(0, min(255, c + mod)) for c in (base2 if second else base1))
    return out


def etc1_decode(data: bytes, width: int, height: int) -> Image.Image:
    im = Image.new("RGB", (width, height))
    px = im.load()
    pos = 0
    for ty in range(0, height, 8):
        for tx in range(0, width, 8):
            for b in range(4):
                bx, by = tx + (b & 1) * 4, ty + (b >> 1) * 4
                block = _etc1_block(data[pos : pos + 8])
                pos += 8
                for y in range(4):
                    for x in range(4):
                        px[bx + x, by + y] = block[y][x]
    return im


def waves(original: Image.Image) -> Image.Image:
    """The stock wave's line, column by column (its brightest pixel), flattened, lowered,
    recoloured."""
    w, h = original.size
    px = original.load()
    out = Image.new("RGB", (w, h), BLUE)
    draw = ImageDraw.Draw(out)
    lines = [max(range(h), key=lambda y: sum(px[x, y])) for x in range(w)]
    mean = sum(lines) / w
    for x in range(w):
        # a third of the swell, low: the name on the screen's middle row should stay on the
        # blue while the animation lifts the wave. Never off the texture's bottom: the layout
        # stretches a narrow band of rows over the screens, and a column with no yellow left
        # in it shows as a blue stripe from top to bottom (at 0.95, console video 2026-10-22).
        line = min(h - 4, round(h * WAVE_LEVEL + (lines[x] - mean) / 3))
        draw.line([(x, line + 1), (x, h)], fill=YELLOW)
        draw.line([(x, line - 1), (x, line + 1)], fill=CREST)
    return out


def logo(font: Path) -> Image.Image:
    out = Image.new("RGB", (256, 64), (0, 0, 0))
    draw = ImageDraw.Draw(out)
    text, (w, h) = "Українізатор 3DS", LOGO_SIZE
    size = 40
    while True:
        face = ImageFont.truetype(str(font), size)
        left, top, right, bottom = draw.textbbox((0, 0), text, font=face)
        if right - left <= w - 4 and bottom - top <= h - 8:
            break
        size -= 1
    draw.text(((w - (right - left)) / 2 - left, (h - (bottom - top)) / 2 - top), text, font=face, fill=(255, 255, 255))
    return out


def render(cia: Path, font: Path, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    archive = lz11.decompress(cia_logo(cia.read_bytes()))
    (out / "stock_logo.darc").write_bytes(archive)
    stock = darc.parse(archive).find(TEXTURES["waves"]).data
    waves(etc1_decode(stock, 256, 64)).save(out / "waves.png")
    logo(font).save(out / "logo.png")
    print(f"{out}: waves.png, logo.png - encode them with tex3ds, then `pack`")


def pack(out: Path, home_code: Path) -> None:
    stock = (out / "stock_logo.darc").read_bytes()
    key = find_key(home_code.read_bytes(), stock)
    archive = darc.parse(stock)
    swaps = {}
    for name, path in TEXTURES.items():
        old = archive.find(path).data
        etc1 = (out / f"{name}.etc1").read_bytes()
        footer = old[-0x28:]
        if etc1[0] == 0x00 and len(etc1) == len(old) - len(footer) + 4:
            etc1 = etc1[4:]  # tex3ds -z none keeps its 4-byte "uncompressed" header
        if len(etc1) != len(old) - len(footer):
            raise SystemExit(f"{name}.etc1: {len(etc1)} bytes, the stock texture has {len(old) - len(footer)}")
        swaps[path] = etc1 + footer  # same size and format: the stock CLIM header still holds
    body = darc.splice(stock, archive, swaps)[:-MAC_SIZE]
    signed = body + hmac.new(key, body, hashlib.sha256).digest()
    packed = lz11.compress(signed)
    if len(packed) > LOGO_MAX:
        raise SystemExit(f"logo is {len(packed)} bytes compressed, over the {LOGO_MAX}-byte logo region")
    (out / "logo.bcma.lz").write_bytes(packed.ljust(LOGO_MAX, b"\0"))
    print(f"{out}/logo.bcma.lz: {len(packed)} bytes, signed")


def main() -> None:
    if sys.argv[1:2] == ["render"] and len(sys.argv) == 5:
        render(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]))
    elif sys.argv[1:2] == ["pack"] and len(sys.argv) == 4:
        pack(Path(sys.argv[2]), Path(sys.argv[3]))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
