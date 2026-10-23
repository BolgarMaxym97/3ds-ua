"""Pack every build of the mod into the installer app's romfs, with a manifest it can trust.

The app ships all eight builds - two language slots x two consoles x two glyph variants
(the stand-ins `i ï ε г`, or `GLYPHS=real` for a console whose font NS now reads from SD) -
and picks one on the console. Shipped naively that is ~116 MB; the builds differ mostly in
the text of large files (the electronic manuals carry every language's pages and pictures),
so the payload is stored as:

    data/b/<n>.z   a whole file, zlib-compressed - every file of the `from-ru` default build
    data/d/<n>.d   a delta against one of those, when it is smaller than the whole file

A delta is bsdiff's three streams (tools: bsdiff4.core.diff), each zlib-compressed, so the
app needs zlib and nothing else:

    "UAD1" u32 new size, u32 control triples, u32 zctrl length, u32 zdiff length,
    u32 zextra length, then zctrl (int64 x, y, z per triple), zdiff, zextra

Every delta is applied here by apply_delta() - the same loop the app runs - and must give
back the exact file before it is kept. And the app checks the sha256 of every file it
writes against the manifest anyway, so a payload that is wrong in any way never lands.

data/manifest.txt, one record per line, fields separated by single spaces:

    3DSUA-MANIFEST 1
    version <x.y.z>
    blob <sha256> <size> z <stored name>
    blob <sha256> <size> d <stored name> <base sha256>
    need <model> <folder tid> <title tid> <remaster>   the folder ships only if the installed
                                                       title is that build (AM version >> 10)
    ns <remaster> <code sha256>                        the NS build the font patch is for
    fontpath <sd path>                                 where the built font goes
    upturn <stored name>                               tools/sysfont_glyphs.py's upturn.bin
    set <slot> <model> <glyphs> <file count>           then that many lines:
    file <sha256> <sd path>
    end

Sets: slot ru|en, model old3ds|new3ds, glyphs default|real, plus `set font any any` for the
NS patch files. SD paths are relative to the card root. Every luma/titles/<TID>/ folder of a
build also gets `locale.txt` ("EUR RU" / "EUR EN"): Luma then runs that title in the slot's
language, so the system language never has to change (docs/plan/installer-app.md, §7.1).

Usage (`make installer` runs the builds this reads first):
    python3 tools/installer_manifest.py 1.13.0
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import ns_font  # noqa: E402
from build import TITLES  # noqa: E402
from luma_hook import HOOK_PATCHES  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "dist_installer" / "romfs" / "data"

TREES = {
    ("ru", "default"): ROOT / "dist",
    ("en", "default"): ROOT / "dist_en",
    ("ru", "real"): ROOT / "dist_real",
    ("en", "real"): ROOT / "dist_en_real",
}
MODELS = ("old3ds", "new3ds")
NS_SD = ROOT / "dist_sysfont" / "sd"
UPTURN = ROOT / "dist_sysfont" / "upturn.bin"
BASE_SETS = (("ru", "old3ds", "default"), ("ru", "new3ds", "default"))

# The New 3DS titles that run out of an Old 3DS title's folder (build.write_loader_alias).
ALIAS_OF = {cfg["loader_tid"]: cfg["tids"][0] for cfg in TITLES.values() if cfg.get("loader_tid")}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def collect(tree: Path, model: str, slot: str) -> dict[str, bytes]:
    """SD path -> bytes for one build, the New 3DS overlay laid over the shared tree."""
    files: dict[str, bytes] = {}
    roots = [tree / "luma"] + ([tree / "new3ds" / "luma"] if model == "new3ds" else [])
    for root in roots:
        if not root.is_dir():
            raise SystemExit(f"{root.relative_to(ROOT)} is missing - run `make installer`, not this script alone")
        for path in sorted(root.rglob("*")):
            rel = path.relative_to(root)
            # Finder litters the trees with .DS_Store and ._ files (as in package.py).
            if path.is_file() and not any(part.startswith(".") for part in rel.parts):
                files["luma/" + rel.as_posix()] = path.read_bytes()
    folders = {p.split("/")[2] for p in files if p.startswith("luma/titles/")}
    for tid in folders:
        files[f"luma/titles/{tid}/locale.txt"] = f"EUR {slot.upper()}".encode("ascii")
    return files


def requirements(sets: dict[tuple[str, str, str], dict[str, bytes]]) -> list[str]:
    lines = set()
    for (_, model, _), files in sets.items():
        for tid in {p.split("/")[2] for p in files if p.startswith("luma/titles/")}:
            title = ALIAS_OF.get(tid, tid) if model == "new3ds" else tid
            patch = HOOK_PATCHES.get(title)
            if patch:
                lines.add(f"need {model} {tid} {title} {patch['title_version']}")
    return sorted(lines)


def make_delta(old: bytes, new: bytes) -> bytes:
    import bsdiff4.core

    control, diff, extra = bsdiff4.core.diff(old, new)
    ctrl = b"".join(struct.pack("<qqq", *triple) for triple in control)
    zctrl, zdiff, zextra = (zlib.compress(part, 9) for part in (ctrl, diff, extra))
    head = b"UAD1" + struct.pack("<IIIII", len(new), len(control), len(zctrl), len(zdiff), len(zextra))
    return head + zctrl + zdiff + zextra


def apply_delta(old: bytes, delta: bytes) -> bytes:
    """What the app does with a .d file - kept loop for loop like installer/source."""
    if delta[:4] != b"UAD1":
        raise ValueError("not a UAD1 delta")
    size, count, lc, ld, le = struct.unpack_from("<IIIII", delta, 4)
    at = 24
    ctrl = zlib.decompress(delta[at:at + lc])
    diff = zlib.decompress(delta[at + lc:at + lc + ld])
    extra = zlib.decompress(delta[at + lc + ld:at + lc + ld + le])
    new = bytearray(size)
    newpos = oldpos = di = ei = 0
    for i in range(count):
        x, y, z = struct.unpack_from("<qqq", ctrl, 24 * i)
        for k in range(x):
            o = old[oldpos + k] if 0 <= oldpos + k < len(old) else 0
            new[newpos + k] = (diff[di + k] + o) & 0xFF
        newpos, oldpos, di = newpos + x, oldpos + x, di + x
        new[newpos:newpos + y] = extra[ei:ei + y]
        newpos, ei = newpos + y, ei + y
        oldpos += z
    if newpos != size:
        raise ValueError("delta does not fill the file")
    return bytes(new)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("version")
    args = parser.parse_args()

    sets: dict[tuple[str, str, str], dict[str, bytes]] = {}
    for (slot, glyphs), tree in TREES.items():
        for model in MODELS:
            sets[(slot, model, glyphs)] = collect(tree, model, slot)

    ns_files = {
        f"luma/sysmodules/{ns_font.TID}.ips": NS_SD / "luma" / "sysmodules" / f"{ns_font.TID}.ips",
        f"luma/titles/{ns_font.TID}/exheader.bin": NS_SD / "luma" / "titles" / ns_font.TID / "exheader.bin",
    }
    for path in [*ns_files.values(), UPTURN]:
        if not path.exists():
            raise SystemExit(f"{path.relative_to(ROOT)} is missing - run `make nsfont`")
    font_set = {sd: path.read_bytes() for sd, path in ns_files.items()}

    shutil.rmtree(OUT, ignore_errors=True)
    (OUT / "b").mkdir(parents=True)
    (OUT / "d").mkdir(parents=True)
    (OUT / "font").mkdir(parents=True)

    blobs: dict[str, str] = {}  # sha -> manifest blob line
    stored = 0

    def store_full(data: bytes) -> None:
        nonlocal stored
        digest = sha(data)
        if digest in blobs:
            return
        name = f"b/{len(blobs):04d}.z"
        packed = zlib.compress(data, 9)
        (OUT / name).write_bytes(packed)
        stored += len(packed)
        blobs[digest] = f"blob {digest} {len(data)} z {name}"

    base_by_path: dict[str, list[bytes]] = {}
    for key in BASE_SETS:
        for path, data in sets[key].items():
            store_full(data)
            base_by_path.setdefault(path, []).append(data)
    for data in font_set.values():
        store_full(data)

    deltas = 0
    for key, files in sets.items():
        for path, data in files.items():
            digest = sha(data)
            if digest in blobs:
                continue
            best: tuple[int, bytes, bytes] | None = None
            for base in base_by_path.get(path, []):
                delta = make_delta(base, data)
                if apply_delta(base, delta) != data:
                    raise SystemExit(f"{path}: delta does not reproduce the file")
                if best is None or len(delta) < best[0]:
                    best = (len(delta), delta, base)
            if best and best[0] < len(zlib.compress(data, 9)):
                name = f"d/{deltas:04d}.d"
                deltas += 1
                (OUT / name).write_bytes(best[1])
                stored += best[0]
                blobs[digest] = f"blob {digest} {len(data)} d {name} {sha(best[2])}"
            else:
                store_full(data)

    shutil.copyfile(UPTURN, OUT / "font" / "upturn.bin")
    build = next(iter(ns_font.NS_BUILDS.items()))

    lines = ["3DSUA-MANIFEST 1", f"version {args.version}"]
    lines += list(blobs.values())
    lines += requirements(sets)
    lines.append(f"ns {build[1]['remaster']} {build[0]}")
    lines.append(f"fontpath {ns_font.FONT_SD_PATH}")
    lines.append("upturn font/upturn.bin")
    for (slot, model, glyphs), files in sorted(sets.items()):
        lines.append(f"set {slot} {model} {glyphs} {len(files)}")
        lines += [f"file {sha(data)} {path}" for path, data in sorted(files.items())]
    lines.append(f"set font any any {len(font_set)}")
    lines += [f"file {sha(data)} {path}" for path, data in sorted(font_set.items())]
    lines.append("end")
    for line in lines:
        if any(ch.isspace() for ch in line.split(" ", 1)[0]) or "\t" in line:
            raise SystemExit(f"manifest line with stray whitespace: {line!r}")
    (OUT / "manifest.txt").write_text("\n".join(lines) + "\n", encoding="ascii")

    raw = sum(len(d) for files in sets.values() for d in files.values())
    print(f"{OUT.relative_to(ROOT)}: {len(sets)} builds, {raw / 1e6:.1f} MB raw -> {stored / 1e6:.1f} MB stored "
          f"({len(blobs) - deltas} whole files, {deltas} deltas), {len(requirements(sets))} title requirements")


if __name__ == "__main__":
    main()
