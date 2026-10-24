"""Translation memory for manuals.
  manual_tm.py fill NAME           - copy ua for every ru already translated in another manual
  manual_tm.py todo NAME [layout]  - list untranslated unique ru, in page order, as JSON lines
  manual_tm.py apply NAME FILE     - FILE is JSON {ru: ua}; written to every key with that ru
  manual_tm.py applyk NAME FILE    - FILE is JSON {key: ua}; the same, matched by that key's ru
"""
import json, glob, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
CYR = re.compile("[А-Яа-яЁё]")
cmd, name = sys.argv[1], sys.argv[2]
path = ROOT / "src/manuals" / f"{name}.json"
d = json.loads(path.read_text())
def save():
    path.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
if cmd == "fill":
    tm = {}
    for f in sorted(glob.glob(str(ROOT / "src/manuals/*.json"))):
        if Path(f) == path: continue
        for e in json.loads(Path(f).read_text()).values():
            if e["ua"]: tm.setdefault(e["ru"], e["ua"])
    n = 0
    for e in d.values():
        if not e["ua"] and e["ru"] in tm: e["ua"] = tm[e["ru"]]; n += 1
    save(); print(f"{name}: {n} filled from other manuals")
elif cmd == "todo":
    seen = set()
    for k, e in d.items():
        if e["ua"] or not CYR.search(e["ru"]) or e["ru"] in seen: continue
        if len(sys.argv) > 3 and not k.startswith(sys.argv[3]): continue
        seen.add(e["ru"]); print(json.dumps({"k": k, "ru": e["ru"]}, ensure_ascii=False))
elif cmd in ("apply", "applyk"):
    m = json.loads(Path(sys.argv[3]).read_text())
    if cmd == "applyk":  # keyed by the key of a paragraph; the ru of that key is what matches
        m = {d[k]["ru"]: v for k, v in m.items()}
    n = 0
    for e in d.values():
        if e["ru"] in m: e["ua"] = m[e["ru"]]; n += 1
    save(); print(f"{name}: {n} paragraphs from {len(m)} translations")
