"""Reading and rewriting the visible text of the Nintendo Network ID account pages.

The pages live in the shared archive 0004001B00018002 as one HTML file per language.
Unlike `json/message_<lang>.json`, which the page's script consults for the handful of
messages it builds at runtime, `index_<lang>.html` carries the screens themselves: every
caption, button and paragraph is a literal in the markup.

The file is not reformatted. Every unit records the byte span its text occupies, and a
rewrite touches those spans and nothing else - comments (the originals hold Japanese
section headers), attributes, whitespace and the BOM all survive untouched.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# `<br>` is text as far as a translator is concerned - it is where the line wraps - so a
# run of text broken by it is one unit, and the tag rides along inside the string.
BREAK = re.compile(r"<br\s*/?>", re.IGNORECASE)
SKIP_ELEMENT = re.compile(r"<(script|style)\b.*?</\1\s*>", re.IGNORECASE | re.DOTALL)
COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
TAG = re.compile(r"<[^>]*>", re.DOTALL)
ARTICLE_ID = re.compile(r"<article\b[^>]*\bid=\"([^\"]+)\"", re.IGNORECASE)


@dataclass
class Unit:
    """One translatable string and the byte spans it is spelled across."""

    key: str
    text: str
    spans: list[tuple[int, int]] = field(default_factory=list)


def _dead_ranges(html: str) -> list[tuple[int, int]]:
    """Byte ranges whose text is not page text: comments and script/style bodies."""
    ranges = [m.span() for m in COMMENT.finditer(html)]
    ranges += [m.span() for m in SKIP_ELEMENT.finditer(html)]
    return sorted(ranges)


def _text_runs(html: str) -> list[tuple[int, int]]:
    """Spans of literal text - everything that is neither a tag nor inside a dead range."""
    dead = _dead_ranges(html)
    covered = [False] * len(html)
    for start, end in dead:
        for i in range(start, end):
            covered[i] = True
    for match in TAG.finditer(html):
        start, end = match.span()
        if covered[start]:
            continue
        for i in range(start, end):
            covered[i] = True

    runs: list[tuple[int, int]] = []
    start = None
    for i, is_covered in enumerate(covered):
        if is_covered:
            if start is not None:
                runs.append((start, i))
                start = None
        elif start is None:
            start = i
    if start is not None:
        runs.append((start, len(covered)))
    return [(a, b) for a, b in runs if html[a:b].strip()]


def _joins(html: str, first_end: int, second_start: int) -> bool:
    """True when only `<br>` and whitespace separate two runs - then they are one string."""
    between = html[first_end:second_start]
    return bool(between.strip()) and not BREAK.sub("", between).strip()


def units(html: str) -> list[Unit]:
    """Every translatable string in document order, keyed by `<article>` id plus position.

    The id comes from the screen the text belongs to, which makes the key readable and
    stable: markup can gain a `<div>` without renumbering anything outside its own screen.
    """
    articles = [(m.start(), m.group(1)) for m in ARTICLE_ID.finditer(html)]

    result: list[Unit] = []
    counters: dict[str, int] = {}
    for start, end in _text_runs(html):
        if result and _joins(html, result[-1].spans[-1][1], start):
            unit = result[-1]
            unit.text += BREAK.sub("<br>", html[unit.spans[-1][1]:start]) + html[start:end]
            unit.spans.append((start, end))
            continue

        article = "page"
        for position, name in articles:
            if position > start:
                break
            article = name
        counters[article] = counters.get(article, 0) + 1
        result.append(Unit(f"{article}.{counters[article]}", html[start:end], [(start, end)]))

    return result


def apply(html: str, translations: dict[str, str]) -> tuple[str, int]:
    """Return the page with every translated unit replaced, and how many were replaced.

    A unit spelled across several runs is rewritten as a whole: the first run takes the
    translation, the rest are emptied. The `<br>`s between them stay where they are, so the
    replacement carries its own - which is the point, since a translated line wraps
    differently from the one it replaces.
    """
    edits: list[tuple[int, int, str]] = []
    replaced = 0
    for unit in units(html):
        text = translations.get(unit.key)
        if not text:
            continue
        replaced += 1
        first, last = unit.spans[0], unit.spans[-1]
        edits.append((first[0], last[1], BREAK.sub("<br>", text)))

    out = []
    cursor = 0
    for start, end, text in edits:
        out.append(html[cursor:start])
        out.append(text)
        cursor = end
    out.append(html[cursor:])
    return "".join(out), replaced
