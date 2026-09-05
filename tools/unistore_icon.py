"""Draw the 48x48 icon Universal-Updater shows next to the entry.

    python3 tools/unistore_icon.py --force     # -> assets/unistore-icon.png

Universal-Updater accepts an icon of up to 48x48 (`Store::GetIconValid`, store.cpp:361) and
falls back to its own "no icon" sprite for anything larger. It reads icons only out of the
`.t3x` sheet, never as PNG, so this file is just the source `make unistore-icon` feeds to
tex3ds.

The drawing is a flat clamshell 3DS with the Ukrainian flag on its top screen - the mod in
one picture. Shapes are laid out in the 512x512 space of the reference art and rasterised at
4x before being box-filtered down, which is all the antialiasing flat colour needs.

Written with the standard library alone, like the rest of the build: Pillow is optional here
(tools/banner_art.py needs it, the build does not), and an icon that only some machines can
regenerate is an icon that rots.

Replacing the art: drop your own PNG at assets/unistore-icon.png - anything up to 48x48 -
and run `make unistore-icon`. This script is only what produces the default.
"""

from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "unistore-icon.png"

SIZE = 48
SCALE = 4
W = SIZE * SCALE
REFERENCE = 512.0                      # the coordinate space the layout below is written in
K = W / REFERENCE

CLEAR = (0, 0, 0, 0)
BODY = (114, 114, 114, 255)
SCREEN = (65, 82, 92, 255)
BUTTON = (165, 210, 110, 255)
PAD = (196, 196, 196, 255)
BLUE = (0, 87, 183, 255)
YELLOW = (255, 215, 0, 255)


def rect(pixels, x0, y0, x1, y1, colour, radius=0.0) -> None:
    """A rectangle, optionally with rounded corners, in reference coordinates."""
    px0, py0, px1, py1 = x0 * K, y0 * K, x1 * K, y1 * K
    r = radius * K
    for y in range(max(0, int(py0)), min(W, int(py1) + 1)):
        cy = y + 0.5
        for x in range(max(0, int(px0)), min(W, int(px1) + 1)):
            cx = x + 0.5
            if not (px0 <= cx <= px1 and py0 <= cy <= py1):
                continue
            if r > 0:
                # Outside the corner quarter-circles is outside the shape.
                nx = min(max(cx, px0 + r), px1 - r)
                ny = min(max(cy, py0 + r), py1 - r)
                if (cx - nx) ** 2 + (cy - ny) ** 2 > r * r:
                    continue
            pixels[y][x] = colour


def circle(pixels, cx, cy, radius, colour) -> None:
    pcx, pcy, r = cx * K, cy * K, radius * K
    for y in range(max(0, int(pcy - r)), min(W, int(pcy + r) + 1)):
        for x in range(max(0, int(pcx - r)), min(W, int(pcx + r) + 1)):
            if (x + 0.5 - pcx) ** 2 + (y + 0.5 - pcy) ** 2 <= r * r:
                pixels[y][x] = colour


def draw() -> list[list[tuple[int, int, int, int]]]:
    pixels = [[CLEAR for _ in range(W)] for _ in range(W)]

    # Upper shell. Its screen is the flag, edge to edge - the mod in one picture, and at 48
    # pixels a full field of colour survives where a small badge would not.
    rect(pixels, 64, 28, 460, 248, BODY, radius=44)
    rect(pixels, 118, 62, 408, 138, BLUE)
    rect(pixels, 118, 138, 408, 214, YELLOW)

    # The hinge bar sits between the shells, so it is drawn before the lower one and the
    # lower one starts below it - otherwise it is simply painted over and disappears.
    rect(pixels, 140, 240, 386, 268, SCREEN)
    rect(pixels, 64, 262, 460, 492, BODY, radius=44)
    rect(pixels, 180, 292, 344, 452, SCREEN)

    # Circle pad, D-pad, face buttons. The cross needs long thin arms: at 48 pixels a fat
    # one collapses into a blob.
    circle(pixels, 122, 318, 26, PAD)
    rect(pixels, 76, 388, 168, 420, BUTTON)
    rect(pixels, 106, 358, 138, 450, BUTTON)
    for dx, dy in ((0, -40), (0, 40), (-40, 0), (40, 0)):
        circle(pixels, 402 + dx, 356 + dy, 17, BUTTON)

    out = []
    for y in range(SIZE):
        row = []
        for x in range(SIZE):
            acc = [0, 0, 0, 0]
            for dy in range(SCALE):
                source = pixels[y * SCALE + dy]
                for dx in range(SCALE):
                    r, g, b, a = source[x * SCALE + dx]
                    # Premultiply, so transparent pixels do not drag colour into the edges.
                    acc[0] += r * a; acc[1] += g * a; acc[2] += b * a; acc[3] += a
            alpha = acc[3]
            if alpha == 0:
                row.append(CLEAR)
            else:
                row.append((acc[0] // alpha, acc[1] // alpha, acc[2] // alpha,
                            alpha // (SCALE * SCALE)))
        out.append(row)
    return out


def write_png(path: Path, pixels) -> None:
    raw = bytearray()
    for row in pixels:
        raw.append(0)
        for r, g, b, a in row:
            raw += bytes((r, g, b, a))

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", len(pixels[0]), len(pixels), 8, 6, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


def main() -> int:
    if OUT.exists() and "--force" not in sys.argv:
        print(f"{OUT.relative_to(ROOT)} already exists - pass --force to redraw it")
        return 0
    write_png(OUT, draw())
    print(f"{OUT.relative_to(ROOT)}: {SIZE}x{SIZE}, {OUT.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
