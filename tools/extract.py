"""Extract text from a romfs dump into JSON files for translation.

Usage:
    python3 tools/extract.py work/0004003000009802 home_menu

Output: src/strings/<title>/<messagedir>__<file>.json
    { "<label>": { "en": "...", "ua": "..." }, ... }

`en` is the original of the slot we replace, which doubles as the fallback for
untranslated strings. To see the other official localisations of a label, run
`python3 tools/fit.py <title> --list <label>`.

Existing `ua` values are preserved, so the script is safe to re-run after a system
update to pull in new or changed originals.
Key order follows TXT2 message order to keep diffs stable.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import msbt as msbt_mod  # noqa: E402
from lz11 import decompress  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def load_msbt(path: Path) -> msbt_mod.Msbt:
    raw = path.read_bytes()
    data = decompress(raw) if path.name.endswith("_LZ.bin") else raw
    return msbt_mod.parse(data)


def extract_dir(romfs: Path, message_dir: str, langs: dict[str, str], out_dir: Path) -> list[tuple[str, int, int]]:
    primary = next(iter(langs.values()))
    primary_path = romfs / message_dir / primary
    if not primary_path.is_dir():
        return []

    results = []
    for file in sorted(primary_path.iterdir()):
        if "msbt" not in file.name:
            continue

        per_lang: dict[str, msbt_mod.Msbt] = {}
        for code, lang_dir in langs.items():
            candidate = romfs / message_dir / lang_dir / file.name
            if candidate.exists():
                per_lang[code] = load_msbt(candidate)

        base = per_lang[next(iter(per_lang))]
        out_file = out_dir / f"{message_dir}__{file.name.split('.')[0]}.json"
        existing = json.loads(out_file.read_text(encoding="utf-8")) if out_file.exists() else {}

        entries: dict[str, dict[str, str]] = {}
        kept = 0
        for index in range(len(base.texts)):
            label = base.label_of(index) or f"__index_{index}"
            entry = {code: data.texts[index] for code, data in per_lang.items() if index < len(data.texts)}
            entry["ua"] = existing.get(label, {}).get("ua", "")
            if entry["ua"]:
                kept += 1
            entries[label] = entry

        out_dir.mkdir(parents=True, exist_ok=True)
        out_file.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        results.append((str(out_file.relative_to(ROOT)), len(entries), kept))

    return results


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("title_dir", help="e.g. work/0004003000009802")
    ap.add_argument("name", help="strings project name, e.g. home_menu")
    ap.add_argument(
        "--lang",
        action="append",
        default=None,
        metavar="code=DIR",
        help="reference language, e.g. en=EU_English (repeatable; the first one is the slot we replace)",
    )
    args = ap.parse_args()

    langs = dict(item.split("=", 1) for item in (args.lang or ["en=EU_English"]))
    romfs = Path(args.title_dir) / "romfs"
    out_dir = ROOT / "src" / "strings" / args.name

    total = kept_total = 0
    for message_dir in sorted(p.name for p in romfs.iterdir() if p.is_dir() and p.name.startswith("message")):
        for path, count, kept in extract_dir(romfs, message_dir, langs, out_dir):
            print(f"{path}: {count} strings, {kept} translations kept")
            total += count
            kept_total += kept

    print(f"{total} strings total, {kept_total} translations kept -> {out_dir.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
