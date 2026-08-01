"""Flat message archive — the container Nintendo 3DS Camera and Sound keep their MSBT
files in (`romfs/msg/<LANG>.LZ`, LZ11-compressed).

No magic and no header: the file opens straight into a fixed-size entry table, and the
first entry's data offset is where the table ends.

Entry (0x40 bytes each):
    0x00 name   char[0x38]  — null-padded ASCII (`P_tips.msbt`, `RI.mstl`)
    0x38 offset u32         — absolute, 0x80-aligned
    0x3C size   u32         — exact byte length, unpadded

Unused table slots are all zeroes; both known titles ship 6 slots with 4 in use, so the
slot count is kept from the source instead of recomputed - a shorter table would move
every file. Gaps between files and the tail of the archive are zero padding to 0x80.

Usage:
    python3 tools/msgarc.py <file>      # list contents and verify a byte-exact round-trip
"""

from __future__ import annotations

import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

ENTRY_SIZE = 0x40
NAME_SIZE = 0x38
DATA_ALIGN = 0x80


@dataclass
class Entry:
    name: str
    data: bytes = b""


@dataclass
class MsgArc:
    entries: list[Entry] = field(default_factory=list)
    slots: int = 0  # entry table length, including the unused zeroed slots

    def files(self) -> list[tuple[str, Entry]]:
        """-> [(name, entry)] in archive order, to match darc.files()."""
        return [(entry.name, entry) for entry in self.entries]

    def find(self, name: str) -> Entry | None:
        return next((entry for entry in self.entries if entry.name == name), None)


def parse(data: bytes) -> MsgArc:
    first_offset = struct.unpack_from("<I", data, NAME_SIZE)[0]
    if first_offset % ENTRY_SIZE or not 0 < first_offset <= len(data):
        raise ValueError(f"not a flat message archive: first offset {first_offset:#x}")

    arc = MsgArc(slots=first_offset // ENTRY_SIZE)
    for index in range(arc.slots):
        raw = data[index * ENTRY_SIZE : (index + 1) * ENTRY_SIZE]
        offset, size = struct.unpack_from("<II", raw, NAME_SIZE)
        name = raw[:NAME_SIZE].rstrip(b"\x00").decode("ascii")
        if not name:
            continue  # unused slot
        if offset + size > len(data):
            raise ValueError(f"{name}: entry runs past the archive end")
        arc.entries.append(Entry(name, data[offset : offset + size]))
    return arc


def build(arc: MsgArc) -> bytes:
    table = bytearray(arc.slots * ENTRY_SIZE)
    body = bytearray()
    offset = arc.slots * ENTRY_SIZE

    for index, entry in enumerate(arc.entries):
        body += b"\x00" * (_align(offset, DATA_ALIGN) - offset)
        offset = _align(offset, DATA_ALIGN)
        name = entry.name.encode("ascii")
        if len(name) >= NAME_SIZE:
            raise ValueError(f"{entry.name}: name does not fit in {NAME_SIZE} bytes")
        struct.pack_into(f"<{NAME_SIZE}sII", table, index * ENTRY_SIZE, name, offset, len(entry.data))
        body += entry.data
        offset += len(entry.data)

    body += b"\x00" * (_align(offset, DATA_ALIGN) - offset)
    return bytes(table) + bytes(body)


def _align(value: int, alignment: int) -> int:
    return (value + alignment - 1) // alignment * alignment


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2

    raw = Path(sys.argv[1]).read_bytes()
    if raw[:1] == b"\x11":
        sys.path.insert(0, str(Path(__file__).parent))
        from lz11 import decompress

        raw = decompress(raw)

    arc = parse(raw)
    for name, entry in arc.files():
        print(f"{name:16s} {len(entry.data):#10x}  {entry.data[:8]!r}")
    rebuilt = build(arc)
    print(f"{arc.slots} slots, round-trip: {'byte-exact' if rebuilt == raw else 'DIFFERS'}")
    return 0 if rebuilt == raw else 1


if __name__ == "__main__":
    raise SystemExit(main())
