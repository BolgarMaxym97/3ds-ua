"""Turn the project's screenshots into what Universal-DB asks for.

    python3 tools/udb_screenshots.py        # -> unistore/screenshots/*.png

Universal-DB wants "400x480; no screen gap, 1x resolution, ideally with the left and right of
the bottom screen cut out to transparency" (their App-Template wiki), dropped into
docs/assets/images/screenshots/<slug>/ of a pull request against Universal-Team/db.

The pictures in assets/pictures/ are already almost that: a 400x240 top screen, ten fully
transparent rows, then the 320x240 bottom screen centred with transparent side margins - so
the only thing to do is drop the gap. The gap is verified rather than assumed: a file whose
rows 240-249 are not fully transparent is reported and skipped, because silently cutting ten
rows out of the middle of a picture would be worse than not converting it.

Stdlib only, like the rest of the build - the PNG writer is the one from tools/unistore_icon.py.
"""

from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from unistore_icon import write_png  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "assets" / "pictures"
OUT = ROOT / "unistore" / "screenshots"

WIDTH, TOP_HEIGHT, BOTTOM_HEIGHT = 400, 240, 240
GAP = 10
SOURCE_HEIGHT = TOP_HEIGHT + GAP + BOTTOM_HEIGHT      # 490


def read_png(path: Path) -> tuple[int, int, list[list[tuple[int, int, int, int]]]]:
    """Just enough PNG: 8-bit, non-interlaced, RGB/RGBA/grey/palette."""
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise SystemExit(f"{path.name} is not a PNG")

    pos, idat, palette = 8, b"", None
    width = height = colour_type = 0
    while pos < len(data):
        length, tag = struct.unpack(">I4s", data[pos:pos + 8])
        chunk = data[pos + 8:pos + 8 + length]
        if tag == b"IHDR":
            width, height, depth, colour_type, _, _, interlace = struct.unpack(">IIBBBBB", chunk)
            if depth != 8 or interlace:
                raise SystemExit(f"{path.name}: only 8-bit non-interlaced PNGs are handled")
        elif tag == b"IDAT":
            idat += chunk
        elif tag == b"PLTE":
            palette = chunk
        elif tag == b"IEND":
            break
        pos += 12 + length

    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[colour_type]
    raw = zlib.decompress(idat)
    stride = width * channels

    rows, previous, offset = [], bytearray(stride), 0
    for _ in range(height):
        filter_type = raw[offset]
        offset += 1
        line = bytearray(raw[offset:offset + stride])
        offset += stride
        for x in range(stride):
            left = line[x - channels] if x >= channels else 0
            up = previous[x]
            up_left = previous[x - channels] if x >= channels else 0
            if filter_type == 1:
                line[x] = (line[x] + left) & 0xFF
            elif filter_type == 2:
                line[x] = (line[x] + up) & 0xFF
            elif filter_type == 3:
                line[x] = (line[x] + (left + up) // 2) & 0xFF
            elif filter_type == 4:
                estimate = left + up - up_left
                da, db, dc = abs(estimate - left), abs(estimate - up), abs(estimate - up_left)
                nearest = left if (da <= db and da <= dc) else (up if db <= dc else up_left)
                line[x] = (line[x] + nearest) & 0xFF

        row = []
        for x in range(width):
            pixel = line[x * channels:(x + 1) * channels]
            if colour_type == 3:
                i = pixel[0] * 3
                row.append((palette[i], palette[i + 1], palette[i + 2], 255))
            elif colour_type == 0:
                row.append((pixel[0],) * 3 + (255,))
            elif colour_type == 4:
                row.append((pixel[0],) * 3 + (pixel[1],))
            elif colour_type == 2:
                row.append((pixel[0], pixel[1], pixel[2], 255))
            else:
                row.append(tuple(pixel))
        rows.append(row)
        previous = line
    return width, height, rows


def main() -> int:
    sources = sorted(SOURCE.glob("*.png"))
    if not sources:
        raise SystemExit(f"no PNGs in {SOURCE.relative_to(ROOT)}")

    OUT.mkdir(parents=True, exist_ok=True)
    written = skipped = 0
    for path in sources:
        width, height, rows = read_png(path)
        if (width, height) != (WIDTH, SOURCE_HEIGHT):
            print(f"  skip {path.name}: {width}x{height}, not a both-screens shot")
            skipped += 1
            continue

        gap = rows[TOP_HEIGHT:TOP_HEIGHT + GAP]
        if any(pixel[3] != 0 for row in gap for pixel in row):
            print(f"  skip {path.name}: rows {TOP_HEIGHT}-{TOP_HEIGHT + GAP - 1} are not the "
                  f"transparent gap - cutting them would take out part of the picture")
            skipped += 1
            continue

        out = rows[:TOP_HEIGHT] + rows[TOP_HEIGHT + GAP:]
        target = OUT / path.name
        write_png(target, out)
        print(f"  {path.name}: {width}x{height} -> {WIDTH}x{len(out)}, "
              f"{target.stat().st_size} bytes")
        written += 1

    print(f"{OUT.relative_to(ROOT)}: {written} written, {skipped} skipped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
