"""Lint every `ua` string (UI and manuals): Russian letters, doubled words, spacing."""
import json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
RU = re.compile(r"[ыЫэЭъЪёЁ]")
DOUBLE = re.compile(r"(?<![\w{])(\w{2,})\s+\1(?![\w}])", re.I)
SPACE = re.compile(r"[^\S\n]{2,}|[^\S\n]+\n|\n[^\S\n]+(?=\w)| [,.;:!?](?!\.)")
MIXED = re.compile(r"\b(?=\w*[a-zA-Z])(?=\w*[а-яА-ЯіїєґІЇЄҐ])\w+\b")
def strings():
    for f in sorted((ROOT/"src"/"strings").rglob("*.json")):
        d = json.loads(f.read_text())
        def walk(o, k):
            if isinstance(o, dict):
                for kk, v in o.items():
                    if kk in ("ua", "ua_long") and isinstance(v, str):
                        yield f, k, v, o.get("en", "")
                    elif kk not in ("en", "ru"):
                        yield from walk(v, kk if k == "" else k + "/" + kk)
            elif isinstance(o, str) and f.name.startswith("_all"):
                yield f, k, o, ""
        yield from walk(d, "")
    for f in sorted((ROOT/"src"/"manuals").glob("*.json")):
        for k, e in json.loads(f.read_text()).items():
            yield f, k, e["ua"], e.get("en", "")
for f, k, ua, en in strings():
    t = ua
    rel = f.relative_to(ROOT)
    for name, rx in (("ru-letter", RU), ("double", DOUBLE), ("space", SPACE), ("mixed", MIXED)):
        for m in rx.finditer(t):
            if name == "space" and SPACE.search(en or ""):
                continue
            print(f"{rel}:{k} {name}: {t[max(0,m.start()-25):m.end()+25]!r}")
