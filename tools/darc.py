"""DARC (`darc`) archive reader and writer — the container System Settings and Mii Maker
keep their MSBT files in.

Layout:
    0x00 magic 'darc'
    0x04 BOM u16 (0xFEFF)
    0x06 header size u16 (0x1C)
    0x08 version u32
    0x0C file size u32
    0x10 table offset u32
    0x14 table length u32  (entries + name table)
    0x18 data offset u32

Entry (12 bytes each):
    name_offset u32   — low 24 bits index into the name table, top byte 0x01 marks a directory
    value u32         — directory: index of the parent entry; file: absolute data offset
    size u32          — directory: index one past its last child; file: byte length

Entry 0 is the root directory. Names are null-terminated UTF-16LE and follow the entries.

Usage:
    python3 tools/darc.py <file>        # list contents and verify a byte-exact round-trip
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from functools import reduce
from math import gcd

MAGIC = b"darc"
HEADER_SIZE = 0x1C
DIR_FLAG = 0x01000000
DEFAULT_ALIGN = 0x20
# File alignment differs per archive (System Settings uses 0x20, Mii Maker 0x80), so it is
# inferred from the source offsets instead of hardcoded - otherwise a rebuild shifts every file.


@dataclass
class Entry:
    name: str
    is_dir: bool
    parent: int = 0       # directories only
    end_index: int = 0    # directories only: index one past the last child
    data: bytes = b""     # files only


@dataclass
class Darc:
    version: int = 0x01000000
    entries: list[Entry] = field(default_factory=list)
    data_align: int = DEFAULT_ALIGN
    # data offsets of the source archive, kept so an untouched archive rebuilds byte-exactly
    source_offsets: list[int] = field(default_factory=list)

    def files(self) -> list[tuple[str, Entry]]:
        """-> [(path, entry)] for files only, in archive order."""
        out: list[tuple[str, Entry]] = []
        for index, entry in enumerate(self.entries):
            if not entry.is_dir:
                out.append((self._path_of(index), entry))
        return out

    def find(self, path: str) -> Entry | None:
        for candidate, entry in self.files():
            if candidate == path:
                return entry
        return None

    def _path_of(self, index: int) -> str:
        parts = [self.entries[index].name]
        parent = self._parent_of(index)
        while parent is not None and parent != 0:
            parts.append(self.entries[parent].name)
            parent = self.entries[parent].parent
        return "/".join(reversed(parts))

    def _parent_of(self, index: int) -> int | None:
        """Files do not store their parent, so find the directory that contains them."""
        for candidate in range(index - 1, -1, -1):
            entry = self.entries[candidate]
            if entry.is_dir and candidate < index < entry.end_index:
                return candidate
        return None


def parse(data: bytes) -> Darc:
    if data[:4] != MAGIC:
        raise ValueError(f"not a DARC archive: {data[:4]!r}")

    version = struct.unpack_from("<I", data, 0x08)[0]
    table_offset, table_length = struct.unpack_from("<II", data, 0x10)

    root_name_offset, _, entry_count = struct.unpack_from("<III", data, table_offset)
    if not root_name_offset & DIR_FLAG:
        raise ValueError("entry 0 is not a directory")

    names_offset = table_offset + entry_count * 12
    names = data[names_offset : table_offset + table_length]

    darc = Darc(version=version)
    for index in range(entry_count):
        name_offset, value, size = struct.unpack_from("<III", data, table_offset + index * 12)
        is_dir = bool(name_offset & DIR_FLAG)
        name = _read_name(names, name_offset & 0x00FFFFFF)

        if is_dir:
            darc.entries.append(Entry(name=name, is_dir=True, parent=value, end_index=size))
            darc.source_offsets.append(0)
        else:
            darc.entries.append(Entry(name=name, is_dir=False, data=data[value : value + size]))
            darc.source_offsets.append(value)

    darc.data_align = _infer_align([o for o in darc.source_offsets if o])
    return darc


def _infer_align(offsets: list[int]) -> int:
    """Largest power of two that divides every file offset, clamped to [4, 0x200]."""
    if not offsets:
        return DEFAULT_ALIGN
    common = reduce(gcd, offsets)
    align = 4
    while align * 2 <= min(common, 0x200) and common % (align * 2) == 0:
        align *= 2
    return align


def build(darc: Darc) -> bytes:
    entry_count = len(darc.entries)
    names = bytearray()
    name_offsets: list[int] = []
    for entry in darc.entries:
        name_offsets.append(len(names))
        names += entry.name.encode("utf-16-le") + b"\x00\x00"

    table_length = entry_count * 12 + len(names)
    data_offset = _align(HEADER_SIZE + table_length, darc.data_align)

    blobs = bytearray()
    file_offsets: dict[int, int] = {}
    for index, entry in enumerate(darc.entries):
        if entry.is_dir:
            continue
        while (data_offset + len(blobs)) % darc.data_align:
            blobs.append(0)
        file_offsets[index] = data_offset + len(blobs)
        blobs += entry.data

    table = bytearray()
    for index, entry in enumerate(darc.entries):
        name_field = name_offsets[index] | (DIR_FLAG if entry.is_dir else 0)
        if entry.is_dir:
            table += struct.pack("<III", name_field, entry.parent, entry.end_index)
        else:
            table += struct.pack("<III", name_field, file_offsets[index], len(entry.data))

    out = bytearray(MAGIC)
    out += struct.pack("<HH", 0xFEFF, HEADER_SIZE)
    out += struct.pack("<I", darc.version)
    out += struct.pack("<I", 0)  # file size, filled in below
    out += struct.pack("<III", HEADER_SIZE, table_length, data_offset)
    out += table
    out += names
    while len(out) < data_offset:
        out.append(0)
    out += blobs

    struct.pack_into("<I", out, 0x0C, len(out))
    return bytes(out)


def _read_name(names: bytes, offset: int) -> str:
    end = offset
    while end + 1 < len(names) and names[end : end + 2] != b"\x00\x00":
        end += 2
    return names[offset:end].decode("utf-16-le")


def _align(value: int, alignment: int) -> int:
    return (value + alignment - 1) // alignment * alignment


if __name__ == "__main__":
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent))
    from lz11 import decompress

    path = Path(sys.argv[1])
    raw = path.read_bytes()
    data = decompress(raw) if raw[:1] == b"\x11" else raw

    archive = parse(data)
    files = archive.files()
    print(f"{path.name}: {len(archive.entries)} entries, {len(files)} files, align 0x{archive.data_align:X}")
    for name, entry in files:
        note = f"  {entry.data[:8]!r}" if entry.data[:8] == b"MsgStdBn" else ""
        print(f"  {name}  {len(entry.data)} bytes{note}")

    rebuilt = build(archive)
    if rebuilt == data:
        print("round-trip: byte-identical")
    else:
        diff = next((i for i in range(min(len(rebuilt), len(data))) if rebuilt[i] != data[i]), None)
        where = f", first difference @0x{diff:X}" if diff is not None else ""
        print(f"round-trip: MISMATCH (size {len(rebuilt)} vs {len(data)}{where})")
