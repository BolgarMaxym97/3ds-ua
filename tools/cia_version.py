"""Write the title version into a CIA's TMD and ticket.

makerom drops the minor part of the version: `-major 2 -minor 1 -micro 0` (and `-ver 2064`)
build a CIA that says 2.0.0. Releases only ever bump the minor (1.9.0 -> 1.10.0), so every
2.x.0 installer read as 2.0.0 in FBI, Data Management and AM_GetTitleInfo - and the 3DS UA
Hub, which knows a CIA put on the console without it by its AM version, never recognised one.
This sets the version after makerom, where AM reads it: the TMD, and the ticket alongside.

The signatures over both are makerom's dummy ones; the console takes CIAs with those only
through Luma's signature patches, which do not check them, so editing the bytes is safe.

Layout (3dbrew "CIA", "Ticket", "Title metadata"): a header, then the certificate chain,
ticket and TMD, each aligned to 64 bytes. Ticket and TMD open with a signature whose type
sets its length; the version is at body + 0xA6 in the ticket and body + 0x9C in the TMD, as
major << 10 | minor << 4 | micro, big-endian.

Usage (`make installer-makerom` runs it):
    python3 tools/cia_version.py installer/3ds-ua-installer.cia 2.1.0
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

# signature type -> bytes from the start of the block to its body (type, signature, padding)
BODY = {0x10003: 4 + 0x200 + 0x3C, 0x10004: 4 + 0x100 + 0x3C, 0x10005: 4 + 0x3C + 0x40}
TICKET_VERSION = 0xA6
TMD_VERSION = 0x9C


def align(value: int, to: int = 64) -> int:
    return (value + to - 1) // to * to


def pack_version(text: str) -> int:
    major, minor, micro = (int(p) for p in text.split("."))
    if not (0 <= major < 64 and 0 <= minor < 64 and 0 <= micro < 16):
        raise ValueError(f"{text}: AM holds major and minor below 64, micro below 16")
    return major << 10 | minor << 4 | micro


def body(data: bytearray, start: int) -> int:
    (kind,) = struct.unpack_from(">I", data, start)
    if kind not in BODY:
        raise ValueError(f"unknown signature type {kind:#x} at {start:#x}")
    return start + BODY[kind]


def set_version(data: bytearray, version: int) -> None:
    (header,) = struct.unpack_from("<I", data, 0)
    certs, ticket = struct.unpack_from("<II", data, 8)
    ticket_at = align(header) + align(certs)
    tmd_at = ticket_at + align(ticket)
    struct.pack_into(">H", data, body(data, ticket_at) + TICKET_VERSION, version)
    struct.pack_into(">H", data, body(data, tmd_at) + TMD_VERSION, version)


def main() -> None:
    path, text = Path(sys.argv[1]), sys.argv[2]
    version = pack_version(text)
    data = bytearray(path.read_bytes())
    set_version(data, version)
    path.write_bytes(data)
    print(f"{path}: title version {text} ({version})")


if __name__ == "__main__":
    main()
