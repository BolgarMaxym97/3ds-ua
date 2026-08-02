"""Build a Ukrainian banner from a title's own banner and one replacement texture.

    python3 tools/banner.py 0004001000022000            # write the patched banner
    python3 tools/banner.py 0004001000022000 --extract  # dump every language texture

The banner a title ships (ExeFS:/banner, a CBMD) holds one CGFX per language, and each of
those language blocks carries the localised part of the picture in a single texture - the
title set as type in most of them, the whole logotype in StreetPass Mii Plaza. Where that
texture sits and how it is laid out is per title; docs/banner-ua.md has the measurements.

The replacement pixels come from assets/banner/<TID>_<texture>.<format>, written by
tools/banner_text.py where the texture is type, and tools/banner_art.py where it is a
drawing derived from the title's own art. Two formats appear, one byte per pixel for LA4
and two for RGBA4444; the file extension says which.

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

# TID -> the banner we rebuild, the slot we overwrite, and the texture inside it that
# carries the localised part of the picture. No two banners agree on it: the name is
# COMMON1 in most and TEX1 in the Activity Log, the size is 512x64 or 512x128, and the
# format is LA4 in the ones set as type and RGBA4444 in the two that are drawings.
TITLES = {
    "0004001000022000": {
        "title": "System Settings EUR",
        "slot": cbmd.EUR_RU,
        "texture": "COMMON1",
    },
    "0004001000022100": {
        "title": "Download Play EUR",
        "slot": cbmd.EUR_RU,
        "texture": "COMMON1",
    },
    "0004001000022200": {
        "title": "Activity Log EUR",
        "slot": cbmd.EUR_RU,
        "texture": "TEX1",
    },
    "0004001000022300": {
        "title": "Health & Safety Information EUR",
        "slot": cbmd.EUR_RU,
        "texture": "COMMON1",
    },
    "0004001000022800": {
        "title": "StreetPass Mii Plaza EUR",
        "slot": cbmd.EUR_RU,
        "texture": "COMMON1",
    },
    "0004001000022E00": {
        "title": "AR Games EUR",
        "slot": cbmd.EUR_RU,
        "texture": "COMMON1",
    },
}

# The extension the replacement pixels are stored under, per PICA pixel format.
EXTENSIONS = {cgfx.FORMAT_LA4: "la4", cgfx.FORMAT_RGBA4444: "rgba4444"}


def source_banner(tid: str) -> Path:
    return ROOT / "work" / tid / "banner"


def asset(tid: str, texture: cgfx.Texture) -> Path:
    suffix = EXTENSIONS.get(texture.pica_format)
    if suffix is None:
        raise SystemExit(f"{tid}: {texture.name} is PICA format {texture.pica_format}")
    return ROOT / "assets" / "banner" / f"{tid}_{texture.name}.{suffix}"


def output(tid: str) -> Path:
    # tmp/, not dist/: the release copy is written by tools/build.py into the HOME Menu
    # folder under the name its hook opens. This one is only for looking at.
    return ROOT / "tmp" / "banner" / f"{tid}.bin"


def build(tid: str) -> bytes:
    spec = TITLES[tid]
    banner = cbmd.parse(source_banner(tid).read_bytes())
    slot = spec["slot"]

    original = banner.cgfx(slot)
    texture = cgfx.find(original, spec["texture"])
    path = asset(tid, texture)
    pixels = path.read_bytes()
    if len(pixels) != texture.data_len:
        raise SystemExit(
            f"{path.name}: {len(pixels)} bytes, but {spec['texture']} is "
            f"{texture.width}x{texture.height}x{texture.pixel_size} = {texture.data_len}"
        )

    banner.set_cgfx(slot, cgfx.replace(original, spec["texture"], pixels))

    data = cbmd.build(banner)
    # HOME Menu refuses a CGFX of 0x80000 bytes or more (.text 0x14D0AC and 0x14D0E0).
    for check in cbmd.parse(data).slots():
        size = len(cbmd.parse(data).cgfx(check))
        if size >= 0x80000:
            raise SystemExit(f"slot {check}: {size} bytes, over HOME Menu's 0x80000 limit")
    return data


def extract(tid: str) -> None:
    texture_name = TITLES[tid]["texture"]
    banner = cbmd.parse(source_banner(tid).read_bytes())
    out = ROOT / "tmp" / "banner"
    out.mkdir(parents=True, exist_ok=True)
    for slot in banner.slots():
        raw = banner.cgfx(slot)
        try:
            texture = cgfx.find(raw, texture_name)
        except KeyError:
            continue
        suffix = EXTENSIONS.get(texture.pica_format, f"fmt{texture.pica_format}")
        path = out / f"{tid}_slot{slot:02d}_{texture_name}.{suffix}"
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
