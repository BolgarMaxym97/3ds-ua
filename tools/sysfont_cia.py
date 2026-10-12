"""Opt-in: put the patched system font into a CIA of its title, for GodMode9 to install.

The font lives in the system data archive 0004009B00014002 (JPN/EUR/USA), which LayeredFS
cannot reach (docs/internals.en.md, "How it can reach a console"). The one route that lasts
is to reinstall that title with the patched `cbf_std.bcfnt.lz` inside. This tool does the
computer's half of it and nothing else:

    in    the stock title as GodMode9's `buildcia` writes it from your console (standard,
          i.e. decrypted - the gm9/scripts/sysfont_backup.gm9 script makes it)
    in    dist_sysfont/cbf_std.bcfnt.lz (`make sysfont`)
    out   the same CIA with the font swapped: the RomFS rebuilt with its IVFC hash tree,
          the NCCH header's RomFS size and superblock hash, the TMD's content size and
          hashes. Certificates, ticket, title id and version are kept as they are.
          Next to it, `<name>.sha`: the SHA-256 the install script checks first.

Nothing is signed. The console accepts the result only through Luma3DS's signature patches,
which is also why a console that carries it must keep custom firmware - see the risks in
the docs before installing.

Usage:
    python3 tools/sysfont_cia.py build <stock.standard.cia> [--font F] [--out O]
    python3 tools/sysfont_cia.py check <file.cia>     # every hash, the font, the new letters
"""

from __future__ import annotations

import argparse
import hashlib
import struct
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import bcfnt  # noqa: E402
import lz11  # noqa: E402
import romfs  # noqa: E402
from cia import SIGNATURE_SIZES, TMD_CONTENT_COUNT, TMD_CONTENT_INFO, TMD_TITLE_ID, align  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FONT = ROOT / "dist_sysfont" / "cbf_std.bcfnt.lz"
OUTPUT = ROOT / "dist_sysfont" / "sysfont_patched.cia"

TITLE_ID = 0x0004009B00014002   # the JPN/EUR/USA shared font; CHN/KOR/TWN have their own
FONT_PATH = "/cbf_std.bcfnt.lz"
CIA_HEADER = 0x2020
SECTION = 64
IVFC_HEADER = 0x60
BLOCK_LOG = 12                  # 0x1000-byte hash blocks on every level, as Nintendo's tools
TMD_INFO_HASH = 0xA4            # SHA-256 of the 64 content info records, in the TMD body
INFO_RECORDS = 64
INFO_SIZE = 0x24
CHUNK_SIZE = 0x30
NCCH_ROMFS = 0x1B0              # offset, size, hash region size: u32 media units each
NCCH_ROMFS_HASH = 0x1E0
NCCH_FLAGS = 0x188


# ---------------------------------------------------------------- CIA


def split_cia(data: bytes) -> dict:
    header_size, _, _, cert_size, ticket_size, tmd_size, meta_size, content_size = struct.unpack_from(
        "<IHHIIIIQ", data, 0
    )
    if header_size != CIA_HEADER:
        raise SystemExit(f"CIA header size {header_size:#x}, expected {CIA_HEADER:#x} - not a CIA?")
    at = align(header_size, SECTION)
    parts = {"header": data[:header_size]}
    for name, size in (("certs", cert_size), ("ticket", ticket_size), ("tmd", tmd_size)):
        parts[name] = data[at : at + size]
        at += align(size, SECTION)
    parts["content"] = data[at : at + content_size]
    at += align(content_size, SECTION)
    parts["meta"] = data[at : at + meta_size]
    return parts


def join_cia(parts: dict) -> bytes:
    header = bytearray(parts["header"])
    struct.pack_into("<IIIIQ", header, 0x08, len(parts["certs"]), len(parts["ticket"]), len(parts["tmd"]),
                     len(parts["meta"]), len(parts["content"]))
    out = bytearray()
    for blob in (bytes(header), parts["certs"], parts["ticket"], parts["tmd"], parts["content"], parts["meta"]):
        if blob:
            out += blob + b"\0" * (-len(blob) % SECTION)
    return bytes(out)


def tmd_body(tmd: bytes) -> int:
    signature_type = struct.unpack_from(">I", tmd, 0)[0]
    if signature_type not in SIGNATURE_SIZES:
        raise SystemExit(f"unknown TMD signature type {signature_type:#x}")
    return 4 + SIGNATURE_SIZES[signature_type]


def tmd_chunks(tmd: bytes) -> list[tuple[int, int, int, int, bytes]]:
    """[(chunk offset in the TMD, content id, index, size, sha256)]"""
    body = tmd_body(tmd)
    count = struct.unpack_from(">H", tmd, body + TMD_CONTENT_COUNT)[0]
    first = body + TMD_CONTENT_INFO + INFO_RECORDS * INFO_SIZE
    out = []
    for i in range(count):
        at = first + i * CHUNK_SIZE
        content_id, index, kind, size = struct.unpack_from(">IHHQ", tmd, at)
        if kind & 1:
            raise SystemExit("the content is encrypted - build the stock CIA as `standard`, not `legit`")
        out.append((at, content_id, index, size, tmd[at + 0x10 : at + 0x30]))
    return out


def rehash_tmd(tmd: bytes, sizes_hashes: list[tuple[int, bytes]]) -> bytes:
    """New sizes and hashes for the content chunks, then the two hash levels above them."""
    out = bytearray(tmd)
    body = tmd_body(tmd)
    for (at, *_), (size, digest) in zip(tmd_chunks(tmd), sizes_hashes):
        struct.pack_into(">Q", out, at + 8, size)
        out[at + 0x10 : at + 0x30] = digest
    infos = body + TMD_CONTENT_INFO
    chunks = infos + INFO_RECORDS * INFO_SIZE
    for i in range(INFO_RECORDS):
        at = infos + i * INFO_SIZE
        first, count = struct.unpack_from(">HH", out, at)
        if count:
            out[at + 4 : at + 0x24] = hashlib.sha256(
                out[chunks + first * CHUNK_SIZE : chunks + (first + count) * CHUNK_SIZE]
            ).digest()
    out[body + TMD_INFO_HASH : body + TMD_INFO_HASH + 0x20] = hashlib.sha256(
        out[infos : infos + INFO_RECORDS * INFO_SIZE]
    ).digest()
    return bytes(out)


def check_tmd(tmd: bytes, contents: list[bytes]) -> None:
    body = tmd_body(tmd)
    infos = body + TMD_CONTENT_INFO
    if hashlib.sha256(tmd[infos : infos + INFO_RECORDS * INFO_SIZE]).digest() != tmd[body + TMD_INFO_HASH : body + TMD_INFO_HASH + 0x20]:
        raise SystemExit("TMD: content info hash does not match")
    if rehash_tmd(tmd, [(len(c), hashlib.sha256(c).digest()) for c in contents]) != tmd:
        raise SystemExit("TMD: a content size or hash does not match")


# ---------------------------------------------------------------- IVFC / RomFS


def ivfc_build(level3: bytes) -> bytes:
    """The IVFC-wrapped RomFS: header, master hash, level 3, level 1, level 2 (GodMode9's order)."""
    block = 1 << BLOCK_LOG

    def hashes(data: bytes) -> bytes:
        padded = data + b"\0" * (-len(data) % block)
        return b"".join(hashlib.sha256(padded[i : i + block]).digest() for i in range(0, len(padded), block))

    level2 = hashes(level3)
    level1 = hashes(level2)
    master = hashes(level1)
    logical2 = align(len(level1), block)
    logical3 = logical2 + align(len(level2), block)
    header = b"IVFC" + struct.pack(
        "<II" + "QQII" * 3 + "II",
        0x10000, len(master),
        0, len(level1), BLOCK_LOG, 0,
        logical2, len(level2), BLOCK_LOG, 0,
        logical3, len(level3), BLOCK_LOG, 0,
        0x5C, 0,
    )
    out = bytearray(header + b"\0" * (IVFC_HEADER - len(header)) + master)  # 0x5C, padded to 0x60
    out += b"\0" * (align(len(out), block) - len(out))
    for level in (level3, level1, level2):
        out += level + b"\0" * (-len(level) % block)
    return bytes(out)


def ivfc_check(image: bytes) -> bytes:
    """Verify every hash level; return level 3."""
    if image[:4] != b"IVFC":
        raise SystemExit("RomFS: no IVFC header")
    master_size = struct.unpack_from("<I", image, 8)[0]
    levels = [struct.unpack_from("<QQI", image, 0x0C + i * 0x18) for i in range(3)]
    sizes = [size for _, size, _ in levels]
    logs = [log for _, _, log in levels]
    at3 = align(IVFC_HEADER + master_size, 1 << logs[2])
    at1 = at3 + align(sizes[2], 1 << logs[2])
    at2 = at1 + align(sizes[0], 1 << logs[0])
    data = {1: image[at1 : at1 + sizes[0]], 2: image[at2 : at2 + sizes[1]], 3: image[at3 : at3 + sizes[2]]}
    above = {1: image[IVFC_HEADER : IVFC_HEADER + master_size], 2: data[1], 3: data[2]}
    for level in (1, 2, 3):
        block = 1 << logs[level - 1]
        padded = data[level] + b"\0" * (-len(data[level]) % block)
        for i in range(0, len(padded), block):
            expected = above[level][i // block * 0x20 : i // block * 0x20 + 0x20]
            if hashlib.sha256(padded[i : i + block]).digest() != expected:
                raise SystemExit(f"RomFS: level {level} block {i // block} does not match its hash")
    return data[3]


# ---------------------------------------------------------------- NCCH


def ncch_romfs(ncch: bytes) -> tuple[int, bytes]:
    if ncch[0x100:0x104] != b"NCCH":
        raise SystemExit("content 0 is not an NCCH - build the stock CIA as `standard`")
    if not ncch[NCCH_FLAGS + 7] & 0x04:
        raise SystemExit("the NCCH is encrypted - build the stock CIA as `standard`, not `legit`")
    unit = 0x200 << ncch[NCCH_FLAGS + 6]
    offset, size, hashed = struct.unpack_from("<III", ncch, NCCH_ROMFS)
    image = ncch[offset * unit : (offset + size) * unit]
    if hashlib.sha256(image[: hashed * unit]).digest() != ncch[NCCH_ROMFS_HASH : NCCH_ROMFS_HASH + 0x20]:
        raise SystemExit("NCCH: RomFS superblock hash does not match")
    return unit, image


def replace_romfs(ncch: bytes, image: bytes) -> bytes:
    unit = 0x200 << ncch[NCCH_FLAGS + 6]
    offset = struct.unpack_from("<I", ncch, NCCH_ROMFS)[0]
    master_size = struct.unpack_from("<I", image, 8)[0]
    hashed = align(IVFC_HEADER + master_size, unit) // unit
    image = image + b"\0" * (-len(image) % unit)
    out = bytearray(ncch[: offset * unit])
    struct.pack_into("<I", out, 0x104, offset + len(image) // unit)   # content size
    struct.pack_into("<III", out, NCCH_ROMFS, offset, len(image) // unit, hashed)
    out[NCCH_ROMFS_HASH : NCCH_ROMFS_HASH + 0x20] = hashlib.sha256(image[: hashed * unit]).digest()
    return bytes(out) + image


def romfs_with(level3: bytes, path: str, blob: bytes) -> bytes:
    files = romfs.read(level3)
    if path not in files:
        raise SystemExit(f"{path} is not in this title's RomFS - is it {TITLE_ID:016X}?")
    files[path] = blob
    with tempfile.TemporaryDirectory() as tmp:
        for name, data in files.items():
            target = Path(tmp) / name.lstrip("/")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        return romfs.build(Path(tmp))


# ---------------------------------------------------------------- commands


def title_of(parts: dict) -> int:
    tmd = parts["tmd"]
    return struct.unpack_from(">Q", tmd, tmd_body(tmd) + TMD_TITLE_ID)[0]


def contents_of(parts: dict) -> list[bytes]:
    out, at = [], 0
    for _, _, _, size, _ in tmd_chunks(parts["tmd"]):
        out.append(parts["content"][at : at + size])
        at += size  # back to back, as tools/cia.py reads them; NCCH sizes are whole media units
    return out


def build(stock: Path, font: Path, out: Path) -> None:
    parts = split_cia(stock.read_bytes())
    if title_of(parts) != TITLE_ID:
        raise SystemExit(f"title {title_of(parts):016X}, expected {TITLE_ID:016X}")
    contents = contents_of(parts)
    check_tmd(parts["tmd"], contents)
    if len(contents) != 1:
        raise SystemExit(f"{len(contents)} contents, expected 1")

    _, image = ncch_romfs(contents[0])
    new_font = font.read_bytes()
    bcfnt.parse(lz11.decompress(new_font))  # refuse anything that is not a font
    level3 = romfs_with(ivfc_check(image), FONT_PATH, new_font)
    ncch = replace_romfs(contents[0], ivfc_build(level3))

    parts["content"] = ncch
    parts["tmd"] = rehash_tmd(parts["tmd"], [(len(ncch), hashlib.sha256(ncch).digest())])
    data = join_cia(parts)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    digest = hashlib.sha256(data).digest()
    out.with_name(out.name + ".sha").write_bytes(digest)
    print(f"-> {out} ({len(data)} bytes, sha256 {digest.hex()})")
    check(out)


def check(path: Path) -> None:
    parts = split_cia(path.read_bytes())
    contents = contents_of(parts)
    check_tmd(parts["tmd"], contents)
    _, image = ncch_romfs(contents[0])
    files = romfs.read(ivfc_check(image))
    font = bcfnt.parse(lz11.decompress(files[FONT_PATH]))
    size = len(bcfnt.build(font))
    letters = [code for code in (0x0456, 0x0406, 0x0457, 0x0407, 0x0454, 0x0404, 0x0491, 0x0490, 0x02BC) if code in font.cmap]
    print(f"{path.name}: title {title_of(parts):016X}, TMD and content hashes ok, IVFC ok, NCCH superblock ok; "
          f"font {size} bytes, {len(font.cmap)} code points, {len(letters)}/9 Ukrainian additions")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build")
    b.add_argument("stock", type=Path)
    b.add_argument("--font", type=Path, default=FONT)
    b.add_argument("--out", type=Path, default=OUTPUT)
    c = sub.add_parser("check")
    c.add_argument("cia", type=Path)
    args = parser.parse_args()
    if args.command == "build":
        build(args.stock, args.font, args.out)
    else:
        check(args.cia)


if __name__ == "__main__":
    main()
