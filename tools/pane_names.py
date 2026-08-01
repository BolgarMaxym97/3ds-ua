"""Build the string-substitution table for titles that never read an SMDH themselves.

The Activity Log is the awkward case: it has no `am:*` and no `ns:s`, its only
`ARCHIVE_SAVEDATA_AND_CONTENT` open is the shared system font, and the `icon` in its code is
a layout pane name rather than a file. It receives finished strings and draws them, so there
is no SMDH buffer to rewrite the way tools/smdh_names.py does for the HOME Menu.

What it does have is one text setter that every string goes through:

    add r0, pc, #...      the MSBT label
    bl  GetMessage        -> u16*
    mov r1, r0
    add r2, pc, #...      the pane name
    bl  SetPaneText(layout, text, pane, ...)

Hooking that and swapping the `text` pointer when it matches a name we know translates the
application names without touching anyone's buffer - the replacement string lives in our own
blob and the original is left alone.

Table layout, little-endian, terminated by a zero length:

    +0x00  u16  length of the original, in UTF-16 code units, 0 = end of table
    +0x02  u16  length of the replacement, its NUL included
    +0x04  u16  the original, no terminator - the hook compares exactly this many units
                and then requires the candidate to end
           u16  the replacement, NUL-terminated: this is what the pointer is swapped for
"""

from __future__ import annotations

import struct

ENTRY_HEADER = 4


def build_table(entries: list[tuple[str, str]]) -> tuple[bytes, list[str]]:
    """Assemble the table from [(original, replacement)], plus a log.

    Replacements arrive with homoglyphs already applied; originals must not have them - they
    are compared against what the title itself holds in memory.
    """
    out = bytearray()
    log: list[str] = []
    for original, replacement in entries:
        if not original or not replacement:
            continue
        if len(original) > 0xFFFF or len(replacement) + 1 > 0xFFFF:
            raise ValueError(f"{original!r} -> {replacement!r} does not fit the length fields")
        out += struct.pack("<HH", len(original), len(replacement) + 1)
        out += original.encode("utf-16-le")
        out += replacement.encode("utf-16-le") + b"\0\0"
        log.append(f"{original!r} -> {replacement!r}")

    out += struct.pack("<H", 0)
    return bytes(out), log
