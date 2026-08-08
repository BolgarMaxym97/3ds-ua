"""BCLYT (`CLYT`) reader and writer — only as much of the layout format as a manual page needs.

A manual page is a CLYT whose text lives in `txt1` panes, one pane per rendered line, with
the line break already baked in by Nintendo's ManualEditor. Every pane carries its own box
size, so a translation that is wider than the original needs the box widened too.

File: magic 'CLYT', BOM u16, header size u16 (0x14), version u32, file size u32,
section count u16, padding u16. Sections follow back to back, each `magic` + size u32,
and nothing outside a section points into another one - so a section can grow or shrink as
long as its own size field and the file size are updated.

txt1 body (after the 0x44-byte pane block that starts at +0x08):
    +0x4C textBufBytes u16   +0x4E textStrBytes u16   (both count the NUL terminator)
    +0x50 materialIdx u16    +0x52 fontIdx u16
    +0x54 textPosition u8    +0x55 textAlignment u8   +0x56 padding u16
    +0x58 textOffset u32     — 0x74 in every manual pane seen so far
    +0x5C topColor u32       +0x60 bottomColor u32
    +0x64 fontSizeX f32      +0x68 fontSizeY f32
    +0x6C charSpace f32      +0x70 lineSpace f32
    +0x74 the string, UTF-16LE, NUL-terminated, padded to a 4-byte boundary

Usage:
    python3 tools/bclyt.py <file.bclyt>     # list text panes and verify a round-trip
"""

from __future__ import annotations

import struct
import sys
from dataclasses import dataclass
from pathlib import Path

MAGIC = b"CLYT"
TXT1 = b"txt1"
PANE_KINDS = (b"pan1", b"pic1", b"txt1", b"wnd1", b"bnd1")
PANE_ORIGIN = 0x09
PANE_NAME = 0x0C
PANE_NAME_LEN = 0x18
PANE_SIZE = 0x44  # size.x, size.y f32 - the text box
TEXT_BUF = 0x4C
TEXT_STR = 0x4E
MATERIAL = 0x50   # materialIdx u16, fontIdx u16
TEXT_OFFSET = 0x58
TOP_COLOR = 0x5C  # topColor u32, bottomColor u32
FONT_SIZE = 0x64
CHAR_SPACE = 0x6C
STRING_AT = 0x74
TRANSLATE = 0x24


@dataclass
class Pane:
    kind: str          # 'txt1', 'pic1', 'pan1', ...
    name: str
    width: float       # the box, not the rendered text
    height: float
    x: float
    y: float
    text: str = ""         # txt1 only, exactly as stored, without the NUL
    font_size: float = 0.0  # fontSizeX
    line_height: float = 0.0  # fontSizeY plus lineSpace - the step between lines in one pane
    char_space: float = 0.0
    origin: int = 0        # 0 = the pane is placed by its top-left corner
    style: tuple = ()      # font and vertex colours - what makes a highlighted run look different

    @property
    def is_text(self) -> bool:
        return self.kind == "txt1"


@dataclass
class Edit:
    """What to change about one pane. `None` leaves that field alone."""

    text: str | None = None
    x: float | None = None
    y: float | None = None
    width: float | None = None
    # Keep the pane's existing textBufBytes and pad the new string out to it, instead of
    # sizing the buffer to the string. The pane, the section and the whole file then stay
    # exactly as long as they were, which is what lets tools/darc.py splice() write a
    # layout back into an archive in place - see build_layout_texts() in tools/build.py.
    # Only ever shrinks the used length: a string too long for the buffer is an error.
    keep_buffer: bool = False


def parse(data: bytes) -> list[Pane]:
    """Every pane in the file, in layout order. Pictures are included because an icon
    sitting inside a line of text has to be accounted for when the text is re-wrapped."""
    if data[:4] != MAGIC:
        raise ValueError(f"not a BCLYT: {data[:4]!r}")

    return [
        _read_pane(data, start, magic)
        for magic, start, _ in _sections(data)
        if magic in PANE_KINDS
    ]


def texts(data: bytes) -> list[Pane]:
    return [pane for pane in parse(data) if pane.is_text]


def rewrite(data: bytes, changes: dict[str, Edit]) -> bytes:
    """Apply the edits to the named panes.

    Panes not mentioned are copied byte for byte, so rewriting with what is already there
    gives the file back unchanged.
    """
    out = bytearray(data[: struct.unpack_from("<H", data, 0x06)[0]])
    unused = set(changes)

    for magic, start, size in _sections(data):
        section = data[start : start + size]
        if magic in PANE_KINDS:
            name = _name(data, start)
            if name in changes:
                unused.discard(name)
                section = _write_pane(section, magic, changes[name])
        out += section

    if unused:
        raise KeyError(f"no such pane: {sorted(unused)}")

    struct.pack_into("<I", out, 0x0C, len(out))
    return bytes(out)


def _sections(data: bytes):
    header_size = struct.unpack_from("<H", data, 0x06)[0]
    count = struct.unpack_from("<H", data, 0x10)[0]
    pos = header_size
    for _ in range(count):
        size = struct.unpack_from("<I", data, pos + 4)[0]
        yield data[pos : pos + 4], pos, size
        pos += size


def _name(data: bytes, start: int) -> str:
    raw = data[start + PANE_NAME : start + PANE_NAME + PANE_NAME_LEN]
    return raw.split(b"\0")[0].decode("ascii")


def _read_pane(data: bytes, start: int, magic: bytes) -> Pane:
    width, height = struct.unpack_from("<ff", data, start + PANE_SIZE)
    x, y = struct.unpack_from("<ff", data, start + TRANSLATE)
    pane = Pane(
        kind=magic.decode("ascii"),
        origin=data[start + PANE_ORIGIN],
        name=_name(data, start),
        width=width,
        height=height,
        x=x,
        y=y,
    )
    if magic != TXT1:
        return pane

    str_bytes = struct.unpack_from("<H", data, start + TEXT_STR)[0]
    offset = struct.unpack_from("<I", data, start + TEXT_OFFSET)[0]
    pane.text = data[start + offset : start + offset + str_bytes].decode("utf-16-le").rstrip("\0")
    pane.font_size = struct.unpack_from("<f", data, start + FONT_SIZE)[0]
    font_size_y = struct.unpack_from("<f", data, start + FONT_SIZE + 4)[0]
    pane.char_space, line_space = struct.unpack_from("<ff", data, start + CHAR_SPACE)
    pane.line_height = font_size_y + line_space
    # The material index is unique per pane here (ManualEditor gives every text box its own,
    # byte-identical one), so what actually distinguishes a highlighted run is the font and
    # the vertex colours.
    pane.style = struct.unpack_from("<H", data, start + MATERIAL + 2) + struct.unpack_from(
        "<II", data, start + TOP_COLOR
    )
    return pane


def _write_pane(section: bytes, magic: bytes, edit: Edit) -> bytes:
    out = bytearray(section)
    if edit.x is not None:
        struct.pack_into("<f", out, TRANSLATE, edit.x)
    if edit.y is not None:
        struct.pack_into("<f", out, TRANSLATE + 4, edit.y)
    if edit.width is not None:
        struct.pack_into("<f", out, PANE_SIZE, edit.width)

    if edit.text is None:
        return bytes(out)
    if magic != TXT1:
        raise ValueError(f"{magic!r} pane has no text")

    offset = struct.unpack_from("<I", out, TEXT_OFFSET)[0]
    if offset != STRING_AT:
        raise ValueError(f"unexpected text offset {offset:#x}")

    # An empty pane stores nothing at all, not a lone terminator: textStrBytes is 0.
    encoded = (edit.text + "\0").encode("utf-16-le") if edit.text else b""
    if len(encoded) > 0xFFFF:
        raise ValueError("string too long for a u16 length")

    used = len(encoded)
    buffer = struct.unpack_from("<H", out, TEXT_BUF)[0]
    if edit.keep_buffer:
        if used > buffer:
            raise ValueError(f"{used} bytes do not fit the pane's {buffer}-byte text buffer")
        encoded += b"\0" * (buffer - used)
        buffer_bytes = buffer
    else:
        buffer_bytes = used

    out = out[:STRING_AT]
    struct.pack_into("<HH", out, TEXT_BUF, buffer_bytes, used)
    out += encoded
    out += b"\0" * (-len(out) % 4)
    struct.pack_into("<I", out, 0x04, len(out))
    return bytes(out)


def main() -> None:
    data = Path(sys.argv[1]).read_bytes()
    panes = texts(data)
    for pane in parse(data):
        print(
            f"  {pane.kind} {pane.name:16} x={pane.x:7.1f} y={pane.y:8.1f} "
            f"w={pane.width:6.1f} {pane.text!r}"
        )
    same = rewrite(data, {p.name: Edit(text=p.text) for p in panes}) == data
    print(f"{len(panes)} text panes; round-trip {'byte-identical' if same else 'MISMATCH'}")
    if not same:
        sys.exit(1)


if __name__ == "__main__":
    main()
