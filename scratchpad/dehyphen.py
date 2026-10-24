"""Re-wrap a hyphenated UI string to the full width budget; keep it only if it fits the
line budget and no word stays split. Usage: dehyphen.py [--write] title:label ..."""
import sys, json, re
sys.argv_saved = sys.argv; sys.argv = [sys.argv[0]]
sys.path.insert(0, "/Users/max/Work/Pet/3ds-ua/scratchpad")
import importlib.util
spec = importlib.util.spec_from_file_location("rf", "/Users/max/Work/Pet/3ds-ua/scratchpad/reflow.py")
src = open(spec.origin).read().replace("\nmain()", "\n")
rf = {}; exec(compile(src, spec.origin, "exec"), rf)
sys.argv = sys.argv_saved
write = "--write" in sys.argv
for arg in [a for a in sys.argv[1:] if not a.startswith("--")]:
    title, label = arg.split(":")
    f = next(p for p in (rf["ROOT"]/"src/strings"/title).glob("*.json") if not p.name.startswith("_") and label in json.loads(p.read_text()))
    d = json.loads(f.read_text()); old = d[label]["ua"]
    b = rf["label_budgets"](title, rf["W"]).get(label, rf["Budget"]())
    new = rf["reflow"](old, (b.width_px or 10**9) - 4)
    lines = new.count("\n") + 1
    split = re.search(r"[а-яіїєґ']-\n", new, re.I) and not re.search(r"(Інтернет|онлайн|фото)-\n", new)
    ok = lines <= (b.lines or 99) and max(rf["line_widths"](new, rf["W"])) <= (b.width_px or 10**9) and not split
    print(f"== {arg} {'OK' if ok else 'no'} lines {old.count(chr(10))+1}->{lines} budget {b.width_px}x{b.lines}\n{new}\n")
    if ok and write and new != old:
        d[label]["ua"] = new; f.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
