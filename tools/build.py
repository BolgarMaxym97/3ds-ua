"""Build LayeredFS-ready files from the JSON translations.

Usage:
    python3 tools/build.py            # every title in TITLES
    python3 tools/build.py home_menu

How it works: the original MSBT from work/ is used as a template, texts are replaced
with the JSON ones (empty `ua` keeps the original), homoglyph substitution is applied,
the result is LZ11-packed into dist/luma/titles/<TID>/romfs/<same path>.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import msbt as msbt_mod  # noqa: E402
from lz11 import compress, decompress  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

# Titles: strings project name -> target TIDs, language slot, dump used as source.
#
# The slot is the language folder we replace. English is a deliberate choice: strings
# left untranslated (new ones after a system update, purely numeric ones, ...) stay
# English instead of Russian. The console language must be set to English.
TITLES = {
    "home_menu": {
        "tids": ["0004003000009802"],  # EUR; JPN 0004003000008202, USA 0004003000008F02 once tested
        "source_tid": "0004003000009802",
        "lang": "EU_English",
    },
}


def load_homoglyphs() -> dict[str, str]:
    data = json.loads((ROOT / "src" / "homoglyphs.json").read_text(encoding="utf-8"))
    table = dict(data["variants"][data["default"]])
    table.pop("_comment", None)
    for key, value in data.get("also_missing", {}).items():
        if key != "_comment":
            table[key] = value
    return table


def apply_homoglyphs(text: str, table: dict[str, str]) -> str:
    return text.translate(str.maketrans(table))


def build_title(name: str, table: dict[str, str]) -> list[str]:
    cfg = TITLES[name]
    lang = cfg["lang"]
    src_romfs = ROOT / "work" / cfg["source_tid"] / "romfs"
    strings_dir = ROOT / "src" / "strings" / name

    written: list[str] = []
    for json_file in sorted(strings_dir.glob("*.json")):
        message_dir, file_stem = json_file.stem.split("__", 1)
        original = _find_original(src_romfs / message_dir / lang, file_stem)
        entries = json.loads(json_file.read_text(encoding="utf-8"))

        raw = original.read_bytes()
        data = decompress(raw) if original.name.endswith("_LZ.bin") else raw
        msbt = msbt_mod.parse(data)

        translated = 0
        for index in range(len(msbt.texts)):
            label = msbt.label_of(index) or f"__index_{index}"
            entry = entries.get(label)
            if not entry or not entry.get("ua"):
                continue
            msbt.texts[index] = apply_homoglyphs(entry["ua"], table)
            translated += 1

        out_bytes = msbt_mod.build(msbt)
        if original.name.endswith("_LZ.bin"):
            out_bytes = compress(out_bytes)

        for tid in cfg["tids"]:
            dest = ROOT / "dist" / "luma" / "titles" / tid / "romfs" / message_dir / lang / original.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(out_bytes)
            written.append(f"{dest.relative_to(ROOT)} ({translated}/{len(msbt.texts)} translated, {len(out_bytes)} bytes)")

    return written


def _find_original(lang_dir: Path, file_stem: str) -> Path:
    for candidate in lang_dir.iterdir():
        if candidate.name.split(".")[0] == file_stem:
            return candidate
    raise FileNotFoundError(f"{file_stem} not found in {lang_dir}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("titles", nargs="*", default=None, help="names from TITLES; all of them when omitted")
    args = ap.parse_args()

    table = load_homoglyphs()
    names = args.titles or list(TITLES)
    for name in names:
        for line in build_title(name, table):
            print(line)


if __name__ == "__main__":
    main()
