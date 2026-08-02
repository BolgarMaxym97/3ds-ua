"""Validate the translations before building.

Usage:
    python3 tools/validate.py            # every strings project
    python3 tools/validate.py home_menu

Rules (every violation is an error):
  1. a character missing from assets/font_charset.txt after homoglyph substitution
     would render as an empty box
  2. line width in pixels above the widest official localisation x WIDTH_LIMIT
     would be clipped
  3. more lines than the tallest official localisation would overflow the dialog
  4. a control tag that appears in no official localisation of that label is invented
  5. a malformed tag token
  6. the set of format specifiers (%d, %ls, %H, ...) matches no official localisation of
     that label: the app would print garbage or crash. Any localisation's set is accepted,
     because languages legitimately differ (%d %n '%y in English vs %d.%M.%y in German).
  7. a character missing from the *HUD* font in one of the labels that font draws. The
     clock line on the top screen has its own 15x17 bitmap subset per title, far smaller
     than the system font, and a letter it lacks is simply not drawn - which is how
     Ukrainian Sunday spent a release showing as `( )`.

Labels that share one UI slot (e.g. every entry of the language list) can be grouped
with `budget_groups` regexes in TITLES: the group's widest member sets the budget for
all of them, because the slot must already fit the longest sibling.

The budgets (width, height, allowed tags) are the maximum/union across ALL language
folders of the title: the UI has to fit the longest official localisation, so that is
the real limit rather than any single language. This also means the language slot
(EU_English / EU_Russian) can be switched without rewriting the translation.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import bcfnt  # noqa: E402
from build import TITLES, apply_homoglyphs, load_all_langs, load_homoglyphs, load_hud_glyphs  # noqa: E402
from msbt import TOKEN_RE  # noqa: E402
from msbt import parse as msbt_parse  # noqa: E402
from store import open_store  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
# The budget is already the widest official localisation, so anything past it is wider than
# anything Nintendo ever put in that pane. There is no headroom to give: a 5% allowance here
# let 175 strings through that overflow their button on hardware. Only a couple of pixels of
# absolute slack remain, for rounding in the renderer.
WIDTH_LIMIT = 1.0
# Slack is absolute on purpose. A percentage grows with the string, which is backwards: it
# handed a 500px dialog 25px of room while giving a button almost none. Eight pixels is
# about one narrow glyph - enough that a word like "Відкрити" is not rewritten for being a
# hair wider than "Открыть", and far too little to hide a real overflow.
WIDTH_SLACK = 8
BRACE_RE = re.compile(r"\{[^}]*\}")
# The labels the HUD font draws, as opposed to the rest of hud.msbt: the clock line's
# date format and its parts. `lau_connect*` and friends sit below it in the system font,
# which is why this is a list of what the small font touches rather than a whole file.
HUD_LABEL_RE = re.compile(r"lau_(?:date|birthday|hours|minutes)|(?:month|day|week)_\w+")
# %% is a literal percent sign and must survive translation, so it is matched first;
# a space is not part of the flags here - it would swallow the next word's first letter.
FORMAT_RE = re.compile(r"%%|%[-+#0-9.]*(?:ls|lc|[a-zA-Z])")


@dataclass
class Budget:
    width_px: int = 0
    lines: int = 0
    tags: set[str] = field(default_factory=set)
    format_sets: set[tuple[str, ...]] = field(default_factory=set)


def load_charset() -> set[int]:
    text = (ROOT / "assets" / "font_charset.txt").read_text(encoding="utf-8")
    return {int(line.split("\t")[0][2:], 16) for line in text.splitlines() if line.startswith("U+")}


def load_widths() -> dict[int, int]:
    data = json.loads((ROOT / "assets" / "font_widths.json").read_text(encoding="utf-8"))
    return {int(code, 16): width for code, width in data.items()}


def hud_charset(cfg: dict) -> set[int]:
    """What the title's HUD font can draw once the build has added its glyphs to it."""
    path = ROOT / "work" / cfg["source_tid"] / "romfs" / cfg["hud_font"]
    font = bcfnt.parse(path.read_bytes())
    return set(font.cmap) | set(load_hud_glyphs())


def strip_tags(text: str) -> str:
    return TOKEN_RE.sub("", text)


def pixel_width(text: str, widths: dict[int, int]) -> int:
    """Width of the widest line in pixels (tags are not rendered)."""
    return max(
        (sum(widths.get(ord(ch), 0) for ch in line) for line in strip_tags(text).split("\n")),
        default=0,
    )


def label_budgets(name: str, widths: dict[int, int]) -> dict[str, Budget]:
    """Per-label budgets: max width and line count, union of tags across all languages."""
    cfg = TITLES[name]
    store = open_store(cfg, ROOT / "work" / cfg["source_tid"] / "romfs")
    budgets: dict[str, Budget] = {}

    for lang in store.languages():
        for data in store.read(lang).values():
            msbt = msbt_parse(data)
            for index, text in enumerate(msbt.texts):
                label = msbt.label_of(index) or f"__index_{index}"
                budget = budgets.setdefault(label, Budget())
                budget.width_px = max(budget.width_px, pixel_width(text, widths))
                budget.lines = max(budget.lines, text.count("\n") + 1)
                budget.tags |= set(TOKEN_RE.findall(text))
                budget.format_sets.add(tuple(sorted(FORMAT_RE.findall(text))))

    for pattern in cfg.get("budget_groups", []):
        group = [label for label in budgets if re.fullmatch(pattern, label)]
        if len(group) < 2:
            continue
        shared = Budget(
            width_px=max(budgets[label].width_px for label in group),
            lines=max(budgets[label].lines for label in group),
            tags=set().union(*(budgets[label].tags for label in group)),
            format_sets=set().union(*(budgets[label].format_sets for label in group)),
        )
        for label in group:
            budgets[label] = shared

    return budgets


def check_entry(
    label: str,
    entry: dict[str, str],
    charset: set[int],
    table: dict[str, str],
    widths: dict[int, int],
    budget: Budget,
    hud: set[int] | None = None,
) -> list[str]:
    ua = entry.get("ua", "")
    if not ua:
        return []

    problems: list[str] = []

    if hud is not None and HUD_LABEL_RE.fullmatch(label):
        missing = {ch for ch in strip_tags(apply_homoglyphs(ua, table)) if ord(ch) not in hud}
        if missing:
            chars = " ".join(f"{ch!r} U+{ord(ch):04X}" for ch in sorted(missing))
            problems.append(f"{label}: characters missing from the HUD font: {chars}")

    for brace in BRACE_RE.findall(ua):
        if not TOKEN_RE.fullmatch(brace):
            problems.append(f"{label}: malformed tag token {brace!r}")

    dst_formats = tuple(sorted(FORMAT_RE.findall(ua)))
    if budget.format_sets and dst_formats not in budget.format_sets:
        allowed = sorted(budget.format_sets)
        problems.append(f"{label}: format specifiers {list(dst_formats)} match no localisation {allowed}")

    unknown = set(TOKEN_RE.findall(ua)) - budget.tags
    if unknown:
        problems.append(f"{label}: tags present in no official localisation: {sorted(unknown)}")

    rendered = apply_homoglyphs(ua, table)
    bad = {ch for ch in strip_tags(rendered) if ch not in "\n\r\t" and ord(ch) not in charset}
    if bad:
        chars = " ".join(f"{ch!r} U+{ord(ch):04X}" for ch in sorted(bad))
        problems.append(f"{label}: characters missing from the font: {chars}")

    dst_px = pixel_width(rendered, widths)
    if budget.width_px and dst_px > budget.width_px * WIDTH_LIMIT + WIDTH_SLACK:
        problems.append(f"{label}: {dst_px}px exceeds budget {budget.width_px}px (x{WIDTH_LIMIT})")

    dst_lines = ua.count("\n") + 1
    if budget.lines and dst_lines > budget.lines:
        problems.append(f"{label}: {dst_lines} lines exceed the {budget.lines}-line maximum across localisations")

    return problems


LETTERS_RE = re.compile(r"[^\W\d_]{2}")


def untranslatable(name: str) -> set[str]:
    """Labels there is nothing to translate in: empty, or with no word in them.

    Counting these as outstanding work is what made the coverage look like a third of the
    text was missing. What is left after stripping tags is things like `%ls`, `1`, `:` and
    the language names a picker deliberately shows in their own language.
    """
    cfg = TITLES[name]
    store = open_store(cfg, ROOT / "work" / cfg["source_tid"] / "romfs")

    def texts(lang: str) -> dict[str, str]:
        out: dict[str, str] = {}
        for data in store.read(lang).values():
            msbt = msbt_parse(data)
            for index, text in enumerate(msbt.texts):
                out[msbt.label_of(index) or f"__index_{index}"] = text
        return out

    slot = texts(cfg["lang"])
    reference = texts(cfg["ref_lang"])
    skip = {label for label, text in slot.items() if not LETTERS_RE.search(strip_tags(text))}
    # Nintendo shipping the same text in two languages means the string is not language
    # dependent: `WPA2-PSK (AES)`, `%ls`, the Latin key rows, and the language names a
    # picker deliberately shows in their own language. Translating those would be a bug.
    skip |= {label for label, text in slot.items() if reference.get(label) == text}
    return skip


def validate(
    name: str, charset: set[int], table: dict[str, str], widths: dict[int, int]
) -> tuple[int, int, list[str]]:
    cfg = TITLES[name]
    strings_dir = ROOT / "src" / "strings" / name
    budgets = label_budgets(name, widths)
    hud = hud_charset(cfg) if cfg.get("hud_font") else None
    skip = untranslatable(name)
    total = translated = 0
    problems: list[str] = []

    # _all_langs.json holds plain {label: text} written into every slot, so it is checked
    # against the same budgets but without the en/ua entry shape.
    for key, labels in load_all_langs(strings_dir).items():
        for label, text in labels.items():
            entry = {"en": "", "ua": text}
            for problem in check_entry(label, entry, charset, table, widths, budgets.get(label, Budget()), hud):
                problems.append(f"_all_langs.json: {problem}")

    for json_file in sorted(strings_dir.glob("*.json")):
        if json_file.name.startswith("_"):
            continue
        entries = json.loads(json_file.read_text(encoding="utf-8"))
        for label, entry in entries.items():
            if label not in skip:
                total += 1
                if entry.get("ua"):
                    translated += 1
            for problem in check_entry(label, entry, charset, table, widths, budgets.get(label, Budget()), hud):
                problems.append(f"{json_file.name}: {problem}")

    return total, translated, problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("titles", nargs="*", default=None)
    args = ap.parse_args()

    charset = load_charset()
    table = load_homoglyphs()
    widths = load_widths()
    failed = False

    for name in args.titles or list(TITLES):
        total, translated, problems = validate(name, charset, table, widths)
        gap = "" if translated == total else f" ({total - translated} left)"
        print(f"{name}: {translated}/{total} translatable strings done{gap}, problems: {len(problems)}")
        for problem in problems:
            print(f"  ✗ {problem}")
        failed = failed or bool(problems)

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
