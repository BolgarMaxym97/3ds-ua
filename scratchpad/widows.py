"""One-word last lines of a paragraph that would fit on the line above (within the string's own widest line)."""
import sys, json, re
sys.path.insert(0, "/Users/max/Work/Pet/3ds-ua/tools")
from pathlib import Path
from validate import load_widths, line_widths as _lw, strip_tags, TITLES
from build import apply_homoglyphs, load_homoglyphs
HG, W = load_homoglyphs(), load_widths()
ROOT = Path("/Users/max/Work/Pet/3ds-ua")
def lw(t): return _lw(apply_homoglyphs(t, HG), W)
for title in TITLES:
    for f in sorted((ROOT/"src/strings"/title).glob("*.json")):
        if f.name.startswith("_"): continue
        for k, e in json.loads(f.read_text()).items():
            ua = e.get("ua") if isinstance(e, dict) else None
            if not ua or "\n" not in ua: continue
            lines = ua.split("\n"); widths = lw(ua); top = max(widths)
            for i in range(1, len(lines)):
                cur, prev = strip_tags(lines[i]).strip(), strip_tags(lines[i-1]).strip()
                nxt = strip_tags(lines[i+1]).strip() if i + 1 < len(lines) else ""
                if not cur or " " in cur or not prev or nxt or "{" in lines[i] or "{" in lines[i-1]: continue
                if prev.endswith((":", ".", "!", "?", "…")) or re.match(r"^[•■●\-–—]", cur): continue
                joined = lines[i-1].rstrip() + " " + lines[i].strip()
                if lw(joined)[0] <= top:
                    print(f"{title}:{k}  …{prev[-30:]} | {cur}")
