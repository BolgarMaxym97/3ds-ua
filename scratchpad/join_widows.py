"""Pull a one-word paragraph-final line up onto the line above when it fits within the
string's own widest line. Usage: join_widows.py [--write] title:label ..."""
import sys, json, re
sys.path.insert(0, "/Users/max/Work/Pet/3ds-ua/tools")
from pathlib import Path
from validate import load_widths, line_widths as _lw, strip_tags
from build import apply_homoglyphs, load_homoglyphs
HG, W = load_homoglyphs(), load_widths()
ROOT = Path("/Users/max/Work/Pet/3ds-ua")
def lw(t): return _lw(apply_homoglyphs(t, HG), W)
def fix(ua):
    lines = ua.split("\n"); top = max(lw(ua)); i = 1
    while i < len(lines):
        cur, prev = strip_tags(lines[i]).strip(), strip_tags(lines[i-1]).strip()
        nxt = strip_tags(lines[i+1]).strip() if i + 1 < len(lines) else ""
        ok = (cur and " " not in cur and prev and not nxt and "{" not in lines[i] + lines[i-1]
              and not prev.endswith((":", ".", "!", "?", "…")) and not re.match(r"^[•■●\-–—]", cur))
        if ok:
            joined = lines[i-1].rstrip() + " " + lines[i].strip()
            if lw(joined)[0] <= top:
                lines[i-1:i+1] = [joined]; continue
        i += 1
    return "\n".join(lines)
write = "--write" in sys.argv
for arg in [a for a in sys.argv[1:] if not a.startswith("--")]:
    title, label = arg.split(":")
    f = next(p for p in (ROOT/"src/strings"/title).glob("*.json") if not p.name.startswith("_") and label in json.loads(p.read_text()))
    d = json.loads(f.read_text()); old = d[label]["ua"]; new = fix(old)
    if new != old:
        print(f"== {arg}\n{new}\n")
        if write:
            d[label]["ua"] = new
            f.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
