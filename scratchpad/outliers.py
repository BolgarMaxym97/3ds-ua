"""List button-like labels that fit only because one language set a generous budget.

    python3 scratchpad/outliers.py [title ...]

A label is reported when it is single-line in every language, its budget is at most 320px,
the widest official localisation is more than 10px wider than the second widest, and the
Ukrainian text is wider than that second widest by more than 6px. Such a pane may well be
sized for the common case, with the widest language (often German or French) itself
clipped or shrunk on hardware - the glossary already records such cases (`base_3b_*`,
`dat_nand`). Review each: shorten or scale if a natural shorter wording exists.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from build import TITLES, apply_homoglyphs, load_homoglyphs  # noqa: E402
from msbt import parse as msbt_parse  # noqa: E402
from store import open_store  # noqa: E402
from validate import load_widths, pixel_width  # noqa: E402

W = load_widths()
HG = load_homoglyphs()


def main() -> None:
    titles = sys.argv[1:] or list(TITLES)
    for name in titles:
        if name not in TITLES:
            continue
        cfg = TITLES[name]
        store = open_store(cfg, ROOT / "work" / cfg["source_tid"] / "romfs")
        per: dict[str, list[tuple[int, str, str]]] = {}
        for lang in store.languages():
            for data in store.read(lang).values():
                m = msbt_parse(data)
                for i, text in enumerate(m.texts):
                    per.setdefault(m.label_of(i) or f"__index_{i}", []).append((pixel_width(text, W), lang, text))
        ours: dict[str, str] = {}
        for f in (ROOT / "src/strings" / name).glob("*.json"):
            if not f.name.startswith("_"):
                for k, e in json.loads(f.read_text()).items():
                    if isinstance(e, dict) and e.get("ua"):
                        ours[k] = e["ua"]
        for label, rows in per.items():
            if label not in ours or any("\n" in t for _, _, t in rows) or "\n" in ours[label]:
                continue
            rows.sort(reverse=True)
            if len(rows) < 3 or rows[0][0] > 320:
                continue
            top, second = rows[0][0], rows[1][0]
            ua = pixel_width(apply_homoglyphs(ours[label], HG), W)
            if top - second > 10 and ua > second + 6:
                print(f"{name}:{label} ua={ua}px budget={top}px ({rows[0][1]}) second={second}px ({rows[1][1]}) "
                      f"ru={next((w for w, l, _ in rows if l.endswith('Russian')), '?')}px  {ours[label]!r}")


if __name__ == "__main__":
    main()
