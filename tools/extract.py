"""Extract text from a romfs dump into JSON files for translation.

Usage:
    python3 tools/extract.py                 # every title in TITLES
    python3 tools/extract.py home_menu

Output: src/strings/<title>/<message_dir>__<file>.json
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
from build import TITLES  # noqa: E402
from msbt import parse  # noqa: E402
from store import open_store  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def extract_title(name: str) -> list[tuple[str, int, int]]:
    cfg = TITLES[name]
    romfs = ROOT / "work" / cfg["source_tid"] / "romfs"
    store = open_store(cfg, romfs)
    out_dir = ROOT / "src" / "strings" / name
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for key, data in sorted(store.read(cfg["lang"]).items()):
        msbt = parse(data)
        out_file = out_dir / f"{key}.json"
        existing = json.loads(out_file.read_text(encoding="utf-8")) if out_file.exists() else {}

        entries: dict[str, dict[str, str]] = {}
        kept = 0
        for index, text in enumerate(msbt.texts):
            label = msbt.label_of(index) or f"__index_{index}"
            ua = existing.get(label, {}).get("ua", "")
            entries[label] = {"en": text, "ua": ua}
            kept += bool(ua)

        out_file.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        results.append((str(out_file.relative_to(ROOT)), len(entries), kept))

    return results


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("titles", nargs="*", default=None, help="names from TITLES; all of them when omitted")
    args = ap.parse_args()

    for name in args.titles or list(TITLES):
        total = kept_total = 0
        for path, count, kept in extract_title(name):
            print(f"{path}: {count} strings, {kept} translations kept")
            total += count
            kept_total += kept
        print(f"{name}: {total} strings total, {kept_total} translations kept")


if __name__ == "__main__":
    main()
