"""Mechanically fix the line breaks scratchpad/breaks.py reports, where it is safe.

    python3 scratchpad/fixbreaks.py [--write] [title ...]

For every break between two non-empty lines that breaks.py would flag, try in order:
  1. move the last word of the upper line down to the next line  (hang, name, unit, icon)
  2. pull the first word of the lower line up                       (name, unit, punct, dash)
A move is kept only if the whole text still fits the label's budget - width measured the way
tools/validate.py measures it (homoglyphs applied, font-scale tags honoured), and no more
lines than before. Anything that cannot be fixed this way is printed as UNFIXED for a human.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "scratchpad"))
from breaks import HANG, NAMES, UNIT, findings  # noqa: E402
from build import apply_homoglyphs, load_homoglyphs  # noqa: E402
from validate import Budget, label_budgets, line_widths, load_widths, strip_tags  # noqa: E402

W = load_widths()
HG = load_homoglyphs()


def width(text: str) -> float:
    return max(line_widths(apply_homoglyphs(text, HG), W), default=0)


def bad_break(upper: str, lower: str) -> str | None:
    """Which rule the break between two raw lines violates, if any."""
    u, l = strip_tags(upper).rstrip(), strip_tags(lower).lstrip()
    if not u.strip() or not l.strip():
        return None
    last = u.split()[-1].lower().strip("«(") if u.split() else ""
    pair = u + "\n" + l
    if last in HANG:
        return "hang"
    if any(re.search(p, pair[len(u) - 20 if len(u) > 20 else 0:][:60]) for p in NAMES):
        joined = re.search("|".join(NAMES), pair)
        if joined and joined.start() < len(u) < joined.end():
            return "name"
    m = re.search(UNIT, pair)
    if m and m.start() < len(u) < m.end():
        return "unit"
    if re.match(r"[,.;:!?»)]", l):
        return "punct"
    if re.match(r"[—–] ", l):
        return "dash"
    if re.search(r"[-] ?$", u):
        return "icon"
    return None


def split_last(line: str) -> tuple[str, str] | None:
    body = line.rstrip()
    i = body.rfind(" ")
    if i <= 0 or not body[:i].strip():
        return None
    return body[:i], body[i + 1:]


def split_first(line: str) -> tuple[str, str] | None:
    indent = len(line) - len(line.lstrip(" "))
    body = line[indent:]
    i = body.find(" ")
    if i <= 0:
        return None
    return body[:i], line[:indent] + body[i + 1:]


def try_fix(text: str, budget: Budget) -> tuple[str, list[str]]:
    lines = text.split("\n")
    limit = budget.width_px or 10**9
    notes: list[str] = []
    changed = True
    guard = 0
    while changed and guard < 50:
        changed = False
        guard += 1
        for i in range(len(lines) - 1):
            rule = bad_break(lines[i], lines[i + 1])
            if not rule:
                continue
            candidates = []
            if rule in ("hang", "name", "unit", "icon"):
                s = split_last(lines[i])
                if s:
                    indent = re.match(r" *", lines[i + 1]).group(0)
                    down = lines[:i] + [s[0], indent + s[1] + " " + lines[i + 1].lstrip()] + lines[i + 2:]
                    candidates.append(down)
            if rule in ("name", "unit", "punct", "dash"):
                s = split_first(lines[i + 1])
                if s:
                    up = lines[:i] + [lines[i].rstrip() + " " + s[0], s[1]] + lines[i + 2:]
                    candidates.append(up)
            for cand in candidates:
                new = "\n".join(cand)
                if width(new) <= limit and not any(bad_break(cand[j], cand[j + 1]) == rule and j == i for j in range(len(cand) - 1)):
                    lines = cand
                    changed = True
                    notes.append(rule)
                    break
            if changed:
                break
    return "\n".join(lines), notes


def main() -> None:
    write = "--write" in sys.argv
    titles = [a for a in sys.argv[1:] if not a.startswith("--")]
    titles = titles or [p.name for p in sorted((ROOT / "src/strings").iterdir()) if p.is_dir()]
    fixed = unfixed = 0
    for title in titles:
        try:
            budgets = label_budgets(title, W)
        except Exception as exc:  # noqa: BLE001 - area/plaza_map are not MSBT titles
            budgets = {}
        for f in sorted((ROOT / "src/strings" / title).glob("*.json")):
            if f.name.startswith("_"):
                continue
            data = json.loads(f.read_text())
            if not isinstance(data, dict):
                continue
            dirty = False
            for label, e in data.items():
                if not isinstance(e, dict) or not e.get("ua") or not findings(e["ua"]):
                    continue
                budget = budgets.get(label, Budget())
                new, notes = try_fix(e["ua"], budget)
                if new != e["ua"]:
                    fixed += len(notes)
                    print(f"FIXED {title}/{f.name}:{label} {notes}")
                    e["ua"] = new
                    dirty = True
                for rule, ctx in findings(new):
                    unfixed += 1
                    print(f"UNFIXED {title}/{f.name}:{label} {rule}: {ctx!r}")
            if dirty and write:
                f.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"fixed moves: {fixed}, still flagged: {unfixed}")


if __name__ == "__main__":
    main()
