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
  6. format specifiers (%d, %ls, %H, ...) differ from the original: the app would print
     garbage or crash

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
from build import TITLES, apply_homoglyphs, load_homoglyphs  # noqa: E402
from msbt import TOKEN_RE  # noqa: E402
from msbt import parse as msbt_parse  # noqa: E402
from store import open_store  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
WIDTH_LIMIT = 1.05  # headroom for renderer rounding
WIDTH_SLACK = 4     # absolute slack, so wording is not rewritten over 1-2 pixels
BRACE_RE = re.compile(r"\{[^}]*\}")
# %% is a literal percent sign and must survive translation, so it is matched first;
# a space is not part of the flags here - it would swallow the next word's first letter.
FORMAT_RE = re.compile(r"%%|%[-+#0-9.]*(?:ls|lc|[a-zA-Z])")


@dataclass
class Budget:
    width_px: int = 0
    lines: int = 0
    tags: set[str] = field(default_factory=set)


def load_charset() -> set[int]:
    text = (ROOT / "assets" / "font_charset.txt").read_text(encoding="utf-8")
    return {int(line.split("\t")[0][2:], 16) for line in text.splitlines() if line.startswith("U+")}


def load_widths() -> dict[int, int]:
    data = json.loads((ROOT / "assets" / "font_widths.json").read_text(encoding="utf-8"))
    return {int(code, 16): width for code, width in data.items()}


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

    for pattern in cfg.get("budget_groups", []):
        group = [label for label in budgets if re.fullmatch(pattern, label)]
        if len(group) < 2:
            continue
        shared = Budget(
            width_px=max(budgets[label].width_px for label in group),
            lines=max(budgets[label].lines for label in group),
            tags=set().union(*(budgets[label].tags for label in group)),
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
) -> list[str]:
    ua = entry.get("ua", "")
    if not ua:
        return []

    problems: list[str] = []

    for brace in BRACE_RE.findall(ua):
        if not TOKEN_RE.fullmatch(brace):
            problems.append(f"{label}: malformed tag token {brace!r}")

    src_formats = sorted(FORMAT_RE.findall(entry.get("en", "")))
    dst_formats = sorted(FORMAT_RE.findall(ua))
    if src_formats != dst_formats:
        problems.append(f"{label}: format specifiers {dst_formats} do not match the original {src_formats}")

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


def validate(
    name: str, charset: set[int], table: dict[str, str], widths: dict[int, int]
) -> tuple[int, int, list[str]]:
    strings_dir = ROOT / "src" / "strings" / name
    budgets = label_budgets(name, widths)
    total = translated = 0
    problems: list[str] = []

    for json_file in sorted(strings_dir.glob("*.json")):
        entries = json.loads(json_file.read_text(encoding="utf-8"))
        for label, entry in entries.items():
            total += 1
            if entry.get("ua"):
                translated += 1
            for problem in check_entry(label, entry, charset, table, widths, budgets.get(label, Budget())):
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
        print(f"{name}: {translated}/{total} translated, problems: {len(problems)}")
        for problem in problems:
            print(f"  ✗ {problem}")
        failed = failed or bool(problems)

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
