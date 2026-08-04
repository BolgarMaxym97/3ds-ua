"""Read the news module savedata (notifications) and match it against the HOME Menu tips.

The Notifications applet does not render text from romfs: the HOME Menu copies each
built-in tip (`new_tips0`..`new_tips16` in `menu_msbt`) into the news module savedata
through `news:s AddNotification`. That copy is frozen at delivery time, which is why
tips delivered before the mod stay Russian no matter what LayeredFS serves.

Savedata layout (3dbrew, News Services):
    news.db        0x2BD0 bytes: 0x10 header + 100 notification headers of 0x70
    newsXXX.txt    message body, UTF-16LE, up to 0x1780 bytes (XXX = decimal index)
    newsXXX.mpo    image, up to 0x10000 bytes

Usage:
    python3 tools/newsdb.py work/newsdb/00000000        # raw DISA image, what GodMode9 gives
    python3 tools/newsdb.py work/newsdb/00000000 --hook # also check the patch's own table
    python3 tools/newsdb.py work/newsdb                 # folder with news.db + newsXXX.txt
    python3 tools/newsdb.py work/newsdb/news.db         # headers only
    python3 tools/newsdb.py work/newsdb/00000000 --json tmp/newsdb.json

Dumping it with GodMode9: `1:` -> `data` -> `<ID0>` -> `sysdata` -> `00010035`, then A on
`00000000` -> `Copy to 0:/gm9/out`. That is the whole savedata as a DISA image, which is
what the scanning path below reads; the inner filesystem is not walked, the fixed-size
`news.db` is located by its shape instead. Mounting the image in GodMode9 and copying the
files out works too, and then the folder path gives message bodies per slot as well.

`--hook` is the check worth running on a fresh dump: it recognises each stored notification
the way the HOME Menu patch does at runtime, so a mismatch shows up here rather than on the
console. See tools/news_tips.py and _news_hook() in tools/luma_hook.py.
"""

from __future__ import annotations

import argparse
import json
import re
import struct
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lz11 import decompress  # noqa: E402
from msbt import parse as parse_msbt  # noqa: E402
from news_tips import hash_text  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
HOME_MENU_MSBT = ROOT / "work/0004003000009802/romfs/message/EU_Russian/menu_msbt_LZ.bin"
HOME_MENU_JSON = ROOT / "src/strings/home_menu/message__menu_msbt_LZ.json"

DB_SIZE = 0x2BD0
DB_HEADER_SIZE = 0x10
RECORD_SIZE = 0x70
RECORD_COUNT = 100
TITLE_SIZE = 0x40
MESSAGE_MAX = 0x1780

# HOME Menu title IDs; the EUR one is what we patch, the others help identify foreign dumps.
HOME_MENU_TIDS = {
    0x0004003000009802: "HOME Menu EUR",
    0x0004003000008202: "HOME Menu JPN",
    0x0004003000008F02: "HOME Menu USA",
    0x000400300000A102: "HOME Menu KOR",
    0x000400300000B102: "HOME Menu TWN",
}

TAG_RE = re.compile(r"\{/?t:[^}]*\}")
EPOCH_2000 = datetime(2000, 1, 1, tzinfo=timezone.utc)
# Milliseconds since 2000 for 2004 and 2040 - a date outside that is not a real timestamp.
SANE_DATES = (126_230_400_000, 1_262_304_000_000)


@dataclass
class Notification:
    index: int
    valid: bool
    unread: bool
    jpeg: bool
    spotpass: bool
    opted_out: bool
    browser_link: bool
    unknown: int
    program_id: int
    ns_data_id: int
    version: int
    jump_param: int
    datetime_ms: int
    title: str
    message: str = ""
    message_bytes: int = 0
    image_bytes: int = 0
    matched_label: str | None = None
    matched_by: str | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def program_name(self) -> str:
        return HOME_MENU_TIDS.get(self.program_id, f"{self.program_id:016X}")

    @property
    def date(self) -> str:
        if not self.datetime_ms:
            return "-"
        return (EPOCH_2000 + timedelta(milliseconds=self.datetime_ms)).strftime("%Y-%m-%d %H:%M")


def parse_record(data: bytes, index: int) -> Notification:
    (
        valid,
        unread,
        jpeg,
        spotpass,
        opted_out,
        browser_link,
        unknown,
        _padding,
        program_id,
        ns_data_id,
        version,
        jump_param,
    ) = struct.unpack_from("<8B Q I I Q", data, 0)
    datetime_ms = struct.unpack_from("<Q", data, 0x28)[0]
    title = decode_utf16(data[0x30 : 0x30 + TITLE_SIZE])
    return Notification(
        index=index,
        valid=bool(valid),
        unread=bool(unread),
        jpeg=bool(jpeg),
        spotpass=bool(spotpass),
        opted_out=bool(opted_out),
        browser_link=bool(browser_link),
        unknown=unknown,
        program_id=program_id,
        ns_data_id=ns_data_id,
        version=version,
        jump_param=jump_param,
        datetime_ms=datetime_ms,
        title=title,
    )


def decode_utf16(raw: bytes) -> str:
    """UTF-16LE up to the first NUL; the 3DS pads the rest of the field with garbage."""
    end = len(raw) - len(raw) % 2
    text = raw[:end].decode("utf-16-le", errors="replace")
    return text.split("\x00", 1)[0]


def parse_db(data: bytes) -> tuple[dict[str, int], list[Notification]]:
    if len(data) < DB_SIZE:
        raise ValueError(f"news.db is {len(data)} bytes, expected {DB_SIZE}")
    header = {"valid": data[0], "flags": data[1]}
    records = [
        parse_record(data[off : off + RECORD_SIZE], i)
        for i, off in enumerate(
            range(DB_HEADER_SIZE, DB_HEADER_SIZE + RECORD_COUNT * RECORD_SIZE, RECORD_SIZE)
        )
    ]
    return header, records


def load_folder(folder: Path) -> tuple[dict[str, int], list[Notification]]:
    db = next((p for p in folder.rglob("news.db")), None)
    if db is None:
        raise SystemExit(f"{folder}: no news.db inside (mount the savedata in GodMode9 first)")
    header, records = parse_db(db.read_bytes())
    for note in records:
        txt = db.parent / f"news{note.index:03d}.txt"
        mpo = db.parent / f"news{note.index:03d}.mpo"
        if txt.is_file():
            raw = txt.read_bytes()
            note.message_bytes = len(raw)
            note.message = decode_utf16(raw)
            if len(raw) > MESSAGE_MAX:
                note.warnings.append(f"message {len(raw)} > {MESSAGE_MAX} bytes")
        elif note.valid:
            note.warnings.append("valid header, no newsXXX.txt")
        if mpo.is_file():
            note.image_bytes = mpo.stat().st_size
    return header, records


def find_db(data: bytes, align: int = 0x1000) -> list[tuple[int, dict[str, int], list[Notification]]]:
    """Locate news.db copies inside a raw DISA image without walking the inner filesystem.

    The db is a fixed 0x2BD0-byte blob that starts on a block boundary, so the aligned
    offsets are scored instead: a valid header plus records that all look like records.
    Slots are not packed - a used console has them scattered across the 100 indices, so
    only the valid ones are checked. DPFS keeps two copies, so several hits are normal.
    """
    hits = []
    for off in range(0, len(data) - DB_SIZE, align):
        if data[off] != 1 or any(data[off + 2 : off + DB_HEADER_SIZE]):
            continue
        try:
            header, records = parse_db(data[off : off + DB_SIZE])
        except ValueError:
            continue
        used = [n for n in records if n.valid]
        if used and all(plausible(n) for n in used):
            hits.append((off, header, records))
    return hits


def plausible(note: Notification) -> bool:
    """A parsed record that could not have come from anything but news.db."""
    sane_date = SANE_DATES[0] < note.datetime_ms < SANE_DATES[1]
    return bool(note.title) and sane_date and note.unknown <= 1 and note.opted_out <= 1


def scan_image(data: bytes) -> list[Notification]:
    """Best-effort: find notification headers inside a raw DISA image (no FAT parsing).

    A record is accepted when the programID at +0x8 is a known HOME Menu title and the
    flag bytes look sane. DPFS keeps two copies of the savedata, so the same record shows
    up twice - identical hits are collapsed and the offsets are listed in the warning.
    """
    seen: dict[bytes, Notification] = {}
    for tid in HOME_MENU_TIDS:
        needle = struct.pack("<Q", tid)
        start = 0
        while (hit := data.find(needle, start)) != -1:
            start = hit + 1
            base = hit - 8
            if base < 0 or base + RECORD_SIZE > len(data):
                continue
            record = data[base : base + RECORD_SIZE]
            if record[0] not in (0, 1) or record[1] not in (0, 1) or record[2] not in (0, 1):
                continue
            note = parse_record(record, index=-1)
            if not note.title:
                continue
            if (previous := seen.get(record)) is not None:
                previous.warnings[0] += f", 0x{base:X}"
                continue
            note.warnings.append(f"scanned at image offsets 0x{base:X}")
            seen[record] = note
    return list(seen.values())


def scan_bodies(data: bytes, tips: dict[str, dict[str, str]]) -> dict[str, dict[str, object]]:
    """Find the newsXXX.txt bodies inside a raw image by looking for the Russian text.

    The bodies live in their own files in the inner filesystem, so a header scan cannot
    reach them. Searching for the known Russian tip text finds them anyway and shows how
    Nintendo stored it (tags stripped or not, byte length, how many copies).
    """
    found: dict[str, dict[str, object]] = {}
    for label, entry in sorted(tips.items()):
        if "_title" in label or not entry.get("ru"):
            continue
        stripped = TAG_RE.sub("", entry["ru"])
        # A prefix hit is enough to locate the body; the stored text is then read back so a
        # difference from the MSBT (tags kept, text truncated) becomes visible.
        prefix = stripped[:24]
        if len(prefix) < 8:
            continue
        offsets = []
        needle = prefix.encode("utf-16-le")
        start = 0
        while (hit := data.find(needle, start)) != -1:
            offsets.append(hit)
            start = hit + 2
        if not offsets:
            continue
        stored = decode_utf16(data[offsets[0] : offsets[0] + MESSAGE_MAX])
        found[label] = {
            "bytes": len(stored.encode("utf-16-le")) + 2,
            "copies": len(offsets),
            "offsets": [f"0x{off:X}" for off in offsets],
            "exact": stored == stripped,
            "keeps_tags": stored == entry["ru"],
            "stored": stored,
        }
    return found


def load_tips() -> dict[str, dict[str, str]]:
    """-> {label: {"ru": ..., "ua": ...}} for every new_tips* label that has text."""
    tips: dict[str, dict[str, str]] = {}
    if HOME_MENU_MSBT.is_file():
        msbt = parse_msbt(decompress(HOME_MENU_MSBT.read_bytes()))
        for label, index in msbt.labels.items():
            if label.startswith("new_tips") and msbt.texts[index]:
                tips.setdefault(label, {})["ru"] = msbt.texts[index]
    if HOME_MENU_JSON.is_file():
        entries = json.loads(HOME_MENU_JSON.read_text(encoding="utf-8"))
        for label, entry in entries.items():
            if label.startswith("new_tips") and entry.get("ua"):
                tips.setdefault(label, {})["ua"] = entry["ua"]
    return tips


def normalize(text: str) -> str:
    """Strip MSBT style tags and whitespace so stored text can be compared with the MSBT."""
    return re.sub(r"\s+", " ", TAG_RE.sub("", text)).strip()


def match_tips(records: list[Notification], tips: dict[str, dict[str, str]]) -> None:
    by_body = {normalize(v["ru"]): k for k, v in tips.items() if v.get("ru") and "_title" not in k}
    by_title = {
        normalize(v["ru"]): k for k, v in tips.items() if v.get("ru") and k.endswith("_title")
    }
    for note in records:
        if not note.valid:
            continue
        if label := by_body.get(normalize(note.message)):
            note.matched_label, note.matched_by = label, "body"
        elif label := by_title.get(normalize(note.title)):
            note.matched_label, note.matched_by = label.removesuffix("_title"), "title"


def report_bodies(bodies: dict[str, dict[str, object]]) -> None:
    print()
    print(f"tip bodies found in the image: {len(bodies)}")
    for label, info in bodies.items():
        if info["exact"]:
            state = "exact MSBT text, style tags stripped"
        elif info["keeps_tags"]:
            state = "exact MSBT text, style tags kept"
        else:
            state = "differs from MSBT"
        print(f"  {label:<16} {info['bytes']:>5} bytes  x{info['copies']}  {state}")
        print(f"      at {', '.join(info['offsets'][:4])}")
        if not info["exact"] and not info["keeps_tags"]:
            print(f"      stored: {info['stored'][:120]!r}")


def report(header: dict[str, int] | None, records: list[Notification], tips: dict) -> None:
    if header is not None:
        print(f"news.db header: valid={header['valid']} flags=0x{header['flags']:02X} "
              f"(bit0 unread, bit1 CECD)")
    used = [n for n in records if n.valid]
    print(f"notifications: {len(used)} valid of {len(records) if header else len(records)}")
    print()
    print(f"{'idx':>3} {'prog':<16} {'jumpParam':>18} {'nsData':>8} {'date':<16} "
          f"{'spot':>4} {'msg':>6} {'img':>7} {'tip':<16} title")
    for note in used:
        print(
            f"{note.index:>3} {note.program_name:<16} 0x{note.jump_param:016X} "
            f"{note.ns_data_id:>8} {note.date:<16} {int(note.spotpass):>4} "
            f"{note.message_bytes:>6} {note.image_bytes:>7} "
            f"{note.matched_label or '-':<16} {note.title!r}"
        )
        for warning in note.warnings:
            print(f"      !! {warning}")

    matched = {n.matched_label for n in used if n.matched_label}
    print()
    print(f"matched HOME Menu tips: {len(matched)} of {len({k for k in tips if '_title' not in k})}")
    missing_ua = sorted(label for label in matched if not tips.get(label, {}).get("ua"))
    if missing_ua:
        print(f"!! stored but not translated yet: {', '.join(missing_ua)}")

    # jumpParam is the cheapest possible key for the code hook - report whether it is one.
    params = {n.jump_param for n in used if n.matched_label}
    if params and len(params) == len([n for n in used if n.matched_label]):
        print("jumpParam is unique per tip -> the hook can key on it")
    elif params == {0}:
        print("jumpParam is always 0 -> the hook must match on the stored Russian text")


def report_hook(records: list[Notification]) -> None:
    """Check the dump against the table the HOME Menu patch was built with.

    The patch recognises a notification by a hash of its stored title, so this is the one
    test that matters before trusting it on hardware: every Russian tip in the database has
    to be reachable from the table, and the label it resolves to has to be the right tip.
    """
    from build import load_homoglyphs, news_tip_table  # late: build imports half the toolbox

    entries, _ = news_tip_table(load_homoglyphs())
    by_hash = {int(entry["ru_hash"]): entry for entry in entries}

    print()
    print(f"hook table: {len(entries)} tips")
    print(f"{'slot':>4} {'hash':>10}  {'tip':<16} title")
    unmatched = 0
    for note in (n for n in records if n.valid):
        digest = hash_text(note.title)
        entry = by_hash.get(digest)
        label = str(entry["body_label"]) if entry else "-- no entry --"
        print(f"{note.index:>4} 0x{digest:08X}  {label:<16} {note.title!r}")
        unmatched += entry is None

    if unmatched:
        print(f"!! {unmatched} notifications the patch would leave alone - Nintendo's own "
              f"SpotPass messages are expected here, a Russian tip is not")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", type=Path, help="savedata folder, news.db, or raw DISA image")
    ap.add_argument("--json", type=Path, help="also write the parsed notifications here")
    ap.add_argument(
        "--hook",
        action="store_true",
        help="also check the dump against the table the HOME Menu patch is built with",
    )
    args = ap.parse_args()

    tips = load_tips()
    if not tips:
        print(f"!! no tips loaded - is {HOME_MENU_MSBT} missing?", file=sys.stderr)

    header: dict[str, int] | None = None
    bodies: dict[str, dict[str, object]] = {}
    if args.path.is_dir():
        header, records = load_folder(args.path)
    else:
        data = args.path.read_bytes()
        if len(data) == DB_SIZE:
            header, records = parse_db(data)
        else:
            print(f"{args.path.name}: {len(data)} bytes, not a bare news.db - scanning")
            copies = find_db(data)
            if copies:
                offsets = ", ".join(f"0x{off:X}" for off, _, _ in copies)
                print(f"news.db copies at {offsets} - using the one with the most notifications")
                _, header, records = max(copies, key=lambda c: sum(n.valid for n in c[2]))
            else:
                print("no news.db found - falling back to a header scan")
                records = scan_image(data)
            bodies = scan_bodies(data, tips)

    match_tips(records, tips)
    report(header, records, tips)
    if bodies:
        report_bodies(bodies)
    if args.hook:
        report_hook(records)

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "notifications": [asdict(n) for n in records if n.valid],
            "bodies": bodies,
        }
        args.json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nwrote {args.json} ({len(payload['notifications'])} notifications)")


if __name__ == "__main__":
    main()
