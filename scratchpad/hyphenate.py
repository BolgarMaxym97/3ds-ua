"""Propose hyphenation for the manual paragraphs whose lines run past their column.

    python3 scratchpad/hyphenate.py system_settings          # propose
    python3 scratchpad/hyphenate.py system_settings --write  # write the ones that fit

The manual has no runtime reflow: manual.py wraps the paragraph itself and a word wider than
the column is simply drawn past the edge. Nintendo's own localisations solve this by breaking
the word with a real hyphen ("Прочие на-стройки", "Подтвер-ждение"), and so does this: it
lays the paragraph out exactly the way manual.py will and searches for the fewest hyphens
that bring every line inside the column.

Breaks follow the ordinary Ukrainian rules: a vowel on both sides, at least two letters on
each side, never a line starting with ь, й or an apostrophe, and never a break inside дж/дз.
Trailing punctuation does not count as a letter, so `Переконайтеся,` cannot break as
`Переконайтес-я,`.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import manual as M  # noqa: E402
from build import apply_homoglyphs, load_homoglyphs  # noqa: E402
from validate import load_widths  # noqa: E402

VOWELS = set("аеєиіїоуюяАЕЄИІЇОУЮЯ")
NEVER_STARTS = set("ьйЬЙ'ʼ-")
SONORANTS = set("влмнрВЛМНР")
CORE_RE = re.compile(r"^\W*(.*?)\W*$", re.UNICODE)
MAX_HYPHENS = 5


def candidates(word: str) -> list[str]:
    """Every hyphenation of `word` allowed by Ukrainian rules, longest prefix first.

    `word` may already be the head of a hyphenated word ("Батьківсь-"): a column narrow
    enough needs the same word broken twice, and the second break has to be found inside a
    fragment that already carries a hyphen of its own.
    """
    tail = ""
    if word.endswith("-"):
        word, tail = word[:-1], "-"

    match = CORE_RE.match(word)
    core = match.group(1)
    if len(core) < 5 or "-" in core or "{" in word:
        return []
    head = word.index(core)

    out = []
    for cut in range(2, len(core) - 1):
        left, right = core[:cut], core[cut:]
        if not (set(left) & VOWELS) or not (set(right) & VOWELS):
            continue
        if right[0] in NEVER_STARTS or left[-1] in "'ʼ-":
            continue
        if left[-1] in "дД" and right[0] in "жзЖЗ":
            continue
        # A syllable break sits either after a vowel (на-лаштування, керу-вання) or inside a
        # consonant cluster that a vowel opened (налаш-тування, керуван-ня). Cutting a
        # consonant away from the vowel it belongs to - `налашт-ування` - is neither.
        if left[-1] not in VOWELS and right[0] in VOWELS:
            continue
        # A sonorant followed by another consonant closes the syllable it sits in: фор-ма,
        # not фо-рма. Without this the search happily proposes `інфо-рмація`.
        if left[-1] in VOWELS and right[0] in SONORANTS and len(right) > 1 and right[1] not in VOWELS:
            continue
        out.append(word[: head + cut] + "-" + word[head + cut :] + tail)
    return list(reversed(out))


def widest_over(lines, flow, limit: float) -> str | None:
    """The text of the first line that runs past the column."""
    for number, line in enumerate(lines):
        if not line:
            continue
        if line[-1].x + line[-1].width - flow.margin(number) > limit:
            return "".join(piece.text for piece in line if piece.text).strip()
    return None


def source_of(over: str, text: str, table) -> str | None:
    """The piece of `text` that was drawn as `over`.

    The laid-out line is the text after homoglyph substitution - `Батькiвський` with a Latin
    `i` - so it never matches the source it came from. Reversing the substitution is not an
    option either (`i` also occurs in `Nintendo`), so the source is found by rendering the
    candidates instead. Fragments already carrying a hyphen count: a narrow column needs the
    same word broken twice.
    """
    for word in text.split():
        for part in re.split(r"(?<=-)(?=.)", word):
            if apply_homoglyphs(part, table) == over:
                return part
    return None


def solve(text: str, flow, limit: float, widths, table, budget: int) -> str | None:
    lines = M.layout(apply_homoglyphs(text, table), flow, limit, widths)
    if len(lines) > len(flow.lines):
        return None
    over = widest_over(lines, flow, limit)
    if over is None:
        return text
    if budget == 0 or " " in over:
        return None

    word = source_of(over, text, table)
    if word is None:
        return None

    for candidate in candidates(word):
        answer = solve(text.replace(word, candidate, 1), flow, limit, widths, table, budget - 1)
        if answer is not None:
            return answer
    return None


def main() -> None:
    name = sys.argv[1]
    write = "--write" in sys.argv
    cfg = M.MANUALS[name]
    source = M.source_manual(name)
    widths, table = load_widths(), load_homoglyphs()
    limits = M.budgets(source, cfg["slot"], widths)
    path = ROOT / "src" / "manuals" / f"{name}.json"
    strings = json.loads(path.read_text(encoding="utf-8"))

    fixed = stuck = 0
    for page, flows in M.pages_of(source, cfg["slot"]).items():
        for index, flow in enumerate(flows):
            key = f"{page}#{index}"
            ua = strings.get(key, {}).get("ua", "")
            if not ua:
                continue
            limit = limits[key] + M.WIDTH_SLACK
            try:
                lines = M.layout(apply_homoglyphs(ua, table), flow, limit, widths)
                M.to_edits(lines, flow)
            except M.LayoutError:
                continue
            if M.overflow(lines, flow, limit) <= 0:
                continue

            # Iterative deepening: one hyphen beats three, and depth-first search would
            # happily return the three-hyphen answer it stumbled on first.
            better = None
            for depth in range(1, MAX_HYPHENS + 1):
                better = solve(ua, flow, limit, widths, table, depth)
                if better is not None:
                    break
            if better is None or better == ua:
                stuck += 1
                print(f"MANUAL  {key}  {limits[key]:.0f}px x{len(flow.lines)}  ru={strings[key].get('ru', '')!r}")
                print(f"                ua={ua!r}")
                continue
            print(f"HYPHEN  {key}  {ua!r}\n     -> {better!r}")
            fixed += 1
            if write:
                strings[key]["ua"] = better

    if write:
        path.write_text(json.dumps(strings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n{fixed} hyphenated, {stuck} need rewording")


main()
