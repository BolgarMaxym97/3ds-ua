"""Validate the translations before building.

Usage:
    python3 tools/validate.py            # every strings project
    python3 tools/validate.py home_menu

Rules (every violation is an error):
  1. a character missing from assets/font_charset.txt after homoglyph substitution
     would render as an empty box
  2. line width in pixels above the widest official localisation x WIDTH_LIMIT
     would be clipped
  3. more lines than the tallest official localisation would overflow the dialog
  4. a control tag whose shape (group and type, argument aside) appears in no official
     localisation anywhere in the file is invented - the argument is data, so a colour tag
     with a colour Nintendo never used is still a colour tag
  5. a malformed tag token - unless the same brace run appears verbatim in an official
     localisation of that label, i.e. it is literal text and not a tag at all (the software
     keyboard warnings list `{|}~` among the characters a password may contain)
  6. the set of format specifiers (%d, %ls, %H, ...) matches no official localisation of
     that label: the app would print garbage or crash. Any localisation's set is accepted,
     because languages legitimately differ (%d %n '%y in English vs %d.%M.%y in German).
  7. a character missing from the *HUD* font in one of the labels that font draws. The
     clock line on the top screen has its own 15x17 bitmap subset per title, far smaller
     than the system font, and a letter it lacks is simply not drawn - which is how
     Ukrainian Sunday spent a release showing as `( )`.

Labels that share one UI slot (e.g. every entry of the language list) can be grouped
with `budget_groups` regexes in TITLES: the group's widest member sets the budget for
all of them, because the slot must already fit the longest sibling.

The budgets (width, height, allowed tags) are the maximum/union across ALL language
folders of the title: the UI has to fit the longest official localisation, so that is
the real limit rather than any single language. This also means the language slot
(EU_English / EU_Russian) can be switched without rewriting the translation - which is
why this runs once and covers both builds, and why it takes no `--slot`.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import bcfnt  # noqa: E402
import variant  # noqa: E402
from build import TITLES, apply_homoglyphs, load_all_langs, load_homoglyphs, load_hud_glyphs  # noqa: E402
from msbt import TOKEN_RE  # noqa: E402
from msbt import parse as msbt_parse  # noqa: E402
from store import open_store  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
# Which slot the mod replaces changes nothing here - the budgets are the widest official
# localisation of every label and the reference is English in both builds - so the checks
# read the Russian slot and validating once covers dist/ and dist_en/ alike.
BASE_SLOT = "ru"
# The budget is already the widest official localisation, so anything past it is wider than
# anything Nintendo ever put in that pane. There is no headroom to give: a 5% allowance here
# let 175 strings through that overflow their button on hardware. Only a couple of pixels of
# absolute slack remain, for rounding in the renderer.
WIDTH_LIMIT = 1.0
# Slack is absolute on purpose. A percentage grows with the string, which is backwards: it
# handed a 500px dialog 25px of room while giving a button almost none. Eight pixels is
# about one narrow glyph - enough that a word like "Відкрити" is not rewritten for being a
# hair wider than "Открыть", and far too little to hide a real overflow.
#
# Known blind spot: eight pixels is one narrow glyph on a 400px dialog line but a tenth of
# a button, and STR_CONTRIBUTE in miiverse_post reached QA wrapped to two lines while
# sitting at exactly budget + 8. Tightening this catches that class of bug, but 135
# translations currently clear their budget by 3-8px (~30 of them on button-sized panes),
# so the limit cannot drop until those are retranslated.
WIDTH_SLACK = 8
BRACE_RE = re.compile(r"\{[^}]*\}")
# `{t:1.0:XXXX}` and `{t:1.1:XXXX}` scale the font: 0x6400 is 100%, 0x4600 is 70%. Both
# shapes exist in the dumps and a label often carries one of each, so both are read here -
# ignoring `{t:1.1}` inflated the budget of every label the officials shrank with it, which
# is how the Notifications launch button and the friend card shipped clipped. Measuring the glyphs
# without it made the budget meaningless - the widest official localisation is usually the
# one that squeezed itself the most, so a full-size Ukrainian label measured "narrower" than
# a shrunken Dutch one and still overflowed the pane on hardware (the Camera and Sound
# buttons of release 0.9.0). The pane holds the widest *painted* line, not the widest glyph run.
SCALE_RE = re.compile(r"\{(/?)t:1\.([01])(?::([0-9a-fA-F]*))?\}")
SCALE_100 = 0x6400
# The labels the HUD font draws, as opposed to the rest of hud.msbt: the clock line's
# date format and its parts. `lau_connect*` and friends sit below it in the system font,
# which is why this is a list of what the small font touches rather than a whole file.
HUD_LABEL_RE = re.compile(r"lau_(?:date|birthday|hours|minutes)|(?:month|day|week)_\w+")
# %% is a literal percent sign and must survive translation, so it is matched first;
# a space is not part of the flags here - it would swallow the next word's first letter.
FORMAT_RE = re.compile(r"%%|%[-+#0-9.]*(?:ls|lc|[a-zA-Z])")


@dataclass
class Budget:
    width_px: int = 0
    lines: int = 0
    tags: set[str] = field(default_factory=set)
    format_sets: set[tuple[str, ...]] = field(default_factory=set)
    # Brace runs the original text itself carries, tags and literal punctuation alike.
    braces: set[str] = field(default_factory=set)
    # Every tag *shape* - closing slash, group, type - used anywhere in this file, with the
    # argument dropped. Shared by every label of the title, unlike the sets above.
    tag_shapes: set[tuple[str, str, str]] = field(default_factory=set)


def load_charset() -> set[int]:
    text = (ROOT / "assets" / "font_charset.txt").read_text(encoding="utf-8")
    return {int(line.split("\t")[0][2:], 16) for line in text.splitlines() if line.startswith("U+")}


def load_widths() -> dict[int, int]:
    data = json.loads((ROOT / "assets" / "font_widths.json").read_text(encoding="utf-8"))
    return {int(code, 16): width for code, width in data.items()}


def hud_charset(cfg: dict) -> set[int]:
    """What the title's HUD font can draw once the build has added its glyphs to it."""
    # `hud_font_from` names a donor for the two applets that read the font from a shared
    # archive rather than carrying it - see build_hud_font() in tools/build.py.
    owner = cfg.get("hud_font_from") or cfg["source_tid"]
    path = ROOT / "work" / owner / "romfs" / cfg["hud_font"]
    font = bcfnt.parse(path.read_bytes())
    return set(font.cmap) | set(load_hud_glyphs())


def strip_tags(text: str) -> str:
    return TOKEN_RE.sub("", text)


def line_widths(text: str, widths: dict[int, int]) -> list[float]:
    """Painted width of every line in pixels, honouring the font-scale tags."""
    # Both scale tags can be open at once - the originals nest `{t:1.1}` around `{t:1.0}` -
    # so each type keeps its own factor and the painted size is their product.
    scales = {"0": 1.0, "1": 1.0}
    lines = [0.0]
    index = 0

    while index < len(text):
        tag = TOKEN_RE.match(text, index)
        if tag:
            scaling = SCALE_RE.fullmatch(tag.group(0))
            if scaling:
                # `{/t:1.0}` and a valueless `{t:1.0}` end the run and restore full size.
                value = scaling.group(3)
                scales[scaling.group(2)] = (
                    int(value, 16) / SCALE_100 if value and not scaling.group(1) else 1.0
                )
            index = tag.end()
            continue
        char = text[index]
        index += 1
        if char == "\n":
            lines.append(0.0)
            continue
        lines[-1] += widths.get(ord(char), 0) * scales["0"] * scales["1"]

    return lines


def pixel_width(text: str, widths: dict[int, int]) -> int:
    """Painted width of the widest line in pixels (tags are not rendered)."""
    return round(max(line_widths(text, widths), default=0))


def label_budgets(name: str, widths: dict[int, int]) -> dict[str, Budget]:
    """Per-label budgets: max width and line count, union of tags across all languages."""
    cfg = TITLES[name]
    store = open_store(cfg, ROOT / "work" / cfg["source_tid"] / "romfs")
    budgets: dict[str, Budget] = {}

    # One set for the whole title, handed to every label: which tags exist at all is a
    # property of the renderer, not of the string that happens to use one.
    shapes: set[tuple[str, str, str]] = set()

    for lang in store.languages():
        for data in store.read(lang).values():
            msbt = msbt_parse(data)
            for index, text in enumerate(msbt.texts):
                label = msbt.label_of(index) or f"__index_{index}"
                budget = budgets.setdefault(label, Budget(tag_shapes=shapes))
                budget.width_px = max(budget.width_px, pixel_width(text, widths))
                budget.lines = max(budget.lines, text.count("\n") + 1)
                tags = set(TOKEN_RE.findall(text))
                budget.tags |= tags
                shapes |= {tag[:3] for tag in tags}
                budget.braces |= set(BRACE_RE.findall(text))
                budget.format_sets.add(tuple(sorted(FORMAT_RE.findall(text))))

    for pattern in cfg.get("budget_groups", []):
        group = [label for label in budgets if re.fullmatch(pattern, label)]
        if len(group) < 2:
            continue
        shared = Budget(
            width_px=max(budgets[label].width_px for label in group),
            lines=max(budgets[label].lines for label in group),
            tags=set().union(*(budgets[label].tags for label in group)),
            format_sets=set().union(*(budgets[label].format_sets for label in group)),
            braces=set().union(*(budgets[label].braces for label in group)),
            tag_shapes=shapes,
        )
        for label in group:
            budgets[label] = shared

    return budgets


def check_entry(
    label: str,
    entry: dict[str, str],
    charset: set[int],
    table: dict[str, str],
    widths: dict[int, int],
    budget: Budget,
    hud: set[int] | None = None,
) -> list[str]:
    ua = entry.get("ua", "")
    if not ua:
        return []

    problems: list[str] = []

    if hud is not None and HUD_LABEL_RE.fullmatch(label):
        missing = {ch for ch in strip_tags(apply_homoglyphs(ua, table)) if ord(ch) not in hud}
        if missing:
            chars = " ".join(f"{ch!r} U+{ord(ch):04X}" for ch in sorted(missing))
            problems.append(f"{label}: characters missing from the HUD font: {chars}")

    for brace in BRACE_RE.findall(ua):
        # Not a tag and not in the original either - a typo in a tag, which the renderer
        # would print raw. A brace run the original carries verbatim is literal text.
        if not TOKEN_RE.fullmatch(brace) and brace not in budget.braces:
            problems.append(f"{label}: malformed tag token {brace!r}")

    dst_formats = tuple(sorted(FORMAT_RE.findall(ua)))
    if budget.format_sets and dst_formats not in budget.format_sets:
        allowed = sorted(budget.format_sets)
        problems.append(f"{label}: format specifiers {list(dst_formats)} match no localisation {allowed}")

    # A tag this label never carried can still be Nintendo's own with a different argument -
    # `{t:0.3:RRGGBBAA}` is one colour tag, not one tag per colour. So a tag the label does
    # not know is only invented when its *shape* appears nowhere in the file either.
    unknown = {
        tag for tag in set(TOKEN_RE.findall(ua)) - budget.tags
        if tag[:3] not in budget.tag_shapes
    }
    if unknown:
        problems.append(f"{label}: tags present in no official localisation: {sorted(unknown)}")

    rendered = apply_homoglyphs(ua, table)
    bad = {ch for ch in strip_tags(rendered) if ch not in "\n\r\t" and ord(ch) not in charset}
    if bad:
        chars = " ".join(f"{ch!r} U+{ord(ch):04X}" for ch in sorted(bad))
        problems.append(f"{label}: characters missing from the font: {chars}")

    dst_px = pixel_width(rendered, widths)
    if budget.width_px and dst_px > budget.width_px * WIDTH_LIMIT + WIDTH_SLACK:
        problems.append(f"{label}: {dst_px}px exceeds budget {budget.width_px}px (x{WIDTH_LIMIT})")

    dst_lines = ua.count("\n") + 1
    if budget.lines and dst_lines > budget.lines:
        problems.append(f"{label}: {dst_lines} lines exceed the {budget.lines}-line maximum across localisations")

    return problems


LETTERS_RE = re.compile(r"[^\W\d_]{2}")


def untranslatable(name: str) -> set[str]:
    """Labels there is nothing to translate in: empty, or with no word in them.

    Counting these as outstanding work is what made the coverage look like a third of the
    text was missing. What is left after stripping tags is things like `%ls`, `1`, `:` and
    the language names a picker deliberately shows in their own language.
    """
    cfg = TITLES[name]
    store = open_store(cfg, ROOT / "work" / cfg["source_tid"] / "romfs")

    def texts(lang: str) -> dict[str, str]:
        out: dict[str, str] = {}
        for data in store.read(lang).values():
            msbt = msbt_parse(data)
            for index, text in enumerate(msbt.texts):
                out[msbt.label_of(index) or f"__index_{index}"] = text
        return out

    slot = texts(cfg["lang"][BASE_SLOT])
    reference = texts(cfg["ref_lang"])
    skip = {label for label, text in slot.items() if not LETTERS_RE.search(strip_tags(text))}
    # Nintendo shipping the same text in two languages means the string is not language
    # dependent: `WPA2-PSK (AES)`, `%ls`, the Latin key rows, and the language names a
    # picker deliberately shows in their own language. Translating those would be a bug.
    skip |= {label for label, text in slot.items() if reference.get(label) == text}
    return skip


def validate(
    name: str, charset: set[int], table: dict[str, str], widths: dict[int, int]
) -> tuple[int, int, list[str]]:
    cfg = TITLES[name]
    strings_dir = ROOT / "src" / "strings" / name
    budgets = label_budgets(name, widths)
    hud = hud_charset(cfg) if cfg.get("hud_font") else None
    skip = untranslatable(name)
    total = translated = 0
    problems: list[str] = []

    # _all_langs.json holds plain {label: text} written into every slot, so it is checked
    # against the same budgets but without the en/ua entry shape. Both builds' sections are
    # checked, because both ship.
    for slot_key in variant.SLOTS:
        for key, labels in load_all_langs(strings_dir, slot_key).items():
            for label, text in labels.items():
                entry = {"en": "", "ua": text}
                for problem in check_entry(label, entry, charset, table, widths, budgets.get(label, Budget()), hud):
                    problems.append(f"_all_langs.json [{slot_key}]: {problem}")

    for json_file in sorted(strings_dir.glob("*.json")):
        if json_file.name.startswith("_"):
            continue
        entries = json.loads(json_file.read_text(encoding="utf-8"))
        for label, entry in entries.items():
            if label not in skip:
                total += 1
                if entry.get("ua"):
                    translated += 1
            for problem in check_entry(label, entry, charset, table, widths, budgets.get(label, Budget()), hud):
                problems.append(f"{json_file.name}: {problem}")

    return total, translated, problems


def validate_area(charset: set[int], table: dict[str, str], widths: dict[int, int]) -> tuple[int, list[str]]:
    """Check the country and region names of the `area` archive.

    These are not MSBT strings and have no per-label budget: the slot is as wide as the
    widest of the twelve official names in the same file, which is the same reasoning
    validate() uses, only per file instead of per label - WIDTH_SLACK included, for the
    same reason it exists there. Skipped, not failed, when the archive has not been
    dumped - it is one GodMode9 copy and most contributors will not have it.
    """
    import area as area_mod

    strings = ROOT / "src" / "strings" / "area"
    source = ROOT / "work" / "0004009B00010402" / "romfs"
    if not source.is_dir() or not strings.is_dir():
        return 0, []

    problems: list[str] = []
    checked = 0
    for json_file in sorted(strings.glob("EU_*.json")):
        entries = json.loads(json_file.read_text(encoding="utf-8"))
        stem = json_file.stem.split("_", 1)[1]
        original = source / "EU" / f"{stem}_LZ.bin"
        if not original.is_file():
            problems.append(f"{json_file.name}: no {original.name} in the dump")
            continue
        table_file = area_mod.load(original)
        budget = max(
            pixel_width(name, widths)
            for record in table_file.records
            for name in record.names[:12]
            if name
        )
        for key, entry in entries.items():
            if not key.isdigit():
                continue
            rendered = apply_homoglyphs(entry["ua"], table)
            checked += 1
            missing = [ch for ch in rendered if ord(ch) not in charset]
            if missing:
                problems.append(f"{json_file.name} {key}: missing glyphs {missing}")
            width = pixel_width(rendered, widths)
            if width > budget + WIDTH_SLACK:
                problems.append(f"{json_file.name} {key}: {width}px exceeds budget {budget}px")
    return checked, problems


def validate_plaza_map(charset: set[int], table: dict[str, str], widths: dict[int, int]) -> tuple[int, list[str]]:
    """Check the StreetPass Map's country and region names.

    Every row of these tables is drawn in the same slot on the map, so the budget is the
    widest official name in the whole table, not in the row - the way `budget_groups` treats
    labels that share a slot. Skipped when the Plaza is not dumped.
    """
    import csvtab

    strings = ROOT / "src" / "strings" / "plaza_map"
    param = ROOT / "work" / "0004001000022800" / "romfs" / "param"
    if not param.is_dir() or not strings.is_dir():
        return 0, []

    problems: list[str] = []
    checked = 0
    for rel, json_name in (("country.csv", "country.json"), ("region.csv", "region.json")):
        entries = json.loads((strings / json_name).read_text(encoding="utf-8"))
        rows = {csvtab.key_of(row): row.fields for row in csvtab.load(param / rel).data_rows()}
        budget = max(
            pixel_width(name, widths)
            for fields in rows.values()
            for name in fields[csvtab.ENGLISH :]
            if name
        )
        for key, entry in entries.items():
            if key not in rows:
                problems.append(f"{json_name}: row {key} is not in {rel}")
                continue
            rendered = apply_homoglyphs(entry["ua"], table)
            checked += 1
            missing = [ch for ch in rendered if ord(ch) not in charset]
            if missing:
                problems.append(f"{json_name} {key}: missing glyphs {missing}")
            width = pixel_width(rendered, widths)
            if width > budget:
                problems.append(
                    f"{json_name} {key}: {width}px exceeds budget {budget}px ({entry['ua']!r})"
                )

    panels_checked, panel_problems = validate_plaza_panels(charset, table, widths, param, strings)
    return checked + panels_checked, problems + panel_problems


def validate_plaza_panels(
    charset: set[int], table: dict[str, str], widths: dict[int, int], param: Path, strings: Path
) -> tuple[int, list[str]]:
    """Check the Puzzle Swap panel names.

    Unlike the map, each panel has a caption slot of its own, so the budget is the widest
    official name of *that* panel across its twelve language columns, not of the whole table
    - the same rule tools/manual.py measures against. An empty `ua` is a deliberate "leave
    the Latin game title alone" and is not measured.
    """
    import csvtab

    rel, json_name = "Piece2_PanelInfo.csv", "panels.json"
    path, names_path = param / rel, strings / json_name
    if not path.is_file() or not names_path.is_file():
        return 0, []

    entries = json.loads(names_path.read_text(encoding="utf-8"))
    parsed = csvtab.load_panels(path)

    problems: list[str] = []
    checked = 0
    for key, entry in entries.items():
        panel = parsed.panels.get(key)
        if panel is None:
            problems.append(f"{json_name}: panel {key} is not in {rel}")
            continue
        if not entry["ua"]:
            continue
        rendered = apply_homoglyphs(entry["ua"], table)
        checked += 1
        missing = [ch for ch in rendered if ord(ch) not in charset]
        if missing:
            problems.append(f"{json_name} {key}: missing glyphs {missing}")
        budget = max(
            pixel_width(parsed.name(panel, lang), widths) for lang in panel.columns if lang
        )
        width = pixel_width(rendered, widths)
        if width > budget:
            problems.append(
                f"{json_name} {key}: {width}px exceeds budget {budget}px ({entry['ua']!r})"
            )
    return checked, problems


def validate_layouts(
    charset: set[int], table: dict[str, str], widths: dict[int, int]
) -> tuple[int, list[str]]:
    """Check the lines that live in a layout's text panes rather than in an MSBT.

    The pane is one fixed box holding several languages at once, so the budget is the widest
    line the pane already carries in the languages the mod does not touch - they all have to
    fit the same box, which makes them the measurement Nintendo itself signed off on.

    Also checks that the original the spec names is still in the pane: a system update that
    reworded it has to fail here rather than silently translate nothing at build time.
    """
    import bclyt
    import darc
    import lz10
    import lz11

    layouts = ROOT / "src" / "layouts"
    if not layouts.is_dir():
        return 0, []

    problems: list[str] = []
    checked = 0
    for spec_file in sorted(layouts.glob("*.json")):
        name = spec_file.stem
        if name not in TITLES:
            # Only a title's own layout spec belongs here; anything else in src/layouts/ is
            # checked by its own function.
            continue
        romfs = ROOT / "work" / TITLES[name]["source_tid"] / "romfs"
        if not romfs.is_dir():
            continue
        spec = json.loads(spec_file.read_text(encoding="utf-8"))
        for rel, files in spec.items():
            packed = (romfs / rel).read_bytes()
            codec = lz11 if packed[0] == 0x11 else lz10
            archive = dict(darc.parse(codec.decompress(packed)).files())
            for inner, panes in files.items():
                by_name = {pane.name: pane for pane in bclyt.texts(archive[inner].data)}
                for pane_name, lines in panes.items():
                    pane = by_name[pane_name]
                    originals = pane.text.split("\n")
                    for entry in lines:
                        checked += 1
                        problems += _check_layout_line(
                            f"{name}/{pane_name}", entry, originals, charset, table, widths
                        )
    return checked, problems


def _check_layout_line(
    where: str,
    entry: dict,
    originals: list[str],
    charset: set[int],
    table: dict[str, str],
    widths: dict[int, int],
) -> list[str]:
    problems: list[str] = []
    slots = [key for key in ("ru", "en") if key in entry]
    for key in slots:
        if originals.count(entry[key]) != 1:
            problems.append(f"{where}: {entry[key]!r} is no longer a line of this pane")
    if problems or not entry["ua"]:
        return problems

    rendered = apply_homoglyphs(entry["ua"], table)
    missing = [ch for ch in rendered if ord(ch) not in charset]
    if missing:
        problems.append(f"{where}: missing glyphs {missing}")

    others = [line for line in originals if line not in {entry[key] for key in slots}]
    if others:
        budget = max(pixel_width(line, widths) for line in others)
        width = pixel_width(rendered, widths)
        if width > budget:
            problems.append(
                f"{where}: {width}px exceeds budget {budget}px ({entry['ua']!r})"
            )
    return problems


def validate_nnid(charset: set[int], table: dict[str, str], widths: dict[int, int]) -> tuple[int, list[str]]:
    """Check the account pages' string table.

    Two things this can prove and the layout checks elsewhere cannot: every glyph is one the
    console can draw, and the translation keeps the original's structure. The pages are HTML,
    so a lost `<br>` reflows a dialog and a lost `\n` runs two lines together - and unlike a
    text pane there is no pixel budget to measure against, because the browser wraps.

    Keys whose English is `null` are the US-only COPPA and credit-card screens; a European
    build has no text for them and none is expected.
    """
    strings = ROOT / "src" / "strings" / "nnid" / "message__EU.json"
    if not strings.is_file():
        return 0, []

    entries = json.loads(strings.read_text(encoding="utf-8"))
    problems: list[str] = []
    checked = 0
    for key, entry in entries.items():
        original, ua = entry["en"], entry["ua"]
        if not ua:
            if original:
                problems.append(f"nnid {key}: not translated")
            continue
        checked += 1
        rendered = apply_homoglyphs(ua, table)
        # `\n` is a line break the browser honours, not a glyph the font has to carry.
        missing = [ch for ch in rendered if ch != "\n" and ord(ch) not in charset]
        if missing:
            problems.append(f"nnid {key}: missing glyphs {missing}")
        for tag in set(re.findall(r"<[^>]+>", original)) - {"<br>"}:
            if tag not in ua:
                problems.append(f"nnid {key}: lost the {tag} tag")
        if ("\n" in original) and ("\n" not in ua) and len(ua) > 40:
            problems.append(f"nnid {key}: the original breaks lines and this does not")
    return checked, problems


def validate_nnid_pages(
    charset: set[int], table: dict[str, str], widths: dict[int, int]
) -> tuple[int, list[str]]:
    """Check the captions written into the account pages' markup.

    Same two guarantees as the string table above - drawable glyphs, structure kept - with
    one more that only applies here: the translation is spliced into HTML, so anything that
    opens a tag would change the page instead of appearing on it.

    Coverage is checked against the dump when there is one: a caption the extractor found in
    `index_<lang>.html` and the source file does not carry would ship in the slot language,
    silently, which is exactly the failure that made the first attempt look like a dead patch.
    """
    strings = ROOT / "src" / "strings" / "nnid" / "index__EU.json"
    if not strings.is_file():
        return 0, []

    entries = json.loads(strings.read_text(encoding="utf-8"))
    problems: list[str] = []
    for key, entry in entries.items():
        original, ua = entry["en"], entry["ua"]
        if not ua.strip():
            problems.append(f"nnid page {key}: not translated")
            continue
        rendered = apply_homoglyphs(ua, table)
        missing = [ch for ch in rendered if ch != "\n" and ord(ch) not in charset]
        if missing:
            problems.append(f"nnid page {key}: missing glyphs {missing}")
        for tag in set(re.findall(r"<[^>]+>", ua)) - {"<br>"}:
            problems.append(f"nnid page {key}: {tag} would be spliced into the markup")
        if len(re.findall(r"<br>", original)) and not re.search(r"<br>", ua) and len(ua) > 40:
            problems.append(f"nnid page {key}: the original breaks lines and this does not")

    pages = ROOT / "work" / "0004001B00018002" / "romfs" / "index_EU_Russian.html"
    if pages.is_file():
        import nnid_html

        for unit in nnid_html.units(pages.read_text(encoding="utf-8")):
            if re.search(r"[Ѐ-ӿ]", unit.text) and unit.key not in entries:
                problems.append(f"nnid page {unit.key}: in the dump, missing from index__EU.json")

    return len(entries), problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("titles", nargs="*", default=None)
    args = ap.parse_args()

    charset = load_charset()
    table = load_homoglyphs()
    widths = load_widths()
    failed = False

    for name in args.titles or list(TITLES):
        total, translated, problems = validate(name, charset, table, widths)
        gap = "" if translated == total else f" ({total - translated} left)"
        print(f"{name}: {translated}/{total} translatable strings done{gap}, problems: {len(problems)}")
        for problem in problems:
            print(f"  ✗ {problem}")
        failed = failed or bool(problems)

    if not args.titles:
        for label, noun, check in (
            ("area", "country and region names", validate_area),
            ("plaza map", "country and region names", validate_plaza_map),
            ("layouts", "lines baked into layout panes", validate_layouts),
        ):
            checked, problems = check(charset, table, widths)
            if not checked:
                continue
            print(f"{label}: {checked} {noun}, problems: {len(problems)}")
            for problem in problems:
                print(f"  ✗ {problem}")
            failed = failed or bool(problems)

        for noun, check in (
            ("account-page strings", validate_nnid),
            ("account-page captions", validate_nnid_pages),
        ):
            checked, problems = check(charset, table, widths)
            if not checked:
                continue
            print(f"nnid pages: {checked} {noun}, problems: {len(problems)}")
            for problem in problems:
                print(f"  ✗ {problem}")
            failed = failed or bool(problems)

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
