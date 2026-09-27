"""Re-wrap long texts whose lines were split in two instead of reflowed.
reflow.py [--write] title:label ...   (prints before/after)"""
import sys, json, re
sys.path.insert(0, "/Users/max/Work/Pet/3ds-ua/tools")
from validate import load_widths, line_widths as _lw, strip_tags, label_budgets, Budget
from build import apply_homoglyphs, load_homoglyphs
HG = load_homoglyphs()
def line_widths(t, w):
    return _lw(apply_homoglyphs(t, HG), w)
from pathlib import Path

ROOT = Path("/Users/max/Work/Pet/3ds-ua")
W = load_widths()
BULLET = re.compile(r"^\s*(?:[•■●\-–—]|\(\d|\d+\))")
SHORT = set("з із зі в у й і та а але чи або до на за по від для про при без над під що як не ні".split())
COMPOUND = ("консолі-", "консоль-", "консоллю-", "як-", "будь-", "Інтернет-", "інтернет-")

def vis(line):
    return strip_tags(line).strip()

def blocks(text):
    """Split into blocks of lines that belong to one flowing paragraph."""
    lines = text.split("\n")
    out, cur = [], []
    for i, line in enumerate(lines):
        v = vis(line)
        start_new = (not cur or not v or not vis(cur[-1]) or BULLET.match(strip_tags(line))
                     and not strip_tags(line).startswith("  ")
                     or vis(cur[-1]).endswith(":"))
        if start_new and cur:
            out.append(cur); cur = []
        cur.append(line)
        if not v:
            out.append(cur); cur = []
    if cur:
        out.append(cur)
    return out

def join(block):
    s = ""
    for line in block:
        piece = line.strip() if s else line.rstrip()
        if not s:
            s = piece
        elif s.endswith("-") and not s.endswith(" -"):
            last = s.split(" ")[-1]
            s = s + piece if last.endswith(COMPOUND) or re.search(r"[A-Z]-$", last) else s[:-1] + piece
        else:
            s = s + " " + piece
    return s

def width_of(prefix, line):
    # painted width of `line` given the scale state left by `prefix`
    return line_widths(prefix + line, W)[-1]

def wrap(prefix, para, target, indent):
    words = para.split(" ")
    lead = re.match(r"^(\s*(?:[•■●\-–—]\s+)?)", strip_tags(para)).group(1)
    lines, cur = [], ""
    for w in words:
        cand = w if not cur else cur + " " + w
        ctx = prefix + "\n".join(lines) + ("\n" if lines else "")
        if cur and width_of(ctx, cand) > target:
            # do not leave a short preposition dangling at the end of the line
            parts = cur.rsplit(" ", 1)
            if len(parts) == 2 and vis(parts[1]).lower() in SHORT:
                lines.append(parts[0]); cur = (indent + parts[1] + " " + w)
            else:
                lines.append(cur); cur = indent + w
        else:
            cur = cand
    lines.append(cur)
    return lines

def reflow(text, target):
    out = []
    for b in blocks(text):
        if len(b) == 1 or not any(vis(l) for l in b):
            out.extend(b); continue
        indent = ""
        if BULLET.match(strip_tags(b[0])) and len(b) > 1 and b[1].startswith("  "):
            indent = "  "
        prefix = "\n".join(out) + ("\n" if out else "")
        out.extend(wrap(prefix, join(b), target, indent))
    return "\n".join(out)

def main():
    write = "--write" in sys.argv
    budgets = {}
    for arg in [a for a in sys.argv[1:] if not a.startswith("--")]:
        title, label = arg.split(":")
        f = next(p for p in (ROOT / "src/strings" / title).glob("*.json")
                 if not p.name.startswith("_") and label in json.loads(p.read_text()))
        d = json.loads(f.read_text())
        old = d[label]["ua"]
        if title not in budgets:
            budgets[title] = label_budgets(title, W)
        b = budgets[title].get(label, Budget())
        target = min(max(line_widths(old, W)), b.width_px or 10**9)
        new = reflow(old, target)
        if strip_tags(re.sub(r"\s+", "", new)).replace("-", "") != strip_tags(re.sub(r"\s+", "", old)).replace("-", ""):
            print(f"!! text changed beyond whitespace in {arg}")
        print(f"==== {arg}  lines {old.count(chr(10))+1} -> {new.count(chr(10))+1}, target {target:.0f}px, budget {b.width_px}x{b.lines}")
        if "--show" in sys.argv:
            print(new)
        if write and new != old:
            d[label]["ua"] = new
            f.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

main()
