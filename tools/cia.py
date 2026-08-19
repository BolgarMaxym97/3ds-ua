"""Unpack a CIA the way GodMode9 would have unpacked the title it was built from.

A console owner who cannot follow the whole mount-and-copy walk of docs/dumping.md can
send a CIA instead: GodMode9's `Build CIA (standard)` writes one decrypted file holding
every part a dump needs. This turns that file back into the work/<TID>/ layout the rest of
the tools expect:

    work/<TID>/code.bin          ExeFS:/.code, BLZ-unpacked when the exheader says it is
    work/<TID>/exheader.bin      exheader + access descriptor, as GodMode9 writes it
    work/<TID>/banner            ExeFS:/banner, the picture HOME Menu draws
    work/<TID>/icon              ExeFS:/icon, the SMDH the names come from
    work/<TID>/romfs/...         the RomFS tree of content 0
    work/<TID>/manual/Manual.bcma   content 1, the electronic manual

Usage:
    python3 tools/cia.py cia/*.cia            # unpack into work/
    python3 tools/cia.py --list cia/x.cia     # only report what is inside

The contents are checked against the hashes in the TMD, which is also what tells an
encrypted CIA apart: a retail `Build CIA (encrypted)` fails the check and has no readable
NCCH header, and there is nothing this script can do with it - ask for the standard one.
"""

from __future__ import annotations

import argparse
import hashlib
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import romfs  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

SECTION_ALIGN = 64          # every CIA section starts on a 64-byte boundary
MEDIA_UNIT = 0x200          # NCCH offsets and sizes are counted in these
EXHEADER_SIZE = 0x800       # 0x400 of exheader plus the 0x400 access descriptor
EXEFS_HEADER_SIZE = 0x200
EXEFS_ENTRIES = 10
# Signature length per type, without the 4-byte type word itself: RSA-4096, RSA-2048 and
# ECDSA, each followed by the padding that puts the body on a 0x40 boundary.
SIGNATURE_SIZES = {
    0x010000: 0x200 + 0x3C, 0x010003: 0x200 + 0x3C,
    0x010001: 0x100 + 0x3C, 0x010004: 0x100 + 0x3C,
    0x010002: 0x03C + 0x40, 0x010005: 0x03C + 0x40,
}
TMD_TITLE_ID = 0x4C         # offsets inside the TMD body
TMD_TITLE_VERSION = 0x9C
TMD_CONTENT_COUNT = 0x9E
TMD_CONTENT_INFO = 0xC4
TMD_CONTENT_INFO_SIZE = 64 * 0x24
TMD_CHUNK_SIZE = 0x30

# The names ExeFS sections keep on disk. Anything else is written as <name>.bin.
EXEFS_AS_IS = ("banner", "icon", "logo")


def align(value: int, to: int) -> int:
    return (value + to - 1) // to * to


def blz_decompress(data: bytes) -> bytes:
    """Nintendo backwards-LZ used for ExeFS .code. Returns data unchanged if not packed."""
    if len(data) < 8:
        return data
    footer = data[-8:]
    extra_size = struct.unpack_from("<I", footer, 4)[0]
    if extra_size == 0:
        return data

    header_size = footer[3]
    compressed_end = struct.unpack_from("<I", footer, 0)[0] & 0x00FFFFFF
    if not (8 <= header_size <= 0x20) or compressed_end > len(data):
        return data

    # Both ends walk downwards: `src` from the last flag byte before the footer, `dst` from
    # the end of the unpacked image. The pair is little-endian, length in its top nibble.
    total = len(data) + extra_size
    out = bytearray(data + b"\x00" * extra_size)
    src = len(data) - header_size
    dst = total
    stop = len(data) - compressed_end

    while src > stop:
        src -= 1
        flags = out[src]
        for bit in range(8):
            if src <= stop:
                break
            if not flags & (0x80 >> bit):
                src -= 1
                dst -= 1
                out[dst] = out[src]
                continue
            src -= 2
            pair = out[src] | (out[src + 1] << 8)
            for _ in range((pair >> 12) + 3):
                out[dst - 1] = out[dst - 1 + (pair & 0xFFF) + 3]
                dst -= 1

    return bytes(out[:total])


def contents(data: bytes) -> tuple[str, int, list[tuple[int, bytes, bool]]]:
    """-> (title id, title version, [(content index, NCCH, hash matches)])."""
    header_size = struct.unpack_from("<I", data, 0)[0]
    cert_size, ticket_size, tmd_size = struct.unpack_from("<III", data, 0x08)
    offset = align(header_size, SECTION_ALIGN)
    for size in (cert_size, ticket_size):
        offset += align(size, SECTION_ALIGN)
    tmd = data[offset:offset + tmd_size]
    offset += align(tmd_size, SECTION_ALIGN)

    signature_type = struct.unpack_from(">I", tmd, 0)[0]
    if signature_type not in SIGNATURE_SIZES:
        raise SystemExit(f"unknown TMD signature type {signature_type:#x} - not a CIA?")
    body = 4 + SIGNATURE_SIZES[signature_type]
    title_id = struct.unpack_from(">Q", tmd, body + TMD_TITLE_ID)[0]
    title_version = struct.unpack_from(">H", tmd, body + TMD_TITLE_VERSION)[0]
    count = struct.unpack_from(">H", tmd, body + TMD_CONTENT_COUNT)[0]

    chunks = body + TMD_CONTENT_INFO + TMD_CONTENT_INFO_SIZE
    out = []
    for i in range(count):
        chunk = chunks + i * TMD_CHUNK_SIZE
        index = struct.unpack_from(">H", tmd, chunk + 4)[0]
        size = struct.unpack_from(">Q", tmd, chunk + 8)[0]
        blob = data[offset:offset + size]
        offset += size
        out.append((index, blob, hashlib.sha256(blob).digest() == tmd[chunk + 0x10:chunk + 0x30]))
    return f"{title_id:016X}", title_version, out


def exefs_sections(blob: bytes) -> dict[str, bytes]:
    sections = {}
    for i in range(EXEFS_ENTRIES):
        name, offset, size = struct.unpack_from("<8sII", blob, i * 0x10)
        name = name.rstrip(b"\0").decode()
        if name:
            sections[name] = blob[EXEFS_HEADER_SIZE + offset:EXEFS_HEADER_SIZE + offset + size]
    return sections


def romfs_image(blob: bytes) -> bytes:
    """The level 3 RomFS out of the IVFC wrapper - the image tools/romfs.py reads.

    Only the master hash sits between the header and the data; the level 1 and 2 hash
    blocks follow it, which is why the data lands on the first block boundary past it.
    """
    if blob[:4] != b"IVFC":
        raise SystemExit(f"RomFS starts with {blob[:4]!r}, not IVFC")
    master_size = struct.unpack_from("<I", blob, 0x08)[0]
    _, data_size, block_log = struct.unpack_from("<QQI", blob, 0x0C + 2 * 0x18)
    start = align(0x60 + master_size, 1 << block_log)
    return blob[start:start + data_size]


def unpack(blob: bytes, out: Path, manual: bool, write: bool) -> None:
    """One NCCH -> the files of one work/<TID>/ directory."""
    if blob[0x100:0x104] != b"NCCH":
        raise SystemExit("no NCCH header - an encrypted CIA cannot be unpacked, "
                         "ask for GodMode9's `Build CIA (standard)`")
    product = blob[0x150:0x160].rstrip(b"\0").decode()
    encrypted = not blob[0x188 + 7] & 0x04     # flags[7] bit 2: NoCrypto
    exheader_size = struct.unpack_from("<I", blob, 0x180)[0]
    exefs_offset, exefs_size = struct.unpack_from("<II", blob, 0x1A0)
    romfs_offset, romfs_size = struct.unpack_from("<II", blob, 0x1B0)
    print(f"    {product}: exheader {exheader_size:#x}, exefs {exefs_size * MEDIA_UNIT:#x}, "
          f"romfs {romfs_size * MEDIA_UNIT:#x}" + (" - ENCRYPTED" if encrypted else ""))
    if encrypted:
        raise SystemExit("this content is encrypted, ask for `Build CIA (standard)`")

    files: dict[str, bytes] = {}
    compressed = False
    if exheader_size:
        exheader = blob[0x200:0x200 + EXHEADER_SIZE]
        compressed = bool(exheader[0x0D] & 0x01)   # SCI flags: ExeFS .code is BLZ-packed
        files["exheader.bin"] = exheader

    if exefs_size:
        exefs = blob[exefs_offset * MEDIA_UNIT:(exefs_offset + exefs_size) * MEDIA_UNIT]
        for name, section in exefs_sections(exefs).items():
            if name == ".code":
                files["code.bin"] = blz_decompress(section) if compressed else section
            else:
                files[name if name in EXEFS_AS_IS else f"{name}.bin"] = section

    if romfs_size:
        image = romfs_image(blob[romfs_offset * MEDIA_UNIT:(romfs_offset + romfs_size) * MEDIA_UNIT])
        for path, data in romfs.read(image).items():
            # The manual content holds Manual.bcma and nothing else, and tools/manual.py
            # reads it at work/<TID>/manual/Manual.bcma, without a romfs/ level.
            prefix = "" if manual else "romfs/"
            files[prefix + path.lstrip("/")] = data

    for name, data in files.items():
        note = f"{len(data)} bytes"
        if name == "code.bin":
            note += f", sha256 {hashlib.sha256(data).hexdigest()}"
        if not name.startswith("romfs/"):
            print(f"      {name}  {note}")
        if write:
            target = out / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    romfs_files = sum(1 for name in files if name.startswith("romfs/"))
    if romfs_files:
        print(f"      romfs/  {romfs_files} files")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--list", action="store_true", help="report only, write nothing")
    args = parser.parse_args()

    for path in args.files:
        title_id, title_version, blobs = contents(path.read_bytes())
        print(f"{path.name}\n  {title_id} title version {title_version}, {len(blobs)} contents")
        for index, blob, hash_ok in blobs:
            if not hash_ok:
                raise SystemExit(f"content {index} does not match its TMD hash - corrupt or encrypted")
            base = ROOT / "work" / title_id
            print(f"    content {index}: {len(blob)} bytes, hash ok")
            unpack(blob, base / "manual" if index else base, manual=bool(index), write=not args.list)
        if not args.list:
            print(f"  -> work/{title_id}/")


if __name__ == "__main__":
    main()
