"""Extract and rebuild the text of an electronic manual (`Manual.bcma`).

    python3 tools/manual.py extract browser     # romfs dump -> src/manuals/browser.json
    python3 tools/manual.py check browser       # markers, glyphs, line budget, line count
    python3 tools/manual.py build browser       # -> dist/luma/titles/<tid>/.../Manual.bcma
    python3 tools/manual.py build all --slot en # the same, into dist_en/, over EUR_en

Nintendo's ManualEditor bakes the layout in: every rendered line is its own text pane at its
own coordinates, a highlighted word is a second pane on the same line, and a button icon is
a picture pane wedged between them. There is no reflow at runtime - the page is a stack of
absolutely positioned boxes.

So this tool does the reflow itself. It groups the panes back into a paragraph ("flow"),
hands the translator one string per paragraph, and on build re-wraps that string and moves
every pane of the paragraph to where the new line breaks put it.

The string carries the parts that are not plain text as markers, and the build refuses a
translation that does not carry the same ones:

    {i0}        the first icon of this paragraph
    {s1|...}    a run in the paragraph's second style (a highlighted word, another colour)

Limits, all of them checked rather than assumed:
  - a paragraph may not grow past the lines it already occupies, because the paragraph below
    it does not move;
  - each style has as many panes as the original used, so a translation cannot highlight
    more separate runs than the original did;
  - the line budget is the widest box that paragraph has in any of the eight official
    localisations - the same rule the MSBT translations use;
  - a paragraph with no `ua` is left in the original language, so a partial translation
    still builds.

The slot overwritten is the one the build replaces, exactly as with the MSBT text: `EUR_ru`,
or `EUR_en` with `--slot en` - see tools/variant.py. What is translated is always the Russian
document, because that is the layout the strings were written against; a build replacing
another slot copies that document into its own locale whole, pages and screenshots alike,
rather than laying the text out on a document Nintendo split into different pages. See
cmd_build() and tools/bcma.py copy_member().
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import bclyt  # noqa: E402
import bcma  # noqa: E402
import luma_hook  # noqa: E402
import variant  # noqa: E402
from build import TITLES, apply_homoglyphs, load_homoglyphs  # noqa: E402
from validate import load_charset, load_widths  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
# Glyph advances in assets/font_widths.json are for the font's own 24px em, and a manual pane
# scales them by its fontSizeX. Derived from the boxes Nintendo sized to hug their text: the
# tightest of those come out at exactly fontSize/24.
FONT_EM = 24.0
# Absolute slack, as in validate.py, but a little wider: the budget comes from Nintendo's own
# x coordinates while our lines are measured with our own glyph advances and space width, and
# the two disagree by a couple of pixels per line (fitted over 330 of Nintendo's own pane
# positions: mean 2px, p95 5px). Ten covers that and still leaves the page's own right margin
# of about twenty pixels untouched.
WIDTH_SLACK = 10.0
# An icon sits a pixel or two below the baseline of the line it belongs to, and ManualEditor
# nudges the left edge of each line, so "same line" cannot be an exact comparison.
LINE_SLACK = 2.5
# Lines of one paragraph start within a pixel or two of each other; a real change of
# margin means a different paragraph.
COLUMN_JITTER = 2.5
# How much room the next word needs to have had before a short line counts as a deliberate
# break rather than the wrap running out of space. Our pixel widths are a model of the
# renderer, not the renderer, so a line that merely looks tight must not become a `{br}`.
HARD_BREAK_SLACK = 16.0
# Nintendo leaves a hair of room to the right of the text inside the box.
BOX_PADDING = 1.6
PARTS = ("index", "large", "small")
# The Instruction Manual applet (ebird): the process that reads every manual on the console.
MANUAL_APPLET_TID = "0004003000009B02"
# The document the `ua` strings were extracted from, and whose paragraph split the keys of
# src/manuals/*.json mean. Every build translates out of this one, into its own slot.
BASE_SLOT = variant.SLOTS["ru"].manual_slot
# While the viewer asks for one constant file name, only one manual can be on the card.
SHARED_MANUAL = os.environ.get("MANUAL", "browser")
# The language picker of the viewer draws its entries from BcmaInfo.bclyt, one text pane per
# locale of the document, named after that locale. The slot the mod overwrites has to say so.
INFO_ARC = "BcmaInfo"
LANGUAGE_NAME = "Українська"
MARKER_RE = re.compile(r"\{i(\d+)\}|\{s(\d+)\|([^}]*)\}|(\{br\})")
# A no-break space is a space the text must not be broken at - `Nintendo\xa03DS` is one word.
SPACE_RE = re.compile(r"([ \t\n]+)")
# A line may break after a hyphen, and no space appears at that break.
HYPHEN_RE = re.compile(r"(?<=-)(?=.)")

MANUALS = {
    # `tid` is the dump to read the manual out of; it is also the title the manual documents,
    # which is what the viewer builds its path from. Where the build writes it is
    # TITLES[name]["tids"], so a New3DS-only sibling of the same applet gets its copy too.
    #
    # `path` is relative to work/<tid>/. The Internet Browser keeps its manual inside its own
    # romfs; every other title ships it as content index 1, so its dump lands in
    # work/<tid>/manual/Manual.bcma - see docs/dumping.md.
    #
    # `reference` is the locale extract.py writes the `en` column from; which locale the build
    # overwrites is the build's own, not the manual's - see tools/variant.py.
    "browser": {
        "tid": "0004003000009D02",
        "path": "romfs/manual/Manual.bcma",
        "reference": "EUR_en",
    },
    "system_settings": {
        "tid": "0004001000022000",
        "path": "manual/Manual.bcma",
        "reference": "EUR_en",
    },
    "activity_log": {
        "tid": "0004001000022200",
        "path": "manual/Manual.bcma",
        "reference": "EUR_en",
    },
    "download_play": {
        "tid": "0004001000022100",
        "path": "manual/Manual.bcma",
        "reference": "EUR_en",
    },
    "camera": {
        "tid": "0004001000022400",
        "path": "manual/Manual.bcma",
        "reference": "EUR_en",
    },
    "sound": {
        "tid": "0004001000022500",
        "path": "manual/Manual.bcma",
        "reference": "EUR_en",
    },
    "mii_maker": {
        "tid": "0004001000022700",
        "path": "manual/Manual.bcma",
        "reference": "EUR_en",
    },
    "mii_plaza": {
        "tid": "0004001000022800",
        "path": "manual/Manual.bcma",
        "reference": "EUR_en",
    },
    "eshop": {
        "tid": "0004001000022900",
        "path": "manual/Manual.bcma",
        "reference": "EUR_en",
    },
    "face_raiders": {
        "tid": "0004001000022D00",
        "path": "manual/Manual.bcma",
        "reference": "EUR_en",
    },
    "ar_games": {
        "tid": "0004001000022E00",
        "path": "manual/Manual.bcma",
        "reference": "EUR_en",
    },
}


class LayoutError(Exception):
    """The translation cannot be laid out on the panes the paragraph owns."""


@dataclass
class Flow:
    """One paragraph: the panes it is drawn with, grouped into the lines they sit on."""

    part: str
    page: str
    lines: list[list[bclyt.Pane]] = field(default_factory=list)
    # A pane the page does not lay out: the contents entries and the page titles are data,
    # read out of Index.bclyt and drawn by the viewer's own list widget (which truncates
    # them with an ellipsis). Their text is replaced where it stands - no reflow, no move.
    fixed: bool = False

    @property
    def key_page(self) -> str:
        return f"{self.part}/{self.page}"

    @property
    def panes(self) -> list[bclyt.Pane]:
        return [pane for line in self.lines for pane in line]

    @property
    def text_panes(self) -> list[bclyt.Pane]:
        return [pane for pane in self.panes if pane.is_text]

    @property
    def icons(self) -> list[bclyt.Pane]:
        return [pane for pane in self.panes if not pane.is_text]

    @property
    def font_size(self) -> float:
        return self.text_panes[0].font_size

    @property
    def char_space(self) -> float:
        return self.text_panes[0].char_space

    @property
    def line_height(self) -> float:
        return self.text_panes[0].line_height

    @property
    def base_y(self) -> float:
        return self._first_text(0).y

    def margin(self, line: int) -> float:
        """Where line `line` starts. The first line may be indented differently."""
        if line == 0:
            return self._first_text(0).x
        return self._first_text(min(1, len(self.lines) - 1)).x

    def icon_offset(self, pane: bclyt.Pane) -> float:
        for index, line in enumerate(self.lines):
            if pane in line:
                return pane.y - self._first_text(index).y
        raise KeyError(pane.name)

    def _first_text(self, line: int) -> bclyt.Pane:
        return next(pane for pane in self.lines[line] if pane.is_text)


def pages_of(manual: bcma.Bcma, locale: str) -> dict[str, list[Flow]]:
    """-> {'large/Page_003_large_0': [flow, ...]} in page order."""
    out: dict[str, list[Flow]] = {}
    for part in PARTS:
        for page, data in sorted(manual.read(f"{locale}_{part}").items()):
            name = page.removesuffix(".bclyt")
            out[f"{part}/{name}"] = split_page(part, name, bclyt.parse(data))
    return out


def split_page(part: str, page: str, panes: list[bclyt.Pane]) -> list[Flow]:
    """Group a page's panes into paragraphs by where they sit on it."""
    flows: list[Flow] = []
    flow: Flow | None = None
    line_y = 0.0

    for pane in panes:
        if pane.kind not in ("txt1", "pic1") or (pane.is_text and not pane.text.strip()):
            flow = None
            continue
        # Centred panes are positioned by their middle, and the ones in a manual are never
        # part of a paragraph: they are the contents entries and the page titles, each a
        # standalone string the viewer places itself.
        if pane.origin != 0:
            flow = None
            if pane.is_text:
                flows.append(Flow(part=part, page=page, lines=[[pane]], fixed=True))
            continue

        if flow is not None and pane.is_text and abs(pane.font_size - flow.font_size) > 0.01:
            flow = None

        if flow is not None:
            if abs(pane.y - line_y) <= LINE_SLACK:
                flow.lines[-1].append(pane)
                continue
            starts_line = abs((line_y - pane.y) - flow.line_height) <= LINE_SLACK and pane.is_text
            # A line that starts somewhere else is not a continuation but the next item: the
            # bullet of the following list entry sits one line down and at the outer margin.
            if starts_line and len(flow.lines) > 1 and abs(pane.x - flow.margin(1)) > COLUMN_JITTER:
                starts_line = False
            if starts_line:
                flow.lines.append([pane])
                line_y = pane.y
                continue
            flow = None

        if not pane.is_text:  # an icon with no paragraph to belong to
            continue
        flow = Flow(part=part, page=page, lines=[[pane]])
        line_y = pane.y
        flows.append(flow)

    return flows


def markup(flow: Flow, widths: dict[int, int] | None = None, limit: float = 0.0) -> str:
    """The paragraph as one string, with icons, highlighted runs and hard breaks as markers.

    Given a line budget, a break that the text did not run into is taken to be deliberate -
    Nintendo ends a line early to start a note or a list item - and becomes a `{br}` the
    translation has to keep.
    """
    base = flow.text_panes[0].style
    styles: dict[tuple, int] = {}
    icons = {pane.name: index for index, pane in enumerate(flow.icons)}

    parts: list[tuple[int | None, str]] = []
    for index, line in enumerate(flow.lines):
        if index and widths and _is_hard_break(flow, index - 1, widths, limit):
            parts.append((-1, " {br} "))
        elif index and not parts[-1][1].rstrip().endswith("-"):
            # A wrapped line is a space whether or not one is stored - except after a hyphen,
            # where the next line continues the word.
            parts.append((-1, " "))
        for pane in line:
            if not pane.is_text:
                parts.append((-1, f"{{i{icons[pane.name]}}}"))
                continue
            style = None if pane.style == base else styles.setdefault(pane.style, len(styles) + 1)
            # A line break is a space, unless Nintendo broke the line at a hyphen: there the
            # next line continues the word (`Інтернет-` + `налаштування`).
            text = re.sub(r"(?<!-)\n", " ", pane.text).replace("\n", "")
            if parts and parts[-1][0] == style:
                parts[-1] = (style, parts[-1][1] + text)
            else:
                parts.append((style, text))

    out = ""
    for style, text in _join_runs(parts):
        out += text if style is None or style < 0 else f"{{s{style}|{text.strip()}}}"
    return " ".join(out.split())


def _join_runs(parts: list[tuple[int | None, str]]) -> list[tuple[int | None, str]]:
    """A highlighted run split across a line break is one run, not two markers."""
    out = list(parts)
    index = 0
    while index + 2 < len(out):
        left, gap, right = out[index], out[index + 1], out[index + 2]
        if left[0] == right[0] and left[0] not in (None, -1) and gap == (-1, " "):
            out[index : index + 3] = [(left[0], f"{left[1].strip()} {right[1].strip()}")]
            continue
        index += 1
    return out


def _is_hard_break(flow: Flow, line: int, widths: dict[int, int], limit: float) -> bool:
    """Did line `line` end before it had to?"""
    following = flow.lines[line + 1]
    first = following[0]
    word = (first.text.split() or [""])[0] if first.is_text else ""
    extra = text_width(f" {word}", flow, widths) if first.is_text else first.width
    return drawn_width(flow, widths, line) + extra + HARD_BREAK_SLACK <= limit


def markers(text: str) -> list[str]:
    return sorted(match.group(0).split("|")[0] for match in MARKER_RE.finditer(text))


def text_width(text: str, flow: Flow, widths: dict[int, int]) -> float:
    advance = sum(widths.get(ord(ch), 0) for ch in text)
    return advance * flow.font_size / FONT_EM + flow.char_space * max(len(text) - 1, 0)


def drawn_width(flow: Flow, widths: dict[int, int], line: int | None = None) -> float:
    """How wide the paragraph is drawn - its widest line, or one particular line.

    Measured from the text rather than from the boxes: ManualEditor leaves the boxes wider
    than their contents and lets them overlap, so their edges say nothing about the column.
    """
    lines = enumerate(flow.lines) if line is None else [(line, flow.lines[line])]
    return max(
        last.x
        - flow.margin(index)
        + (text_width(last.text.replace("\n", ""), flow, widths) if last.is_text else last.width)
        for index, (last) in ((index, line[-1]) for index, line in lines)
    )


@dataclass
class Piece:
    """A laid-out run: a stretch of text in one style, or one icon."""

    style: int                    # 0 = the paragraph's own style, -1 = an icon
    text: str = ""
    icon: bclyt.Pane | None = None
    x: float = 0.0
    width: float = 0.0
    spaced: bool = False          # a space separates it from the piece before it


def _atoms(text: str):
    """-> (style, payload) runs; style -1 marks an icon and payload is its index."""
    pos = 0
    for match in MARKER_RE.finditer(text):
        if match.start() > pos:
            yield 0, text[pos : match.start()]
        if match.group(1) is not None:
            yield -1, int(match.group(1))
        elif match.group(4):
            yield -2, None
        else:
            yield int(match.group(2)), match.group(3)
        pos = match.end()
    if pos < len(text):
        yield 0, text[pos:]


def _words(
    text: str, flow: Flow, widths: dict[int, int], limit: float
) -> list[tuple[bool, list[Piece]]]:
    """Break the markup into words -> [(glued to the previous word, pieces), ...].

    A word can be several pieces (`{s1|HOME}.` is one word in two styles), and a hyphen is a
    place the line may break without a space appearing there - which is how Nintendo fits
    `Інтернет-` and `налаштування` onto two lines.
    """
    icons = {index: pane for index, pane in enumerate(flow.icons)}
    words: list[tuple[bool, list[Piece]]] = [(False, [])]

    def open_word(glue: bool) -> None:
        if words[-1][1]:
            words.append((glue, []))

    for style, payload in _atoms(text):
        if style == -2:
            open_word(False)
            words[-1][1].append(Piece(style=-2))
            open_word(False)
            continue
        if style < 0:
            if payload not in icons:
                raise LayoutError(f"no icon {{i{payload}}} on this paragraph")
            icon = icons[payload]
            words[-1][1].append(Piece(style=-1, icon=icon, width=icon.width))
            continue
        # A highlighted run is one pane. Breaking it across lines would need a second pane in
        # that colour, which the page does not have, so it stays whole while it fits a line.
        # `while it fits` has to count what the run is glued to: the markup carries no space
        # between `Примітка.` and the run that follows it, so the two are one word, and a run
        # that fits on its own can still push that word off the page.
        whole = text_width(payload, flow, widths)
        glued = sum(piece.width for piece in words[-1][1])
        if style and " " in payload.strip() and glued + whole <= limit:
            words[-1][1].append(Piece(style=style, text=payload.strip(), width=whole))
            continue
        for chunk in re.split(SPACE_RE, payload):
            if not chunk:
                continue
            if SPACE_RE.fullmatch(chunk):
                open_word(False)
                continue
            for index, part in enumerate(HYPHEN_RE.split(chunk)):
                if index:
                    open_word(True)
                words[-1][1].append(
                    Piece(style=style, text=part, width=text_width(part, flow, widths))
                )

    return [word for word in words if word[1]]


def layout(text: str, flow: Flow, limit: float, widths: dict[int, int]) -> list[list[Piece]]:
    """Wrap the marked-up translation into lines of pieces, greedily."""
    space = text_width(" ", flow, widths)
    lines: list[list[Piece]] = [[]]
    x = flow.margin(0)

    for glue, word in _words(text, flow, widths, limit):
        if word[0].style == -2:
            lines.append([])
            x = flow.margin(len(lines) - 1)
            continue
        width = sum(piece.width for piece in word)
        gap = 0.0 if glue or not lines[-1] else space
        if lines[-1] and x + gap + width > flow.margin(len(lines) - 1) + limit:
            lines.append([])
            x = flow.margin(len(lines) - 1)
            gap = 0.0
        x += gap
        for index, piece in enumerate(word):
            piece.x = x
            piece.spaced = index == 0 and gap > 0
            lines[-1].append(piece)
            x += piece.width

    return lines


def overflow(lines: list[list[Piece]], flow: Flow, limit: float) -> float:
    """How far past the column the widest laid-out line reaches, in pixels.

    layout() wraps greedily, so it can only keep a line inside the column by moving the next
    word down - and a word that is wider than the column on its own has nowhere to go. It is
    put on a line of its own and drawn past the right edge, silently: nothing downstream
    looks at how wide the lines came out. That is what clipped `налаштування` out of the
    contents cells and pushed the connection warnings off the page on hardware.
    """
    worst = 0.0
    for index, line in enumerate(lines):
        if not line:
            continue
        last = line[-1]
        worst = max(worst, last.x + last.width - flow.margin(index) - limit)
    return worst


def to_edits(lines: list[list[Piece]], flow: Flow) -> dict[str, bclyt.Edit]:
    """Put the laid-out lines back on the paragraph's own panes."""
    if len(lines) > len(flow.lines):
        raise LayoutError(f"needs {len(lines)} lines, the paragraph has {len(flow.lines)}")

    if flow.fixed:
        pane = flow.text_panes[0]
        piece = _merged(lines[0])[0]
        return {pane.name: bclyt.Edit(text=piece.text, width=max(pane.width, piece.width))}

    base = flow.text_panes[0].style
    pools: dict[int, list[bclyt.Pane]] = {}
    styles: dict[tuple, int] = {}
    for pane in flow.text_panes:
        style = 0 if pane.style == base else styles.setdefault(pane.style, len(styles) + 1)
        pools.setdefault(style, []).append(pane)

    edits: dict[str, bclyt.Edit] = {}
    used: set[str] = set()
    for index, line in enumerate(lines):
        y = flow.base_y - index * flow.line_height
        for piece in _merged(line):
            if piece.icon is not None:
                edits[piece.icon.name] = bclyt.Edit(x=piece.x, y=y + flow.icon_offset(piece.icon))
                used.add(piece.icon.name)
                continue
            pool = pools.get(piece.style, [])
            free = [pane for pane in pool if pane.name not in used]
            if not free:
                raise LayoutError(
                    f"out of panes for style {piece.style} (the original has {len(pool)})"
                )
            pane = free[0]
            used.add(pane.name)
            edits[pane.name] = bclyt.Edit(
                text=piece.text, x=piece.x, y=y, width=piece.width + BOX_PADDING
            )

    for pane in flow.text_panes:
        if pane.name not in used:
            edits[pane.name] = bclyt.Edit(text="")

    return edits


def _merged(line: list[Piece]) -> list[Piece]:
    """Neighbouring pieces in one style are drawn by one pane, spaces and all."""
    out: list[Piece] = []
    for piece in line:
        if out and piece.icon is None and out[-1].icon is None and out[-1].style == piece.style:
            previous = out[-1]
            previous.text += (" " if piece.spaced else "") + piece.text
            previous.width = piece.x + piece.width - previous.x
        else:
            out.append(Piece(**vars(piece)))
    return out


def aligned(manual: bcma.Bcma, slot: str, other: str) -> dict[str, list[Flow]]:
    """The other localisation's paragraphs, page by page, where the two agree on the split.

    The n-th paragraph of a page is the same paragraph in every language - but only while the
    page holds the same paragraphs at all. Nintendo reorders and merges them (the English
    browser page 3 lists Hide Menu before Page Info, the Russian one does not), so a page
    whose paragraph count differs is dropped rather than mismatched.
    """
    mine = pages_of(manual, slot)
    theirs = pages_of(manual, other)
    return {
        page: flows
        for page, flows in theirs.items()
        if page in mine and len(flows) == len(mine[page])
    }


def budgets(manual: bcma.Bcma, slot: str, widths: dict[int, int]) -> dict[str, float]:
    """How wide a line of each paragraph may be -> {key: pixels}.

    The widest line that paragraph is drawn with in any of the eight official localisations:
    Nintendo already wrapped the same text to the same column eight times, so the longest
    line any of them produced is a line the page is known to hold.
    """
    out: dict[str, float] = {}
    # Every contents entry is drawn in the same slot of the same list, so the slot - not the
    # entry - is the budget: the widest entry the page has in any language. Measured per
    # entry, `Introduction` would get a budget only as wide as the word.
    slots: dict[str, float] = {}
    fixed: dict[str, str] = {}

    for locale in manual.locales():
        pages = pages_of(manual, slot) if locale == slot else aligned(manual, slot, locale)
        for page, flows in pages.items():
            for index, flow in enumerate(flows):
                key = f"{page}#{index}"
                if locale != slot and key not in out and not flow.fixed:
                    continue
                width = drawn_width(flow, widths)
                if flow.fixed:
                    slots[page] = max(slots.get(page, 0.0), width)
                    if locale == slot:
                        fixed[key] = page
                out[key] = max(out.get(key, 0.0), width)

    return out | {key: slots[page] for key, page in fixed.items()}


def load_json(name: str) -> dict:
    path = ROOT / "src" / "manuals" / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def source_path(name: str) -> Path:
    cfg = MANUALS[name]
    return ROOT / "work" / cfg["tid"] / cfg["path"]


def source_manual(name: str) -> bcma.Bcma:
    return bcma.load(source_path(name))


def cmd_extract(name: str) -> None:
    cfg = MANUALS[name]
    manual = source_manual(name)
    existing = load_json(name)
    widths = load_widths()
    limits = budgets(manual, BASE_SLOT, widths)
    reference = aligned(manual, BASE_SLOT, cfg["reference"])

    out: dict[str, dict] = {}
    for page, flows in pages_of(manual, BASE_SLOT).items():
        for index, flow in enumerate(flows):
            key = f"{page}#{index}"
            english = reference.get(page)
            out[key] = {
                "lines": len(flow.lines),
                "width": round(limits[key], 1),
                "en": markup(english[index], widths, limits[key]) if english else "",
                "ru": markup(flow, widths, limits[key]),
                "ua": existing.get(key, {}).get("ua", ""),
            }

    path = ROOT / "src" / "manuals" / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    chars = sum(len(entry["ru"]) for entry in out.values())
    print(f"{path.relative_to(ROOT)}: {len(out)} paragraphs, {chars} characters")


def _problems(name: str) -> tuple[list[str], list[str], int, int]:
    """-> (problems, wide, translated, total).

    A paragraph that runs past its column is reported apart from the rest, because it is a
    translation decision rather than a broken build: the column is the widest line any of
    Nintendo's eight localisations drew there, and a handful of Ukrainian UI terms are simply
    longer than any of them (`Стрільба` where Russian has `Тир`). Renaming the term to fit
    the manual would leave the manual naming a button the console does not have, so those are
    listed and left to the translator instead of stopping the build.

    Always the Russian document, whichever slot the build writes into: that is the layout the
    `ua` strings were written against, and the one cmd_build() lays them out on.
    """
    manual = source_manual(name)
    strings = load_json(name)
    widths, table, charset = load_widths(), load_homoglyphs(), load_charset()
    limits = budgets(manual, BASE_SLOT, widths)

    problems: list[str] = []
    wide: list[str] = []
    translated = total = 0
    for page, flows in pages_of(manual, BASE_SLOT).items():
        for index, flow in enumerate(flows):
            total += 1
            key = f"{page}#{index}"
            entry = strings.get(key, {})
            ua = entry.get("ua", "")
            if not ua:
                continue
            translated += 1
            rendered = apply_homoglyphs(ua, table)

            if markers(ua) != markers(entry.get("ru", "")):
                problems.append(f"{key}: markers {markers(ua)} != {markers(entry.get('ru', ''))}")
                continue

            body = MARKER_RE.sub(lambda m: m.group(3) or "", rendered)
            missing = sorted({ch for ch in body if ord(ch) not in charset and not ch.isspace()})
            if missing:
                problems.append(f"{key}: missing glyphs {missing}")

            limit = limits[key] + WIDTH_SLACK
            try:
                lines = layout(rendered, flow, limit, widths)
                to_edits(lines, flow)
            except LayoutError as error:
                problems.append(f"{key}: {error}: {ua[:60]!r}")
                continue

            # A zero-width column means no localisation drew that paragraph, so there is no
            # width to compare against - the `+Скорость-` gauge of the Camera manual, drawn
            # by the artwork rather than by a text pane.
            past = overflow(lines, flow, limit) if limits[key] else 0.0
            if past > 0:
                wide.append(
                    f"{key}: {past:.0f}px past the {limits[key]:.0f}px column: {ua[:60]!r}"
                )

    return problems, wide, translated, total


def cmd_check(name: str) -> list[str]:
    problems, wide, translated, total = _problems(name)
    print(
        f"{name}: {translated} translated paragraphs of {total}, "
        f"{len(problems)} problems, {len(wide)} past their column"
    )
    for problem in problems:
        print(f"  ✗ {problem}")
    for line in wide:
        print(f"  ! {line}")
    return problems


def language_name(
    manual: bcma.Bcma, slot: str, widths: dict[int, int], table: dict[str, str]
) -> dict[str, bytes]:
    """The document's own name for the locale the mod overwrites.

    The picker lists one pane per locale, `EUR_en` through `EUR_ru`, each holding the
    language written in itself. The slot this build replaces has to read `Українська` -
    otherwise the entry that selects the Ukrainian text still says `Русский` or `English`.
    """
    files = manual.read(INFO_ARC)
    page = f"{INFO_ARC}.bclyt"
    rendered = apply_homoglyphs(LANGUAGE_NAME, table)
    pane = next(p for p in bclyt.parse(files[page]) if p.name == slot)
    drawn = sum(widths.get(ord(ch), 0) for ch in rendered) * pane.font_size / FONT_EM
    if drawn > pane.width:
        raise SystemExit(f"{LANGUAGE_NAME!r} is {drawn:.0f}px in the {pane.width:.0f}px {slot} pane")

    return files | {page: bclyt.rewrite(files[page], {slot: bclyt.Edit(text=rendered)})}


def cmd_build(name: str) -> None:
    if cmd_check(name):
        raise SystemExit("fix the problems above first")

    cfg = MANUALS[name]
    manual = source_manual(name)
    strings = load_json(name)
    widths, table = load_widths(), load_homoglyphs()
    limits = budgets(manual, BASE_SLOT, widths)

    # The document translated is always the Russian one - it is what the `ua` strings were
    # laid out against. A build that replaces another slot gets it wholesale first, pages and
    # screenshots alike, and the translation is written on that copy: the localisations do not
    # split a chapter into the same pages, so paragraph-by-paragraph the English document
    # would take barely half the text and mix the two languages on a page. The Russian slot
    # is left as Nintendo wrote it, which is what the console shows if you switch to it.
    slot = variant.current().manual_slot
    if slot != BASE_SLOT:
        for part in (*PARTS, "texture"):
            manual.copy_member(f"{BASE_SLOT}_{part}", f"{slot}_{part}")

    changed = 0
    for part in PARTS:
        rebuilt: dict[str, bytes] = {}
        for page, data in manual.read(f"{BASE_SLOT}_{part}").items():
            name_ = page.removesuffix(".bclyt")
            edits: dict[str, bclyt.Edit] = {}
            for index, flow in enumerate(split_page(part, name_, bclyt.parse(data))):
                key = f"{part}/{name_}#{index}"
                ua = strings.get(key, {}).get("ua", "")
                if not ua:
                    continue
                changed += 1
                rendered = apply_homoglyphs(ua, table)
                limit = limits[key] + WIDTH_SLACK
                edits |= to_edits(layout(rendered, flow, limit, widths), flow)
            rebuilt[page] = bclyt.rewrite(data, edits) if edits else data
        manual.write(f"{slot}_{part}", rebuilt)

    manual.write(INFO_ARC, language_name(manual, slot, widths, table))

    image = manual.build()
    for out in _destinations(name, cfg):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(image)
        print(f"{out.relative_to(ROOT)}: {len(image)} bytes, {changed} paragraphs replaced")


def _destinations(name: str, cfg: dict) -> list[Path]:
    """Where the built manual goes.

    Two places, and only the second one is the one the console actually reads today:

      - the title's own romfs, where the file came from. The Internet Browser is the only
        title that carries its manual there, and nothing reads it: the manual button - both
        from the HOME Menu and from inside the browser - shows the Russian document, which
        means the viewer takes it from content index 1 of the title, not from this file.
        It is still shipped, because it is where the file belongs.

      - the Instruction Manual's own romfs folder, named after the title the manual belongs
        to. tools/luma_hook.py renames that viewer's `man:` mount to `rex:` and has it build
        the path from the documented title's id, so LayeredFS serves
        `<title id>.bcma` from here - and falls back to the console's own manual for every
        title this mod has no file for.
    """
    tids = TITLES.get(name, {}).get("tids", [cfg["tid"]])
    # Nothing goes into the documented title's own folder. The Internet Browser is the only
    # title that keeps a copy of its manual in its romfs, and that copy is dead: shipping it
    # translated left the manual in Russian, which is what proved the viewer reads the
    # document out of the title's content instead. Only the viewer's folder matters.
    out: list[Path] = []

    applet = variant.dist() / "luma" / "titles" / MANUAL_APPLET_TID / "romfs"
    spec = luma_hook.HOOK_PATCHES[MANUAL_APPLET_TID]["manual_path"]
    if luma_hook.manual_path_mode() == "full":
        # The viewer builds the name from the low word of the title id, and only for the
        # titles listed in the patch, so the two have to agree.
        listed = {tid.upper() for tid in spec["titles"]}
        missing = [tid for tid in tids if tid.upper() not in listed]
        if missing:
            raise SystemExit(
                f"{name}: {', '.join(missing)} is not in manual_path['titles'] in "
                f"tools/luma_hook.py - the viewer would ask for the constant name and show "
                f"the console's own manual instead"
            )
        return out + [applet / f"{int(tid, 16) & 0xFFFFFFFF:08x}.bcma" for tid in tids]

    # Without that patch the viewer asks for one constant name whatever title it documents,
    # so the SD card can hold exactly one manual. MANUAL= picks which.
    if name != SHARED_MANUAL:
        print(f"{name}: built, not shipped - the console reads one manual and MANUAL={SHARED_MANUAL}")
        return out
    return out + [applet / "Manual.bcma"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("extract", "check", "build"))
    parser.add_argument("name", choices=[*sorted(MANUALS), "all"])
    variant.add_argument(parser)
    args = parser.parse_args()

    variant.select(args.slot)
    run = {"extract": cmd_extract, "check": cmd_check, "build": cmd_build}[args.command]
    for name in sorted(MANUALS) if args.name == "all" else [args.name]:
        # A title whose manual has not been dumped yet is not an error: it is simply not
        # translated, and the console keeps showing its own.
        if not source_path(name).is_file():
            print(f"{name}: no dump at {source_path(name).relative_to(ROOT)}, skipped")
            continue
        run(name)


if __name__ == "__main__":
    main()
