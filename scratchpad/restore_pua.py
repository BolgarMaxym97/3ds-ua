"""Put back button glyphs (U+E000-F8FF) that a translation lost: each glyph sat between two
characters of `ru`; in `ua` those two now touch, so the glyph goes back between them, in order.
Usage: restore_pua.py NAME [--write]"""
import json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
PUA = re.compile("[-]")
name = sys.argv[1]
path = ROOT / "src/manuals" / f"{name}.json"
d = json.loads(path.read_text())
fixed = failed = 0
for k, e in d.items():
    ru, ua = e["ru"], e["ua"]
    if not ua or sorted(PUA.findall(ru)) == sorted(PUA.findall(ua)) or PUA.search(ua):
        continue
    pos, ok = 0, True
    for m in PUA.finditer(ru):
        left = ru[m.start() - 1] if m.start() else ""
        right = ru[m.end()] if m.end() < len(ru) else ""
        if PUA.match(right or "x"): right = ""
        if not left: at = 0
        elif not right: at = len(ua) if ua.endswith(left) else -1
        else:
            i = ua.find(left + right, pos)
            at = i + 1 if i >= 0 else -1
        if at < 0: ok = False; break
        ua = ua[:at] + m.group() + ua[at:]; pos = at + 1
    if ok and sorted(PUA.findall(ru)) == sorted(PUA.findall(ua)):
        print(f"{k}: {ua.encode('unicode_escape').decode()[:120]}"); e["ua"] = ua; fixed += 1
    else:
        print(f"!! {k}: could not place"); failed += 1
print(f"{fixed} fixed, {failed} left")
if "--write" in sys.argv and not failed:
    path.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
