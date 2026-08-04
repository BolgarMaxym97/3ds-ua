"""Measure a candidate MSBT translation line by line.

    python3 scratchpad/measure.py system_settings net_new_wps1 "line1\nline2"
    python3 scratchpad/measure.py system_settings net_new_wps1     # measure what is in src/
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from build import apply_homoglyphs, load_homoglyphs  # noqa: E402
from validate import label_budgets, line_widths, load_widths  # noqa: E402


def main() -> None:
    name, label = sys.argv[1], sys.argv[2]
    widths = load_widths()
    table = load_homoglyphs()
    budget = label_budgets(name, widths).get(label)

    if len(sys.argv) > 3:
        text = sys.argv[3].replace("\\n", "\n")
    else:
        text = ""
        for path in sorted((ROOT / "src" / "strings" / name).glob("*.json")):
            entries = json.loads(path.read_text(encoding="utf-8"))
            if label in entries:
                text = entries[label]["ua"]

    rendered = apply_homoglyphs(text, table)
    lines = rendered.split("\n")
    px = line_widths(rendered, widths)
    for line, width in zip(lines, px):
        print(f"  {round(width):4}  {line}")
    print(f"widest {round(max(px)):4}px, {len(lines)} lines")
    if budget:
        print(f"budget {budget.width_px}px, {budget.lines} lines")


main()
