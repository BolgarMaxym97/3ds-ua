"""Report ugly line breaks in translated strings.

Usage: python3 scratchpad/breaks.py [title ...]      (no title = every title)
       python3 scratchpad/breaks.py --manuals [name ...]

Rules (one line per finding, `title/file:label rule: context`):
  hang     a short preposition/conjunction left at the end of a line ("... з\\nкарти")
  name     a fixed name split across lines ("Nintendo\\n3DS", "меню\\nHOME", "карта\\nSD")
  unit     a number split from its unit or the "стор." reference ("30\\nсм", "%d\\nхв")
  punct    a line starting with punctuation that belongs to the previous word
  dash     a line starting with an em/en dash (keep the dash with the previous word)
  icon     a button icon (private-use glyph) left alone at the end of a line
  hyph     a word hyphenated leaving one or two letters on a line ("ви-\\nкористовувати" ok,
           "з-\\nавантаження" not)
Only line breaks inside the text are checked; `\\n\\n` paragraph breaks are fine.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from validate import strip_tags  # noqa: E402

HANG = set("з із зі в у й і та а о до на за по від для про при без над під не ні чи як що".split())
NAMES = [
    r"Nintendo\n(3DS|2DS|DS|eShop|Network|Zone|Switch|Wii|DSi)",
    r"New\nNintendo",
    r"Network\nID",
    r"StreetPass\nMii",
    r"Mii\n(Maker|Plaza)",
    r"[Мм]еню\nHOME",
    r"[Кк]арт[аиіуою]{0,2}\n(SD|microSD)",
    r"3DS\nXL|2DS\nXL",
    r"Face\nRaiders|AR\nGames",
]
UNIT = r"(\d+|%d|%ls|%s)\n(см|мм|м|хв|год|сек|с|дн|р\.|МБ|ГБ|блок\w*|%)\b|стор\.\n\d"
PUA = re.compile(r"[-]")


def findings(text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    plain = strip_tags(text)
    # Lookbehind, not a consumed delimiter: consecutive short lines ("—\nна\nsupport")
    # must each be tested, and a consumed "\n" would hide the second one.
    for m in re.finditer(r"(?<![^ \n«(])(\S+) ?\n(?=\S)", plain):
        word = m.group(1).lower().strip("«(")
        if word in HANG:
            out.append(("hang", plain[max(0, m.start() - 15): m.end() + 12]))
    for pat in NAMES:
        for m in re.finditer(pat, plain):
            out.append(("name", plain[max(0, m.start() - 10): m.end() + 10]))
    for m in re.finditer(UNIT, plain):
        out.append(("unit", plain[max(0, m.start() - 10): m.end() + 10]))
    for m in re.finditer(r"\n[,.;:!?»)]", plain):
        out.append(("punct", plain[max(0, m.start() - 15): m.end() + 10]))
    for m in re.finditer(r"\n[—–] ", plain):
        out.append(("dash", plain[max(0, m.start() - 15): m.end() + 10]))
    for m in re.finditer(r"[-] ?\n", plain):
        out.append(("icon", plain[max(0, m.start() - 10): m.end() + 10]))
    for m in re.finditer(r"(?:^|[ \n])(\w{1,2})-\n(\w+)|(\w+)-\n(\w{1,2})\b", plain):
        out.append(("hyph", plain[max(0, m.start() - 5): m.end() + 5]))
    return out


def main() -> None:
    args = sys.argv[1:]
    if args and args[0] == "--manuals":
        names = args[1:] or [p.stem for p in sorted((ROOT / "src/manuals").glob("*.json"))]
        for name in names:
            for key, e in json.loads((ROOT / "src/manuals" / f"{name}.json").read_text()).items():
                if isinstance(e, dict) and e.get("ua"):
                    for rule, ctx in findings(e["ua"]):
                        print(f"manual/{name}:{key} {rule}: {ctx!r}")
        return
    titles = args or [p.name for p in sorted((ROOT / "src/strings").iterdir()) if p.is_dir()]
    for title in titles:
        for f in sorted((ROOT / "src/strings" / title).glob("*.json")):
            if f.name.startswith("_"):
                continue
            data = json.loads(f.read_text())
            if not isinstance(data, dict):
                continue
            for label, e in data.items():
                if isinstance(e, dict) and e.get("ua"):
                    for rule, ctx in findings(e["ua"]):
                        print(f"{title}/{f.name}:{label} {rule}: {ctx!r}")


if __name__ == "__main__":
    main()
