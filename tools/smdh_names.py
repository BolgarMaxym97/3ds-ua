"""Build the title-name table the HOME Menu code patch reads at runtime.

HOME Menu takes the names it displays - icon labels, the "software suspended" overlay, the
close and delete prompts - from each title's SMDH, which it reads out of ExeFS:/icon in
NAND. LayeredFS replaces romfs and nothing else, so those strings are out of its reach.
What is in reach is HOME Menu's own code: the function that reads an SMDH is hooked, and
right after the read the language slot the build replaces - Russian or English, see
tools/variant.py - is overwritten in the buffer from this table.

Table layout, little-endian, terminated by a zero title-id:

    +0x00  u32  title id low word      the search key
    +0x04  u8   title id high byte     0x10 for applications, 0x30 for applets
    +0x05  u8   short length in UTF-16 code units, 0 = leave the field alone
    +0x06  u8   long length in UTF-16 code units, 0 = leave the field alone
    +0x07  u8   padding, so the strings start 8-byte aligned
    +0x08  u16  short description, `short length` code units, no terminator
           u16  long description, `long length` code units, no terminator

The stub writes the terminating NUL itself, which is why the lengths are stored instead:
it keeps every entry as short as the text it carries, and the whole table has to fit in
the .rodata padding.
"""

from __future__ import annotations

import struct

# SMDH application-title array: 8-byte header, then one 0x200-byte structure per language.
# Everything here is relative to the start of the buffer HOME Menu read the SMDH into.
TITLES_OFFSET = 0x08
TITLE_SIZE = 0x200
SHORT_OFFSET = 0x00
LONG_OFFSET = 0x80

# Field capacities in UTF-16 code units, one reserved for the NUL the stub writes.
SHORT_LIMIT = 0x40 - 1
LONG_LIMIT = 0x80 - 1

ENTRY_HEADER = 8


def slot_offsets(index: int) -> tuple[int, int]:
    """Where the short and long description of one language slot start in the buffer."""
    base = TITLES_OFFSET + index * TITLE_SIZE
    return base + SHORT_OFFSET, base + LONG_OFFSET


def build_table(entries: dict[str, dict[str, str]]) -> tuple[bytes, list[str]]:
    """Assemble the table from {title id: {"ua": short, "ua_long": long}}, plus a log.

    The strings arrive with homoglyphs already applied - the console renders them with the
    system font, exactly like the strings in romfs.
    """
    out = bytearray()
    log: list[str] = []
    for tid, entry in entries.items():
        if tid.startswith("_") or not entry.get("ua"):
            continue
        if len(tid) != 16:
            raise ValueError(f"{tid!r} is not a 16-digit title id")
        high, low = int(tid[:8], 16), int(tid[8:], 16)
        if high not in (0x00040010, 0x00040030):
            raise ValueError(f"{tid}: only applications and applets are supported, not {high:#010x}")

        short = entry["ua"]
        long = entry.get("ua_long") or short
        for what, text, limit in (("ua", short, SHORT_LIMIT), ("ua_long", long, LONG_LIMIT)):
            if len(text) > limit:
                raise ValueError(f"{tid} {what} is {len(text)} code units, the field holds {limit}")

        out += struct.pack("<IBBBB", low, high & 0xFF, len(short), len(long), 0)
        out += short.encode("utf-16-le") + long.encode("utf-16-le")
        log.append(f"{tid} -> {short!r}" + (f" / {long!r}" if long != short else ""))

    out += struct.pack("<I", 0)
    return bytes(out), log
