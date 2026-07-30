"""Check whether a candidate translation fits the label's budget.

Usage:
    python3 tools/fit.py home_menu lau_theme_rand "Теми випадково" "Випадкова тема"
    python3 tools/fit.py home_menu --list lau_theme_rand      # show every language of a label

The budget is the widest/tallest official localisation of that label, so a candidate
that fits it will fit on screen.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build import TITLES, apply_homoglyphs, load_homoglyphs  # noqa: E402
from validate import (  # noqa: E402
    WIDTH_LIMIT,
    WIDTH_SLACK,
    Budget,
    label_budgets,
    load_charset,
    load_msbt,
    load_widths,
    pixel_width,
)

ROOT = Path(__file__).resolve().parent.parent


def list_label(name: str, label: str, widths: dict[int, int], budget: Budget) -> None:
    """Print the label's text in every language folder of the title."""
    cfg = TITLES[name]
    romfs = ROOT / "work" / cfg["source_tid"] / "romfs"

    for json_file in sorted((ROOT / "src" / "strings" / name).glob("*.json")):
        message_dir, file_stem = json_file.stem.split("__", 1)
        for lang_dir in sorted((romfs / message_dir).iterdir()):
            if not lang_dir.is_dir():
                continue
            for candidate in lang_dir.iterdir():
                if candidate.name.split(".")[0] != file_stem:
                    continue
                data = load_msbt(candidate)
                if label in data.labels:
                    text = data.texts[data.labels[label]]
                    print(f"{lang_dir.name:16} {pixel_width(text, widths):5}px  {text!r}")

    print(f"\nbudget: {budget.width_px}px wide, {budget.lines} lines")


def main() -> None:
    name = sys.argv[1]
    args = sys.argv[2:]

    widths = load_widths()
    charset = load_charset()
    table = load_homoglyphs()
    budgets = label_budgets(name, widths)

    if args and args[0] == "--list":
        label = args[1]
        list_label(name, label, widths, budgets.get(label, Budget()))
        return

    label, candidates = args[0], args[1:]
    budget = budgets.get(label, Budget())
    limit = budget.width_px * WIDTH_LIMIT + WIDTH_SLACK
    print(f"{label}: budget {budget.width_px}px wide (limit {limit:.0f}px), {budget.lines} lines")

    for candidate in candidates:
        rendered = apply_homoglyphs(candidate, table)
        px = pixel_width(rendered, widths)
        lines = candidate.count("\n") + 1
        bad = [ch for ch in rendered if ch not in "\n\r\t" and ord(ch) not in charset]

        issues = []
        if budget.width_px and px > limit:
            issues.append("too wide")
        if budget.lines and lines > budget.lines:
            issues.append(f"{lines} lines")
        if bad:
            issues.append(f"missing glyphs: {bad}")

        mark = "OK  " if not issues else "FAIL"
        note = f"  <- {', '.join(issues)}" if issues else ""
        print(f"  {mark} {px:5}px  {candidate!r}{note}")


if __name__ == "__main__":
    main()
