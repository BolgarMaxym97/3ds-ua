"""Lay out a candidate manual translation and show where the lines land.

    python3 scratchpad/try_manual.py system_settings large/Page_001_large_0#1
    python3 scratchpad/try_manual.py system_settings large/Page_001_large_0#1 "Інші налашту-вання"

With no candidate it lays out what src/manuals/<name>.json already holds.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import manual as M  # noqa: E402
from build import apply_homoglyphs, load_homoglyphs  # noqa: E402
from validate import load_widths  # noqa: E402


def main() -> None:
    name, key = sys.argv[1], sys.argv[2]
    page, index = key.rsplit("#", 1)
    index = int(index)

    cfg = M.MANUALS[name]
    source = M.source_manual(name)
    widths, table = load_widths(), load_homoglyphs()
    limits = M.budgets(source, cfg["slot"], widths)
    flow = M.pages_of(source, cfg["slot"])[page][index]
    entry = M.load_json(name).get(key, {})

    text = sys.argv[3] if len(sys.argv) > 3 else entry.get("ua", "")
    limit = limits[key] + M.WIDTH_SLACK

    print(f"ru: {entry.get('ru', '')!r}")
    print(f"column {limits[key]:.0f}px (+{M.WIDTH_SLACK:.0f} slack), {len(flow.lines)} lines")

    lines = M.layout(apply_homoglyphs(text, table), flow, limit, widths)
    for number, line in enumerate(lines):
        drawn = line[-1].x + line[-1].width - flow.margin(number) if line else 0.0
        body = "".join((" " if p.spaced else "") + (p.text or "<icon>") for p in line)
        flag = " <<<" if drawn > limit else ""
        print(f"  {drawn:6.1f}  {body}{flag}")
    print(f"{len(lines)} lines, {M.overflow(lines, flow, limit):.1f}px past the column")


main()
