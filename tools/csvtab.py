"""Edit the UTF-16 CSV tables of the StreetPass Mii Plaza in place.

`0004001000022800/romfs/param/` holds the names the StreetPass Map shows for the places
you met people in, as two tables with one column per language:

    country.csv   121 rows, no header
    region.csv    1397 rows plus a `#Country,Country ID,...` header naming the columns

Both are UTF-16 with a BOM, CRLF line endings, every field quoted, and a trailing comma
before the line break - `"Albania","64",...,"阿尔巴尼亚",`. That last empty field is what
makes a normal CSV writer unusable here: `csv` would quote it and change every line. So
this module never re-serialises a row it was not asked to change. It splits a line on
`","`, swaps the one field, and joins it back, which leaves every other byte alone.

Columns, from region.csv's own header:

    0 Country   1 Country ID   2 Simple Address   3 Simple Address ID
    4 English   5 German   6 French   7 Spanish   8 Italian   9 Dutch
    10 Portuguese   11 Russian   12 Japanese   13 Korean   14 SimpChinese
    15 TradChinese

Russian is 11 in both files, and stays 11 in the shorter rows: Japan's have no Korean or
Chinese columns at all, so a row is 13 fields there and 15 elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

RUSSIAN = 11
COUNTRY = 0
COUNTRY_ID = 1
ADDRESS = 2
ADDRESS_ID = 3
ENGLISH = 4


@dataclass
class Row:
    """One table line: its fields if it is a quoted row, else the raw text."""

    text: str
    fields: list[str] | None

    @property
    def is_row(self) -> bool:
        return self.fields is not None

    def render(self) -> str:
        if self.fields is None:
            return self.text
        return '"' + '","'.join(self.fields) + '",'


class Table:
    """A parsed table that re-renders byte-identically until something is changed."""

    def __init__(self, data: bytes) -> None:
        text = data.decode("utf-16")
        self.trailing = text.endswith("\r\n")
        lines = text.split("\r\n")
        if self.trailing:
            lines = lines[:-1]
        self.rows = [Row(line, _fields(line)) for line in lines]

    def data_rows(self) -> list[Row]:
        return [row for row in self.rows if row.is_row]

    def build(self) -> bytes:
        text = "\r\n".join(row.render() for row in self.rows)
        if self.trailing:
            text += "\r\n"
        return text.encode("utf-16")


def _fields(line: str) -> list[str] | None:
    if not (line.startswith('"') and line.endswith('",')):
        return None
    return line[1:-2].split('","')


def load(path: Path) -> Table:
    return Table(path.read_bytes())


def key_of(row: Row) -> str:
    """The stable identity of a row: country code, and address id in region.csv."""
    fields = row.fields or []
    return f"{fields[COUNTRY_ID]}:{fields[ADDRESS_ID]}"
