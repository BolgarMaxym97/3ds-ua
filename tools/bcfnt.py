"""Read a BCFNT (3DS bitmap font) and add code points to it.

The HUD font - the one that draws the clock line on the top screen - is not the shared
system font. Every applet that shows that line carries its own copy in its romfs, and
that copy is a subset: 67 code points, whose only Cyrillic letters are the ones the
Russian weekday abbreviations need (`Вс Пн Вт Ср Чт Пт Сб` -> `В П С Ч б н р с т`).
Ukrainian `Нд` therefore draws as nothing at all, which is the empty `( )` on the clock.

Adding the two missing glyphs needs no new texture sheet: the last sheet has 12 cells and
only 7 are used, so the pixels go into free cells and the tables grow by two entries.

Layout (see 3dbrew "BCFNT"): a 20-byte CFNT header followed by blocks, each with a 4-byte
magic and a u32 size that includes those 8 bytes.

    FINF  font metrics, plus absolute pointers to TGLP / CWDH / CMAP
    TGLP  the texture sheets: cellWidth x cellHeight cells, numColumns x numRows per sheet
    CWDH  one (left, glyphWidth, charWidth) triple per glyph index, as a linked list
    CMAP  code point -> glyph index, as a linked list of blocks in three encodings

Every pointer in the file is to a block's *body* - block start + 8 - so rebuilding means
recomputing all of them. `build(parse(data)) == data` byte for byte, which is what keeps
an untouched font untouched.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

MAGIC = b"CFNT"
HEADER_SIZE = 0x14
BLOCK_HEADER = 8

# Sheet pixel format 9 is LA4: one byte per pixel, luminance in the high nibble, alpha in
# the low one. That is the only format the HUD font uses, and the only one worth writing.
#
# Both nibbles carry shape here, which is easy to get wrong. These glyphs are white with a
# one-pixel black outline, and that is encoded as: alpha = the whole silhouette, outline
# included; luminance = the white core inside it, inset by that one pixel. Filling the
# luminance with 15 across the silhouette - the obvious reading of "the glyph is white" -
# drops the outline and paints the letter a pixel fatter on every side, which on hardware
# reads as a different, bolder font sitting in the middle of the clock line.
FORMAT_LA4 = 9

# CMAP encodings.
MAP_DIRECT = 0
MAP_TABLE = 1
MAP_SCAN = 2


@dataclass
class Sheets:
    """The TGLP block, with the texture kept as one detiled 8-bit plane per sheet."""

    cell_width: int
    cell_height: int
    baseline: int
    max_char_width: int
    image_format: int
    columns: int
    rows: int
    width: int
    height: int
    planes: list[list[bytearray]]

    @property
    def per_sheet(self) -> int:
        return self.columns * self.rows

    @property
    def capacity(self) -> int:
        return self.per_sheet * len(self.planes)

    def cell_origin(self, index: int) -> tuple[list[bytearray], int, int]:
        """The plane and top-left pixel of a glyph's cell.

        Cells sit on a (cellWidth + 1) x (cellHeight + 1) grid and the extra pixel comes
        *first*: a one-pixel gutter above and to the left of every cell, so that filtering
        never pulls a neighbour's ink in. Getting this wrong is easy to miss - the glyphs
        still come out, only shifted a pixel or two, and the widest of them quietly lose
        their last column. The check that catches it: with the right origin, every glyph's
        inked columns start at 0 and are exactly `glyphWidth` wide.
        """
        plane = self.planes[index // self.per_sheet]
        cell = index % self.per_sheet
        return (
            plane,
            (cell % self.columns) * (self.cell_width + 1) + 1,
            (cell // self.columns) * (self.cell_height + 1) + 1,
        )


@dataclass
class Font:
    version: int
    finf: bytes  # the FINF body, offsets excluded - copied through untouched
    sheets: Sheets
    widths: list[tuple[int, int, int]]  # glyph index -> (left, glyph width, char width)
    cmap: dict[int, int]  # code point -> glyph index
    cmap_blocks: list[tuple[int, int, int]]  # (code begin, code end, encoding), in file order
    blocks: list[tuple[bytes, bytes]] = field(default_factory=list)  # blocks we pass through


def parse(data: bytes) -> Font:
    if data[:4] != MAGIC:
        raise ValueError(f"not a BCFNT file: {data[:4]!r}")
    if struct.unpack_from("<H", data, 4)[0] != 0xFEFF:
        raise ValueError("big-endian BCFNT is not supported")

    version = struct.unpack_from("<I", data, 8)[0]
    header_size = struct.unpack_from("<H", data, 6)[0]
    num_blocks = struct.unpack_from("<I", data, 0x10)[0]

    finf = b""
    sheets: Sheets | None = None
    widths: dict[int, tuple[int, int, int]] = {}
    cmap: dict[int, int] = {}
    cmap_blocks: list[tuple[int, int, int]] = []
    extra: list[tuple[bytes, bytes]] = []

    offset = header_size
    for _ in range(num_blocks):
        magic = data[offset : offset + 4]
        size = struct.unpack_from("<I", data, offset + 4)[0]
        body = data[offset + BLOCK_HEADER : offset + size]
        if magic == b"FINF":
            finf = body
        elif magic == b"TGLP":
            sheets = _parse_tglp(data, offset + BLOCK_HEADER)
        elif magic == b"CWDH":
            widths |= _parse_cwdh(body)
        elif magic == b"CMAP":
            cmap_blocks.append(struct.unpack_from("<HHH", body, 0))
            cmap |= _parse_cmap(body)
        else:
            extra.append((magic, body))
        if size <= 0:
            raise ValueError(f"zero-sized {magic!r} block at 0x{offset:X}")
        offset += size

    if not finf or sheets is None:
        raise ValueError("BCFNT without a FINF or a TGLP block")
    if sorted(widths) != list(range(len(widths))):
        raise ValueError("CWDH blocks do not cover a contiguous glyph range from 0")

    return Font(
        version=version,
        finf=finf,
        sheets=sheets,
        widths=[widths[i] for i in range(len(widths))],
        cmap=cmap,
        cmap_blocks=cmap_blocks,
        blocks=extra,
    )


def build(font: Font) -> bytes:
    """Serialise a Font back into a file. Round-trips an unmodified Font byte for byte."""
    # TGLP is the second block, so where its body lands depends only on FINF's length.
    tglp = _build_tglp(font.sheets, HEADER_SIZE + BLOCK_HEADER + len(font.finf) + BLOCK_HEADER)
    cwdh = _build_cwdh(font.widths)
    cmaps = _build_cmaps(font.cmap, font.cmap_blocks)

    # Block order is fixed: FINF, TGLP, CWDH, then the CMAP chain, then anything else.
    sized = [(b"FINF", len(font.finf))] + [
        (magic, len(payload)) for magic, payload in [(b"TGLP", tglp), (b"CWDH", cwdh)] + cmaps
    ]
    sized += [(magic, len(payload)) for magic, payload in font.blocks]

    starts: dict[int, int] = {}
    position = HEADER_SIZE
    for index, (_, length) in enumerate(sized):
        starts[index] = position
        position += BLOCK_HEADER + length
    file_size = position

    # FINF holds pointers to the bodies of the three blocks that follow it.
    finf = bytearray(font.finf)
    struct.pack_into(
        "<III",
        finf,
        8,
        starts[1] + BLOCK_HEADER,  # TGLP
        starts[2] + BLOCK_HEADER,  # CWDH
        starts[3] + BLOCK_HEADER,  # first CMAP
    )

    # Each CWDH / CMAP block points at the next one in its chain, 0 for the last.
    payloads = [bytes(finf), tglp, cwdh] + [payload for _, payload in cmaps]
    payloads += [payload for _, payload in font.blocks]
    payloads[2] = _with_next(payloads[2], 4, 0)  # a single CWDH block ends the chain
    for i in range(len(cmaps)):
        index = 3 + i
        following = starts[index + 1] + BLOCK_HEADER if i + 1 < len(cmaps) else 0
        payloads[index] = _with_next(payloads[index], 8, following)

    out = bytearray()
    out += MAGIC
    out += struct.pack("<HHIII", 0xFEFF, HEADER_SIZE, font.version, file_size, len(sized))
    for (magic, _), payload in zip(sized, payloads):
        out += magic + struct.pack("<I", BLOCK_HEADER + len(payload)) + payload
    return bytes(out)


def add_glyphs(font: Font, glyphs: dict[int, tuple[list[list[tuple[int, int]]], int, int, int]]) -> None:
    """Append code points: {code point: (rows of (luminance, alpha), left, glyph width, char width)}.

    The pixels go into the cells past the last glyph, so the texture keeps its size and
    the sheet count stays what the FINF-side reader expects.
    """
    free = font.sheets.capacity - len(font.widths)
    if len(glyphs) > free:
        raise ValueError(f"{len(glyphs)} glyphs do not fit into {free} free cells")

    for code, (rows, left, glyph_width, char_width) in sorted(glyphs.items()):
        if code in font.cmap:
            raise ValueError(f"U+{code:04X} is already in the font")
        index = len(font.widths)
        _draw_cell(font.sheets, index, rows)
        font.widths.append((left, glyph_width, char_width))
        font.cmap[code] = index


def cell_size(font: Font) -> tuple[int, int]:
    return font.sheets.cell_width, font.sheets.cell_height


def glyph_rows(font: Font, code: int) -> list[list[tuple[int, int]]]:
    """One glyph's cell as cell_height rows of (luminance, alpha), each 0-15."""
    sheets = font.sheets
    plane, x0, y0 = sheets.cell_origin(font.cmap[code])
    return [
        [(plane[y0 + y][x0 + x] >> 4, plane[y0 + y][x0 + x] & 0x0F) for x in range(sheets.cell_width)]
        for y in range(sheets.cell_height)
    ]


def _draw_cell(sheets: Sheets, index: int, rows: list[list[tuple[int, int]]]) -> None:
    if len(rows) != sheets.cell_height or any(len(row) != sheets.cell_width for row in rows):
        raise ValueError(f"glyph must be {sheets.cell_width}x{sheets.cell_height}")
    plane, x0, y0 = sheets.cell_origin(index)
    for y, row in enumerate(rows):
        for x, (luminance, alpha) in enumerate(row):
            plane[y0 + y][x0 + x] = ((luminance & 0x0F) << 4) | (alpha & 0x0F) if alpha else 0x00


def _parse_tglp(data: bytes, pos: int) -> Sheets:
    cell_width, cell_height, baseline, max_char_width = struct.unpack_from("<BBBB", data, pos)
    sheet_size, count, image_format, columns, rows, width, height, sheet_offset = struct.unpack_from(
        "<IHHHHHHI", data, pos + 4
    )
    if image_format != FORMAT_LA4:
        raise ValueError(f"unsupported sheet format {image_format}, only LA4 (9) is handled")
    if sheet_size != width * height:
        raise ValueError("sheet size does not match a one-byte-per-pixel format")

    planes = [
        _detile(data[sheet_offset + i * sheet_size : sheet_offset + (i + 1) * sheet_size], width, height)
        for i in range(count)
    ]
    return Sheets(
        cell_width=cell_width,
        cell_height=cell_height,
        baseline=baseline,
        max_char_width=max_char_width,
        image_format=image_format,
        columns=columns,
        rows=rows,
        width=width,
        height=height,
        planes=planes,
    )


def _build_tglp(sheets: Sheets, body_offset: int) -> bytes:
    """`body_offset` is where this block's body lands in the file - the pixel offset
    stored inside it is absolute, and the pixels themselves are 0x80-aligned."""
    head = struct.pack(
        "<BBBBIHHHHHH",
        sheets.cell_width,
        sheets.cell_height,
        sheets.baseline,
        sheets.max_char_width,
        sheets.width * sheets.height,
        len(sheets.planes),
        sheets.image_format,
        sheets.columns,
        sheets.rows,
        sheets.width,
        sheets.height,
    )
    pixels = b"".join(_tile(plane, sheets.width, sheets.height) for plane in sheets.planes)
    header_end = body_offset + len(head) + 4
    data_offset = (header_end + 0x7F) & ~0x7F
    return head + struct.pack("<I", data_offset) + b"\0" * (data_offset - header_end) + pixels


def _build_cwdh(widths: list[tuple[int, int, int]]) -> bytes:
    body = struct.pack("<HHI", 0, len(widths) - 1, 0)
    body += b"".join(struct.pack("<bBB", *entry) for entry in widths)
    return _pad(body)


def _parse_cwdh(body: bytes) -> dict[int, tuple[int, int, int]]:
    start, end = struct.unpack_from("<HH", body, 0)
    return {
        start + i: struct.unpack_from("<bBB", body, 8 + i * 3) for i in range(end - start + 1)
    }


def _parse_cmap(body: bytes) -> dict[int, int]:
    code_begin, code_end, method = struct.unpack_from("<HHH", body, 0)
    data = body[12:]
    codes: dict[int, int] = {}
    if method == MAP_DIRECT:
        first = struct.unpack_from("<H", data, 0)[0]
        if first != 0xFFFF:
            for i, code in enumerate(range(code_begin, code_end + 1)):
                codes[code] = first + i
    elif method == MAP_TABLE:
        for i in range(code_end - code_begin + 1):
            index = struct.unpack_from("<H", data, i * 2)[0]
            if index != 0xFFFF:
                codes[code_begin + i] = index
    elif method == MAP_SCAN:
        count = struct.unpack_from("<H", data, 0)[0]
        for i in range(count):
            code, index = struct.unpack_from("<HH", data, 2 + i * 4)
            if index != 0xFFFF:
                codes[code] = index
    else:
        raise ValueError(f"unknown CMAP encoding {method}")
    return codes


def _build_cmaps(cmap: dict[int, int], layout: list[tuple[int, int, int]]) -> list[tuple[bytes, bytes]]:
    """Re-encode the mapping into the same chain of blocks the original file used.

    The HUD font keeps a U+0028..U+0078 table block for the Latin run and a catch-all scan
    block for everything scattered around it. Reusing that layout is what makes an
    untouched font rebuild byte for byte; a code point added later lands in the first block
    whose range covers it, which for Cyrillic is the scan block.
    """
    if not cmap:
        raise ValueError("a font with no code points")
    if not layout:
        raise ValueError("a font with no CMAP block")

    unplaced = dict(cmap)
    out: list[tuple[bytes, bytes]] = []
    for begin, end, method in layout:
        taken = {code: index for code, index in unplaced.items() if begin <= code <= end}
        for code in taken:
            del unplaced[code]

        body = struct.pack("<HHHHI", begin, end, method, 0, 0)
        if method == MAP_DIRECT:
            first = taken[begin] if begin in taken else 0xFFFF
            if taken and any(taken.get(begin + i) != first + i for i in range(end - begin + 1)):
                raise ValueError(f"U+{begin:04X}..U+{end:04X} is no longer a direct run")
            body += struct.pack("<H", first)
        elif method == MAP_TABLE:
            body += b"".join(
                struct.pack("<H", taken.get(code, 0xFFFF)) for code in range(begin, end + 1)
            )
        elif method == MAP_SCAN:
            body += struct.pack("<H", len(taken))
            body += b"".join(struct.pack("<HH", code, taken[code]) for code in sorted(taken))
        else:
            raise ValueError(f"unknown CMAP encoding {method}")
        out.append((b"CMAP", _pad(body)))

    if unplaced:
        missed = " ".join(f"U+{code:04X}" for code in sorted(unplaced))
        raise ValueError(f"no CMAP block covers {missed}")
    return out


def _with_next(body: bytes, offset: int, value: int) -> bytes:
    out = bytearray(body)
    struct.pack_into("<I", out, offset, value)
    return bytes(out)


def _pad(body: bytes) -> bytes:
    """Blocks are 4-byte aligned including their 8-byte header."""
    return body + b"\0" * (-(len(body) + BLOCK_HEADER) % 4)


def _morton(index: int) -> tuple[int, int]:
    """Position of the `index`-th byte inside an 8x8 tile."""
    x = (index & 1) | ((index >> 1) & 2) | ((index >> 2) & 4)
    y = ((index >> 1) & 1) | ((index >> 2) & 2) | ((index >> 3) & 4)
    return x, y


def _detile(data: bytes, width: int, height: int) -> list[bytearray]:
    plane = [bytearray(width) for _ in range(height)]
    at = 0
    for ty in range(0, height, 8):
        for tx in range(0, width, 8):
            for i in range(64):
                x, y = _morton(i)
                plane[ty + y][tx + x] = data[at + i]
            at += 64
    return plane


def _tile(plane: list[bytearray], width: int, height: int) -> bytes:
    out = bytearray(width * height)
    at = 0
    for ty in range(0, height, 8):
        for tx in range(0, width, 8):
            for i in range(64):
                x, y = _morton(i)
                out[at + i] = plane[ty + y][tx + x]
            at += 64
    return bytes(out)
