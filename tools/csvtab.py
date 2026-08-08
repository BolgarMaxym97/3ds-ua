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

The build writes the column of the language it replaces - 11 for `from-ru`, 4 for `from-en`,
see tools/variant.py. Those indices hold in the shorter rows too: Japan's have no Korean or
Chinese columns at all, so a row is 13 fields there and 15 elsewhere, but nothing before
column 12 moves.
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


# --- Piece2_PanelInfo.csv ------------------------------------------------------------
#
# The names of the Puzzle Swap panels, in the same param/ folder and the same UTF-16 CRLF
# encoding as the two tables above - but a different shape, so it needs its own reader:
#
#   #パネルID,分割タイプ,入手パターン,,,,,,,,,,,
#   1,0,0,,,,,,,,,,,
#   #パネル名,US_English,US_French,...,EU_Russian,
#   マリオ＆クッパ,Mario and Bowser,...,Марио и Боузер,
#
# Nothing is quoted here, so a field is whatever lies between two commas and splitting on
# "," round-trips exactly - the trailing comma included, because the last field is empty.
# Every panel carries its own pair of headers, which is what makes the language column
# findable by name instead of by a fixed index: EU_Russian is 12 here and 11 in region.csv,
# and hardcoding either number twice is how they drift apart. Two of the seven headers are
# damaged in Nintendo's own file (`Mario and Bowser` and `TUS_English` in place of
# `US_English`), but only in that first column - every EU_* name is intact in all seven.

PANEL_ID_HEADER = "#パネルID"
PANEL_NAME_HEADER = "#パネル名"


@dataclass
class Panel:
    """One panel: where its name line is, and which column each language sits in."""

    panel_id: str
    line: int
    columns: dict[str, int]


class PanelTable:
    """Piece2_PanelInfo.csv, re-rendering byte-identically until something is changed."""

    def __init__(self, data: bytes) -> None:
        text = data.decode("utf-16")
        self.trailing = text.endswith("\r\n")
        lines = text.split("\r\n")
        if self.trailing:
            lines = lines[:-1]
        self.lines = [line.split(",") for line in lines]
        self.panels = _panels(self.lines)

    def name(self, panel: Panel, lang: str) -> str:
        return self.lines[panel.line][panel.columns[lang]]

    def set_name(self, panel: Panel, lang: str, text: str) -> None:
        self.lines[panel.line][panel.columns[lang]] = text

    def build(self) -> bytes:
        text = "\r\n".join(",".join(fields) for fields in self.lines)
        if self.trailing:
            text += "\r\n"
        return text.encode("utf-16")


def _panels(lines: list[list[str]]) -> dict[str, Panel]:
    """Walk the header/value pairs and pin each panel's name line to its id."""
    panels: dict[str, Panel] = {}
    panel_id: str | None = None
    columns: dict[str, int] = {}
    expect: str | None = None

    for index, fields in enumerate(lines):
        head = fields[0]
        if head == PANEL_ID_HEADER:
            expect = "id"
        elif head == PANEL_NAME_HEADER:
            columns = {name: at for at, name in enumerate(fields) if at and name}
            expect = "name"
        elif expect == "id":
            panel_id = fields[0]
            expect = None
        elif expect == "name":
            if panel_id is None:
                raise ValueError(f"line {index}: a panel name before any panel id")
            panels[panel_id] = Panel(panel_id, index, columns)
            expect = None
    return panels


def load_panels(path: Path) -> PanelTable:
    return PanelTable(path.read_bytes())
