"""Read and rewrite the country / region tables of the `area` system data archive.

System Settings does not keep country names in its own romfs. `0004001000022000.dec.code`
mounts the shared data archive `0x0004009B00010402` as `area:` and loads one file whole:

    area:/EU/country_LZ.bin     the country list of the console's region
    area:/EU/<code>_LZ.bin      the sub-region list of country <code>

Both are LZ11 and both are tables of **fixed-size** records, which is what makes them
editable without understanding every field: a name is a 128-byte UTF-16LE slot, so a
translation is written in place and nothing moves.

    country_LZ.bin
        u32                     number of country records
        record[count]           2108 bytes each
        u32                     number of alternate records
        record[count2]          2108 bytes each - a second France and United Kingdom,
                                with a different sub-region count
        u8[count][16]           a duplicate of every record's sort row (see below)
        u8[12]                  trailer

    country record (2108)
        +0x000  u8[3], u8 code  country code (Russia = 100)
        +0x004  u32             number of sub-regions
        +0x008  u32             zero
        +0x00C  16 x u8[128]    names, UTF-16LE, NUL-padded
        +0x80C  u8[16]          sort row
        +0x81C  u8[32]          zero

    <code>_LZ.bin
        u32                     number of sub-regions; also record 0's first field
        record[count + 1]       2072 bytes each; record 0 is the "—" placeholder
        u32                     zero
        u8[count + 1][16]       duplicate sort rows
        u8[12]                  trailer

    region record (2072)
        +0x000  u16, u8 index, u8 code
        +0x004  16 x u8[128]    names
        +0x804  u8[16]          sort row
        +0x814  u32             per-country constant, copied as is

The 16 name slots are the system's language order, so slot 10 is Russian - the same
"block 10" the SMDH patcher writes, and the slot this mod replaces:

    0 JP  1 EN  2 FR  3 DE  4 IT  5 ES  6 ZH  7 KO  8 NL  9 PT  10 RU  11 TW  12-15 spare

The **sort row** is what makes this more than a string swap. Byte j of a record's row is
that record's position in language j's alphabetically sorted list; the records themselves
sit in Japanese order. Rewrite slot 10 without rewriting rank 10 and the console shows
Ukrainian names ordered by the Russian alphabet - «Австралія, Австрія, Азербайджан,
Албанія» happens to survive that, «Німеччина» where «Германия» stood does not. Every row
lives twice, once inside the record and once in the table at the end of the file; both
copies are written.
"""

from __future__ import annotations

import struct
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import lz11

RU_SLOT = 10
NAME_SLOTS = 16
NAME_SIZE = 128
SORT_ROW = 16

COUNTRY_STRIDE = 2108
COUNTRY_NAMES = 0x00C
COUNTRY_SORT = 0x80C

REGION_STRIDE = 2072
REGION_NAMES = 0x004
REGION_SORT = 0x804

# Ukrainian alphabet, for the sort rank. `ь` sorts after `я` in the modern order used by
# DSTU 3966; nothing in these tables ends up depending on that, but the table is the
# authority either way. The apostrophe and space are ignored while comparing, as they are
# in every official localisation of these files.
UA_ALPHABET = "аабвгґдеєжзиіїйклмнопрстуфхцчшщюяь"
UA_ORDER = {ch: i for i, ch in enumerate("абвгґдеєжзиіїйклмнопрстуфхцчшщьюя")}
# Only for the self-test: the Russian column of the untouched dump has to come back
# byte-identical, which it can only do against the Russian alphabet.
RU_ORDER = {ch: i for i, ch in enumerate("абвгдеёжзийклмнопрстуфхцчшщъыьэюя")}


@dataclass
class Record:
    """One country or sub-region: its code, its 16 names and its 16 sort ranks."""

    offset: int
    code: int
    index: int
    sub_count: int
    names: list[str]
    ranks: list[int]
    sort_offset: int = 0
    table_offset: int = 0


@dataclass
class Table:
    """A parsed country or region file, still holding the original bytes."""

    kind: str
    raw: bytearray
    count: int
    records: list[Record] = field(default_factory=list)
    main: int = 0

    @property
    def alternates(self) -> list[Record]:
        return self.records[self.main :]

    @property
    def stride(self) -> int:
        return COUNTRY_STRIDE if self.kind == "country" else REGION_STRIDE

    def by_code(self, code: int) -> Record:
        for record in self.records:
            if record.code == code:
                return record
        raise KeyError(f"no record with country code {code}")


def _name(raw: bytes, offset: int) -> str:
    return raw[offset : offset + NAME_SIZE].decode("utf-16le").split("\0")[0]


def _write_name(raw: bytearray, offset: int, text: str) -> None:
    encoded = text.encode("utf-16le")
    if len(encoded) > NAME_SIZE - 2:
        raise ValueError(f"{text!r} does not fit a {NAME_SIZE}-byte slot")
    raw[offset : offset + NAME_SIZE] = encoded.ljust(NAME_SIZE, b"\0")


def parse(data: bytes, kind: str) -> Table:
    """Parse a decompressed `country` or `region` file. Neither has a magic number, and
    the two record layouts differ, so the caller passes which one it is - `load()` takes
    it from the file name, which is how System Settings tells them apart too."""
    raw = bytearray(data)
    count = struct.unpack_from("<I", raw, 0)[0]
    table = Table(kind, raw, count)

    if kind == "country":
        names_at, sort_at, stride = COUNTRY_NAMES, COUNTRY_SORT, COUNTRY_STRIDE
        total, base = count, 4
    else:
        # A region file has one record more than it counts: index 0 is the "—" row shown
        # before a region has been picked.
        names_at, sort_at, stride = REGION_NAMES, REGION_SORT, REGION_STRIDE
        total, base = count + 1, 4

    # Both kinds can carry a second section of alternate records: another France and
    # United Kingdom in the country list, another set of sub-regions in nine of the region
    # files. Those records have their sort row only inside themselves - the table at the
    # end of the file covers the main section alone - so they are parsed after it and
    # given `table_offset == sort_offset`, which makes writing the row idempotent.
    alt_at = base + total * stride
    alternates = struct.unpack_from("<I", raw, alt_at)[0]
    sort_table = alt_at + 4 + alternates * stride

    table.main = total
    for i in range(total + alternates):
        offset = base + i * stride if i < total else alt_at + 4 + (i - total) * stride
        if table.kind == "country":
            code = raw[offset + 3]
            index = i
            sub = struct.unpack_from("<I", raw, offset + 4)[0]
        else:
            code = raw[offset + 3]
            index = raw[offset + 2]
            sub = 0
        sort_offset = offset + sort_at
        table.records.append(
            Record(
                offset=offset,
                code=code,
                index=index,
                sub_count=sub,
                names=[_name(raw, offset + names_at + s * NAME_SIZE) for s in range(NAME_SLOTS)],
                ranks=list(raw[sort_offset : sort_offset + SORT_ROW]),
                sort_offset=sort_offset,
                table_offset=sort_table + i * SORT_ROW if i < total else sort_offset,
            )
        )
    return table


def ua_key(text: str, order: dict[str, int] | None = None) -> tuple:
    """Collation key for these tables: case-insensitive, accent-folded, letters only.

    Nintendo's own rows follow exactly this rule - `Île-de-France` sits between
    `Guadeloupe` and `Languedoc-Roussillon` in the English column, so the circumflex is
    folded and the hyphen ignored. Cyrillic sorts by the Ukrainian alphabet and ahead of
    Latin, which is how the Russian column is ordered in the originals.
    """
    order = UA_ORDER if order is None else order
    key = []
    for ch in unicodedata.normalize("NFD", text.lower()):
        if unicodedata.combining(ch):
            continue
        if ch in order:
            key.append(order[ch])
        elif ch.isalnum():
            key.append(len(order) + ord(ch))
    return tuple(key)


def set_names(table: Table, names: dict[int, str], slot: int = RU_SLOT, render=None) -> None:
    """Write `names` (keyed by country code, or by sub-region index) into one language slot.

    `render` is applied to the bytes that reach the console while `Record.names` keeps the
    plain text: the glyph substitution this mod needs (`і` -> `i`, `є` -> `ε`) must not
    reach `resort()`, or the list would be alphabetised by the substitutes.
    """
    names_at = COUNTRY_NAMES if table.kind == "country" else REGION_NAMES
    for record in table.records:
        key = record.code if table.kind == "country" else record.index
        if key not in names:
            continue
        record.names[slot] = names[key]
        text = render(names[key]) if render else names[key]
        _write_name(table.raw, record.offset + names_at + slot * NAME_SIZE, text)


def resort(table: Table, slot: int = RU_SLOT, order: dict[str, int] | None = None) -> None:
    """Recompute one language's sort ranks from its names, in every copy of the row.

    Two rankings exist, which is only visible in the nine region files that carry an
    alternates section. France, for instance, ships 27 regions in the main section and a
    28th (Mayotte) in the alternates:

      * a record's **own** row ranks it inside the main section, and the alternate records'
        own rows rank them inside main + alternates;
      * the **table** at the end of the file ranks every main record inside
        main + alternates, so its numbers are one higher past the inserted name.

    In the country files the alternates repeat France and the United Kingdom verbatim, so
    both rankings coincide and each alternate simply carries its twin's row.
    """

    def ranking(records: list[Record]) -> dict[int, int]:
        ranked = sorted((r for r in records if r.names[slot]), key=lambda r: ua_key(r.names[slot], order))
        return {id(r): rank for rank, r in enumerate(ranked)}

    main = table.records[: table.main]
    main_rank = ranking(main)
    # Only a region file's table at the end of the file counts the alternates in; the
    # country file's table repeats the main ranking, which is why France and the United
    # Kingdom do not shift the countries that follow them.
    extended = ranking(table.records) if table.alternates and table.kind == "region" else main_rank

    def write(record: Record, offset: int, rank: int) -> None:
        record.ranks[slot] = rank
        table.raw[offset + slot] = rank

    for record in main:
        if id(record) not in main_rank:  # no name in this language: leave its rank alone
            continue
        write(record, record.sort_offset, main_rank[id(record)])
        table.raw[record.table_offset + slot] = extended[id(record)]


    for record in table.alternates:
        twin = next((r for r in main if r.code == record.code), None)
        if table.kind == "country" and twin is not None and id(twin) in main_rank:
            write(record, record.sort_offset, main_rank[id(twin)])
        elif id(record) in extended:
            write(record, record.sort_offset, extended[id(record)])


def kind_of(path: Path) -> str:
    return "country" if path.name.startswith("country") else "region"


def load(path: Path) -> Table:
    return parse(lz11.decompress(path.read_bytes()), kind_of(path))


def save(table: Table, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(lz11.compress(bytes(table.raw)))


# Files whose sort rows do not follow the plain alphabet of the column, so recomputing
# them cannot reproduce the original: the four Asian region lists are ordered by
# prefecture / province code, and the rest follow a local alphabet ("Ø" after "Z" in
# Norway, "ı" before "i" in Turkey) or sort "St." as "Saint". None of them is a file this
# mod rewrites - the EU country list and the EU region lists we touch all reproduce.
LOCAL_ORDER = {
    "JP/1_LZ.bin",
    "KR/136_LZ.bin",
    "CN/160_LZ.bin",
    "TW/128_LZ.bin",
    "EU/96_LZ.bin",
    "EU/100_LZ.bin",
    "EU/104_LZ.bin",
    "EU/105_LZ.bin",
    "EU/109_LZ.bin",
    "EU/110_LZ.bin",
    "EU/169_LZ.bin",
    "TW/country_LZ.bin",
    "US/10_LZ.bin",
    "US/24_LZ.bin",
    "US/26_LZ.bin",
    "US/174_LZ.bin",
}


def main() -> None:
    """Round-trip every file of the dump and print the Russian slot of the EU list."""
    import sys

    root = Path(__file__).resolve().parent.parent / "work" / "0004009B00010402" / "romfs"
    if len(sys.argv) > 1:
        table = load(Path(sys.argv[1]))
        for record in table.records:
            print(f"code={record.code:3} index={record.index:3} sub={record.sub_count:3} " f"EN={record.names[1]!r:28} RU={record.names[RU_SLOT]!r:26} rank={record.ranks[RU_SLOT]}")
        return

    problems = 0
    for path in sorted(root.rglob("*_LZ.bin")):
        data = lz11.decompress(path.read_bytes())
        table = parse(data, kind_of(path))
        if bytes(table.raw) != data:
            print(f"  ✗ {path.relative_to(root)}: parse mutated the bytes")
            problems += 1
            continue
        # The strongest check there is on both the offsets and the ranking model:
        # recompute the *English* column's ranks from the English names and require every
        # byte of the file to come back the way Nintendo wrote it.
        for slot, order in ((1, None), (RU_SLOT, RU_ORDER)):
            table = parse(data, kind_of(path))
            resort(table, slot=slot, order=order)
            if bytes(table.raw) == data:
                continue
            bad = [i for i, (a, b) in enumerate(zip(table.raw, data)) if a != b]
            names = {"1": "English", str(RU_SLOT): "Russian"}[str(slot)]
            rel = path.relative_to(root).as_posix()
            mark = "-" if rel in LOCAL_ORDER else "✗"
            print(f"  {mark} {rel}: {names} resort changed {len(bad)} bytes, first at 0x{bad[0]:X}")
            problems += rel not in LOCAL_ORDER
        print(f"  {path.relative_to(root)!s:24} {table.kind:8} {len(table.records):3} records, {len(data):7} bytes")
    print("problems:", problems)


if __name__ == "__main__":
    main()
