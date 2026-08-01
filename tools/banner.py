"""Build a Ukrainian banner from a title's own banner and one replacement texture.

    python3 tools/banner.py 0004001000022000            # write the patched banner
    python3 tools/banner.py 0004001000022000 --extract  # dump every language texture

The banner a title ships (ExeFS:/banner, a CBMD) holds one CGFX per language, and each of
those language blocks is nothing but the title's name rendered into a 512x64 8-bit texture
called COMMON1. Nintendo fits that name into a fixed 352-pixel box centred at x=256, and
lets the height fall where it may - checked across every language slot of both banners we
dumped. assets/banner/<TID>_COMMON1.la4 follows the same rule. It is not greyscale: the format is
LA4, luminance in the high nibble and alpha in the low one - see tools/banner_text.py,
which renders it.

Only the Russian slot is touched. Every other block is copied over compressed, so the
languages the console can still switch to stay exactly as Nintendo shipped them.

The result is not installable on its own: ExeFS lives in NAND. It is read from the SD card
by the HOME Menu hook - see docs/banner-ua.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import cbmd  # noqa: E402
import cgfx  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TEXTURE = "COMMON1"

# TID -> the banner we rebuild, and the slot we overwrite.
TITLES = {
    "0004001000022000": {"title": "System Settings EUR", "slot": cbmd.EUR_RU},
}


def source_banner(tid: str) -> Path:
    return ROOT / "work" / tid / "banner"


def asset(tid: str) -> Path:
    return ROOT / "assets" / "banner" / f"{tid}_{TEXTURE}.la4"


def output(tid: str) -> Path:
    # tmp/, not dist/: the release copy is written by tools/build.py into the HOME Menu
    # folder under the name its hook opens. This one is only for looking at.
    return ROOT / "tmp" / "banner" / f"{tid}.bin"


def build(tid: str) -> bytes:
    spec = TITLES[tid]
    banner = cbmd.parse(source_banner(tid).read_bytes())
    slot = spec["slot"]

    original = banner.cgfx(slot)
    texture = cgfx.find(original, TEXTURE)
    pixels = asset(tid).read_bytes()
    if len(pixels) != texture.data_len:
        raise SystemExit(
            f"{asset(tid).name}: {len(pixels)} bytes, but {TEXTURE} is "
            f"{texture.width}x{texture.height} = {texture.data_len}"
        )

    banner.set_cgfx(slot, cgfx.replace(original, TEXTURE, pixels))

    data = cbmd.build(banner)
    # HOME Menu refuses a CGFX of 0x80000 bytes or more (.text 0x14D0AC and 0x14D0E0).
    for check in cbmd.parse(data).slots():
        size = len(cbmd.parse(data).cgfx(check))
        if size >= 0x80000:
            raise SystemExit(f"slot {check}: {size} bytes, over HOME Menu's 0x80000 limit")
    return data


def extract(tid: str) -> None:
    banner = cbmd.parse(source_banner(tid).read_bytes())
    out = ROOT / "tmp" / "banner"
    out.mkdir(parents=True, exist_ok=True)
    for slot in banner.slots():
        raw = banner.cgfx(slot)
        try:
            texture = cgfx.find(raw, TEXTURE)
        except KeyError:
            continue
        path = out / f"{tid}_slot{slot:02d}_{TEXTURE}.la4"
        path.write_bytes(cgfx.unswizzle(raw, texture))
        print(f"slot {slot:2d}: {texture.width}x{texture.height} -> {path}")


def main(argv: list[str]) -> None:
    if not argv or argv[0] not in TITLES:
        raise SystemExit(f"usage: banner.py <{'|'.join(TITLES)}> [--extract]")
    tid = argv[0]
    if "--extract" in argv:
        extract(tid)
        return
    data = build(tid)
    path = output(tid)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    original = source_banner(tid).read_bytes()
    print(f"{TITLES[tid]['title']}: {path} - {len(data)} bytes (original {len(original)})")


if __name__ == "__main__":
    main(sys.argv[1:])
