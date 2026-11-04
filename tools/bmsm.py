"""Read and write the `.bmsm` message tables of the StreetPass Mii Plaza update.

The update (0004000E00022800, v14.7.0) keeps every text of the plaza and its fifteen games
in `romfs/message/<lang>/message/{park,minigame,system}/*.bmsm`, one table per screen or
game, in a format of its own rather than MSBT:

    u32  row count
    u32  column count - 6 in every file the update ships
    then row count x column count fields, one after the other

A field is either a NUL-terminated ASCII string, or a UTF-16LE string led by the FF FE byte
order mark and ended by a 0000 code unit. Between two fields there is a run of zero bytes,
from none to six, with no rule an offset or a length explains - the reader cannot depend on
it, and does not: every field starts at an even offset, and a field never starts with a
zero byte, so the next field is simply the next non-zero byte. That is how this module reads
the 304 shipped files (8 languages x 38 tables), and every one comes out as exactly
rows x columns fields.

The six columns:

    0 id        `hat_shop_00`, the key the code looks the row up by
    1 style     `std_green_mid` - colour and size, defined in meet.bmss / meet.bmsc
    2 text      the UTF-16 string, with inline tags such as [System:Color name="..."]
    3, 4        small numbers, as ASCII
    5           `nil` or another ASCII value

The first row of a file is often a defaults row (`select_text`, ...), shaped like the rest.

`build` writes the smallest file the reader takes: each field padded with zeros to the next
even offset and nothing more. The padding of the original is not reproduced because there
is nothing to reproduce it from; `parse(build(parse(x)))` equals `parse(x)` for every file.

Usage:
    python3 tools/bmsm.py --check work/0004000E00022800/romfs/message   # round-trip all
    python3 tools/bmsm.py FILE.bmsm                                     # print the texts
"""

from __future__ import annotations

import argparse
import re
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

BOM = b"\xff\xfe"
TEXT = 2
TAG = re.compile(r"\[[^\]]*\]")


def translatable(text: str) -> bool:
    """Whether a text has a letter outside its [tags] - `nil` is a placeholder, not a word."""
    rest = TAG.sub("", text)
    return rest != "nil" and any(ch.isalpha() for ch in rest)


@dataclass
class Field:
    value: str
    utf16: bool


@dataclass
class Table:
    columns: int
    rows: list[list[Field]] = field(default_factory=list)

    def keyed_rows(self) -> list[tuple[str, list[Field]]]:
        """(key, row) for every row: the id, or `id#2`, `id#3` for a repeated one.

        Seven tables repeat an id (mgFlo has two `title` rows); the code finds the first
        one, but the text of the second is still in the file, so it gets a key of its own.
        """
        seen: dict[str, int] = {}
        out = []
        for row in self.rows:
            ident = row[0].value
            seen[ident] = seen.get(ident, 0) + 1
            out.append((ident if seen[ident] == 1 else f"{ident}#{seen[ident]}", row))
        return out

    def texts(self) -> dict[str, str]:
        """{key: text} for the rows whose text column is UTF-16."""
        return {key: row[TEXT].value for key, row in self.keyed_rows() if row[TEXT].utf16}


def parse(data: bytes) -> Table:
    count, columns = struct.unpack_from("<II", data, 0)
    pos = 8
    fields: list[Field] = []
    while True:
        while pos < len(data) and data[pos] == 0:
            pos += 1
        if pos >= len(data):
            break
        if data[pos:pos + 2] == BOM:
            end = pos + 2
            while data[end:end + 2] != b"\0\0":
                if end + 2 > len(data):
                    raise ValueError(f"unterminated UTF-16 field at 0x{pos:x}")
                end += 2
            fields.append(Field(data[pos + 2:end].decode("utf-16-le"), True))
            pos = end + 2
        else:
            end = data.index(b"\0", pos)
            fields.append(Field(data[pos:end].decode("ascii"), False))
            pos = end + 1
    if len(fields) != count * columns:
        raise ValueError(f"{len(fields)} fields, the header says {count} x {columns}")
    rows = [fields[i:i + columns] for i in range(0, len(fields), columns)]
    return Table(columns, rows)


def build(table: Table) -> bytes:
    out = bytearray(struct.pack("<II", len(table.rows), table.columns))
    for row in table.rows:
        if len(row) != table.columns:
            raise ValueError(f"row {row[0].value} has {len(row)} fields, not {table.columns}")
        for f in row:
            if not f.value:
                raise ValueError(f"row {row[0].value}: an empty field cannot be told from padding")
            if "\0" in f.value:
                raise ValueError(f"row {row[0].value}: NUL inside a field")
            if len(out) % 2:
                out += b"\0"
            out += BOM + f.value.encode("utf-16-le") + b"\0\0" if f.utf16 else f.value.encode("ascii") + b"\0"
    if len(out) % 2:
        out += b"\0"
    return bytes(out)


def check(root: Path) -> int:
    bad = 0
    files = sorted(root.rglob("*.bmsm"))
    for path in files:
        original = parse(path.read_bytes())
        again = parse(build(original))
        if again != original:
            bad += 1
            print(f"MISMATCH {path}")
    print(f"{len(files) - bad}/{len(files)} round-trip")
    return 1 if bad or not files else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("path", type=Path)
    parser.add_argument("--check", action="store_true", help="round-trip every .bmsm under PATH")
    args = parser.parse_args()
    if args.check:
        sys.exit(check(args.path))
    for key, text in parse(args.path.read_bytes()).texts().items():
        print(f"{key}\t{text!r}")


if __name__ == "__main__":
    main()
