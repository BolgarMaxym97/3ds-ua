"""Generate the UniStore that installs, updates and removes the mod from the console itself.

Usage:
    python3 tools/unistore.py            # version read from Makefile
    python3 tools/unistore.py 1.8.0
    python3 tools/unistore.py --check

Output: unistore/3ds-ua.unistore, a Universal-Updater store served straight out of `main`.
The user adds STORE_URL once in Universal-Updater and from then on installs, updates and
removes the translation without ever taking the SD card out of the console.

The store is one entry with three scripts, and every number in it is derived - the folder
list from build.TITLES, the asset names from package.archive_name(), the jump offsets from
the step lists themselves. Nothing here is a copy of anything.

Four things about Universal-Updater shape this file, all read out of its source rather than
its wiki:

`runFunctions` loops `for(i...; ret == NONE; i++)`, so the first step that fails kills the
rest of the script. `deleteFile` on a missing file returns DELETE_ERROR, which counts as a
failure - so a generated "delete every file we ship" list is impossible, because the Old 3DS
card legitimately lacks the New 3DS files. `rmdir` is the opposite: harmless when the folder
is absent, but it asks the user to confirm every folder that *is* there. That is why the
32-folder wipe lives in its own scripts instead of running before every routine update.

`promptMessage` is a real branch: answering no jumps `count` steps ahead, and `name` makes
Universal-Updater remember the answer under "<info.title>/<name>". That remembering is the
closest thing to detecting the console model, which no store script can do - hence the two
questions, and hence info.title being frozen forever.

`extractFile` matches each archive member with regex_search and writes it to
`output + match.suffix()` - the matched part is the prefix it strips. So "^luma/" with
"/luma/" reproduces the card layout and leaves README.txt in the archive, while the obvious
looking "^luma/.*" would consume the whole name and pile every file onto one path.

The green update arrow comes from Meta::UpdateAvailable, which compares info.last_updated as
a string against what it recorded when the user last ran a script. info.version has nothing
to do with it. A malformed date means nobody is ever told about a new release, which is why
--check asserts the format.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import package  # noqa: E402
import variant  # noqa: E402
from build import TITLES  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STORE_DIR = ROOT / "unistore"
STORE_FILE = STORE_DIR / "3ds-ua.unistore"
SHEET_FILE = STORE_DIR / "3ds-ua.t3x"

REPO = "BolgarMaxym97/3ds-ua"
RAW = f"https://raw.githubusercontent.com/{REPO}/main/unistore"
# The one spelling of the store URL, so README.txt inside the archive and the store itself
# cannot disagree about where users are told to point Universal-Updater.
STORE_URL = package.STORE_URL
SHEET_URL = f"{RAW}/3ds-ua.t3x"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"


def store_url(branch: str) -> str:
    """Where Universal-Updater refetches the store from.

    A store served off a test branch has to *say* it lives on that branch, or the console
    reloads it from main on the next launch and loses whatever was being tested.
    """
    if branch == "main":
        return STORE_URL
    return STORE_URL.replace("/main/", f"/{branch}/", 1)


def sheet_url(branch: str) -> str:
    if branch == "main":
        return SHEET_URL
    return SHEET_URL.replace("/main/", f"/{branch}/", 1)

# Universal-Updater saves a prompt answer under "<ENTRY_TITLE>/<name>", so renaming the entry
# silently forgets which console model and language slot every existing user already told it.
# Treat it as frozen from here on - it was last changed while nobody had answers worth keeping.
ENTRY_TITLE = "Українізатор 3DS/2DS"

# Where the archive is downloaded before it is unpacked. /3ds/ exists on every CFW card, so
# downloadRelease never has to create the parent, and the file is deleted one step later.
TEMP_ZIP = "/3ds/3ds-ua.zip"

# Universal-Updater renders release notes as plain text in a small box; past this much it is
# a scrolling wall nobody reads.
NOTES_LIMIT = 1200

TIMESTAMP = "%Y-%m-%d at %H:%M (UTC)"
TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2} at \d{2}:\d{2} \(UTC\)$")

MODELS = ("new3ds", "old3ds")
SLOTS = ("ru", "en")

MODEL_WORDS = {"new3ds": "New 3DS / New 2DS XL", "old3ds": "3DS / 2DS"}
SLOT_WORDS = {"ru": "замість російської", "en": "замість англійської"}

INSTALL = "1. Встановити / оновити"
UNINSTALL = "2. Видалити українізатор"
FORCE_UNINSTALL = "3. Видалити примусово (питає про кожну папку)"

ASK_MODEL = ("У вас New 3DS, New 3DS XL або New 2DS XL?\n\n"
             "Модель написана спереду під нижнім екраном:\n"
             "якщо там немає слова New - відповідайте Ні.")
ASK_SLOT = ("Замінити РОСІЙСЬКУ мову?\n\n"
            "Ні = замінити англійську.")

DONE_NOTE = ("Готово.\n\n"
             "1. Вимкніть консоль, увімкніть із затиснутим SELECT,\n"
             "   увімкніть Enable game patching, натисніть START.\n"
             "2. Налаштування системи -> Інші налаштування ->\n"
             "   Мова -> Українська.")
REMOVED_NOTE = ("Файли видалено.\n\n"
                "Перемкніть мову консолі в Налаштуваннях системи.")

# Shown inline, right before the script is handed to the queue - which is the only moment
# the user is looking at the screen that can explain the queue to them.
PREINSTALL = (
    "УВАГА: Universal-Updater виконує все у ЧЕРЗІ.\n"
    "Після запуску відкрийте її третьою іконкою\n"
    "в лівій панелі - там будуть питання.\n"
    "Без відповіді на них робота стоїть.\n\n"
    "Потрібна Luma3DS з увімкненим Enable game patching,\n"
    "а мову консолі після встановлення треба\n"
    "перемкнути вручну."
)

DESCRIPTION = (
    "Українська мова для системного інтерфейсу Nintendo 3DS/2DS - 3DS, 3DS XL, 2DS, "
    "New 3DS, New 3DS XL, New 2DS XL. Стає на місце російського або англійського мовного "
    "слота; яка у вас модель і який слот замінити - питає під час установки."
)


def makefile_version() -> str:
    """The one place the version lives (Makefile:6), so a bare run is still correct."""
    m = re.search(r"^VERSION\s*:=\s*(\S+)", (ROOT / "Makefile").read_text(), re.M)
    if not m:
        raise SystemExit("no `VERSION :=` line in Makefile")
    return m.group(1)


def revision_of(version: str) -> int:
    """A store revision that rises on its own with every release.

    Universal-Updater refetches the store only when this number grows, so it must never be
    forgotten - deriving it from the version removes the chance to forget.
    """
    parts = (version.split(".") + ["0", "0"])[:3]
    try:
        major, minor, patch = (int(p) for p in parts)
    except ValueError:
        raise SystemExit(f"cannot derive a store revision from version {version!r}")
    return major * 10000 + minor * 100 + patch


def title_folders() -> tuple[set[str], set[str]]:
    """(Old 3DS card layout, New 3DS card layout) as sets of TIDs.

    Mirrors what package.collect() puts in each archive: a title with `ships_to` is rebuilt
    into its readers' folders and has none of its own, and a title with `loader_tid` lands in
    the New 3DS overlay under both its own id and the Old 3DS id Luma looks it up by - see
    write_loader_alias() in tools/build.py.
    """
    shared: set[str] = set()
    overlay: set[str] = set()
    for cfg in TITLES.values():
        if cfg.get("ships_to"):
            continue
        loader = cfg.get("loader_tid")
        if loader:
            overlay.update(cfg["tids"])
            overlay.add(loader)
        else:
            shared.update(cfg["tids"])
    return shared, shared | overlay


def removable_dirs() -> list[str]:
    """Every /luma/titles/<TID> this project can have written, on either console.

    One list serves both models because the New 3DS set is a superset. The nine titles that
    tools/package.py:216 says must be deleted whole need no special case: rmdir is recursive,
    so every folder goes whole regardless.
    """
    return [f"/luma/titles/{tid}" for tid in sorted(title_folders()[1])]


def asset_pattern(slot: str, model: str) -> str:
    """The regex Universal-Updater matches against the release's asset names.

    downloadRelease matches with std::regex_match, so this can leave the version open and
    the store then needs no edit between releases. Built from package.archive_name() so it
    cannot drift from the file `make package` actually writes.
    """
    sentinel = "@@VERSION@@"
    pattern = re.escape(package.archive_name(slot, sentinel, model))
    # re.escape also escapes the hyphens. `\-` is a legal identity escape in the ECMAScript
    # grammar std::regex uses, but there is no reason to lean on that from here.
    return pattern.replace("\\-", "-").replace(re.escape(sentinel), ".*")


class Label(str):
    """A jump target. Occupies no step; resolve() turns it into a count."""


def prompt(message: str, goto: str | None = None, name: str | None = None) -> dict:
    step: dict = {"type": "promptMessage", "message": message}
    if name:
        step["name"] = name
    if goto:
        step["_goto"] = goto
    return step


def skip(goto: str) -> dict:
    return {"type": "skip", "_goto": goto}


def resolve(items: list) -> list[dict]:
    """Turn symbolic jumps into counts, so no offset in this file is ever written by hand.

    Universal-Updater runs `i += count` and then the loop's own `i++`, for both step types,
    so one rule covers both: the next step executed is `i + count + 1`.
    """
    steps = [item for item in items if not isinstance(item, Label)]
    at: dict[str, int] = {}
    seen = 0
    for item in items:
        if isinstance(item, Label):
            at[str(item)] = seen
        else:
            seen += 1

    for i, step in enumerate(steps):
        goto = step.pop("_goto", None)
        if goto is None:
            continue
        if goto not in at:
            raise SystemExit(f"step {i} ({step['type']}) jumps to unknown label {goto!r}")
        count = at[goto] - (i + 1)
        if count < 1:
            # 0 would be a branch that does nothing and a negative one would loop forever.
            raise SystemExit(f"step {i} ({step['type']}) jumps to {goto!r} at offset {count}")
        step["count"] = count
    return steps


def download_steps(slot: str, model: str) -> list[dict]:
    """Download, unpack, tidy up. The one thing an install actually does."""
    return [
        {
            "type": "downloadRelease",
            "repo": REPO,
            "file": asset_pattern(slot, model),
            "output": TEMP_ZIP,
            "message": "Завантаження архіву (~23 МБ)...",
            "includePrereleases": False,
        },
        {
            # "^luma/" is the prefix to strip, and /luma/ puts it back: extractFile writes to
            # output + whatever follows the match. It also skips README.txt, which would
            # otherwise be dropped in the card root.
            "type": "extractFile",
            "file": TEMP_ZIP,
            "input": "^luma/",
            "output": "/luma/",
            "message": "Розпакування...",
        },
        {"type": "deleteFile", "file": TEMP_ZIP},
    ]


def script_names() -> dict[tuple[str, str], dict[str, str]]:
    """(model, slot) -> the two script names for that variant, in one place."""
    variants = [(m, sl) for m in MODELS for sl in SLOTS]
    names = {}
    for index, (model, slot) in enumerate(variants, start=1):
        label = f"{MODEL_WORDS[model]} · {SLOT_WORDS[slot]}"
        names[(model, slot)] = {
            "install": f"{index}. Встановити: {label}",
            "uninstall": f"{index + len(variants)}. Видалити: {label}",
        }
    return names


def branching(body) -> list:
    """The two questions, then one of four branches. `body(slot, model)` supplies each.

    Universal-Updater has no way to detect the console model or the system language, so the
    choice has to be asked. It also has no inline execution: running a script only queues it,
    and a queued promptMessage waits inside the Queue menu until the user goes there. That is
    survivable but only if they are told, which is what `preinstall_message` is for - it is
    shown inline at the one moment the user is still looking at the screen.
    """
    return [
        prompt(ASK_MODEL, goto="OLD3DS", name="new3ds"),
        prompt(ASK_SLOT, goto="EN_NEW", name="slot"),
        *body("ru", "new3ds"),
        skip("DONE"),
        Label("EN_NEW"),
        *body("en", "new3ds"),
        skip("DONE"),
        Label("OLD3DS"),
        prompt(ASK_SLOT, goto="EN_OLD", name="slot"),
        *body("ru", "old3ds"),
        skip("DONE"),
        Label("EN_OLD"),
        *body("en", "old3ds"),
        Label("DONE"),
    ]


def installed_files(slot: str, model: str) -> list[str]:
    """Every file the given archive puts on the card, hooks first.

    Order matters. `deleteFile` aborts the rest of the script when a file is already gone, so
    a partial run is a real possibility - a card carrying an older release, or a user who
    deleted something by hand. Removing every code.ips and exheader.bin first means a run
    that stops early leaves only inert data behind: nothing reads a romfs blob once the hook
    that redirected the title to it is gone. The reverse order could leave a title hooked to
    a file that no longer exists, which is how an applet stops booting.
    """
    dist = ROOT / ("dist" if slot == "ru" else "dist_en")
    if not dist.is_dir():
        raise SystemExit(f"no {dist.name}/ - run `make build` first, the delete lists come from it")

    files = set(package.collect(dist))
    if model == "new3ds":
        files |= set(package.collect(dist / variant.NEW3DS_DIR))

    hooks = sorted(f for f in files if f.endswith(("code.ips", "exheader.bin")))
    rest = sorted(files - set(hooks))
    return [f"/{path}" for path in hooks + rest]


def uninstall_steps(slot: str, model: str) -> list[dict]:
    return [{"type": "deleteFile", "file": path} for path in installed_files(slot, model)]


def wipe_steps() -> list[dict]:
    return [
        {"type": "rmdir", "directory": directory, "message": f"Видаляю {directory}"}
        for directory in removable_dirs()
    ]


def release_notes(version: str, path: Path | None) -> str:
    """The release notes, flattened - Universal-Updater renders plain text in a narrow box."""
    if path is None:
        path = ROOT / "tmp" / f"release-{version}.md"
    if not path.is_file():
        print(f"note: no {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}, releasenotes left empty")
        return ""

    # Only the "what changed" section: the rest of the file is the install guide, which the
    # store's own scripts replace, and Universal-Updater shows this in a narrow box.
    section: list[str] = []
    inside = False
    for line in path.read_text().splitlines():
        if line.startswith("## "):
            inside = line.startswith("## Що нового")
            continue
        if not inside or line.startswith(("|", "#")):
            continue
        line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
        line = line.replace("**", "").replace("`", "")
        section.append(line.rstrip())

    text = re.sub(r"\n{3,}", "\n\n", "\n".join(section)).strip()
    if not text:
        print(f"note: no '## Що нового' section in {path.name}, releasenotes left empty")
    if len(text) > NOTES_LIMIT:
        text = text[:NOTES_LIMIT].rsplit("\n", 1)[0].rstrip() + "\n\n(далі — у примітках релізу на GitHub)"
    return text


def build_store(version: str, revision: int, notes: str, branch: str) -> dict:
    info = {
        "title": ENTRY_TITLE,
        "author": "BolgarMaxym97",
        "description": DESCRIPTION,
        "version": version,
        "category": ["translation", "system"],
        "console": ["3DS"],
        "license": "MIT",
        "color": "#005BBB",
        "preinstall_message": PREINSTALL,
        "releasenotes": notes,
        # CheckInstalled() calls a path existing "installed". Both of these are ours and both
        # are in the shared tree, so they are there in all four archives. A slot-dependent
        # path such as 000400100002C100/romfs/index_EU_Russian.html only exists in from-ru
        # and would report "not installed" to half the users.
        "installed_files": [
            "/luma/titles/0004003000009802/banner_22800.bin",
            "/luma/titles/0004003000009B02/romfs/2000",
        ],
        # No title_ids: CheckInstalled() resolves those with AM_GetTitleProductCode, which
        # would find the system titles on every console and mark the entry installed for all.
    }

    entry = {
        INSTALL: {
            "size": "~23 МБ",
            "script": resolve(branching(download_steps) + [prompt(DONE_NOTE)]),
        },
        UNINSTALL: resolve(branching(uninstall_steps) + [prompt(REMOVED_NOTE)]),
        # The fallback. rmdir is the only removal Universal-Updater can do on a card whose
        # contents it cannot predict - it skips folders that are not there instead of giving
        # up - but it asks about every folder it does find, which is why it is not the
        # everyday path.
        FORCE_UNINSTALL: wipe_steps(),
        "info": info,
    }

    store_info = {
        "title": ENTRY_TITLE,
        "author": "BolgarMaxym97",
        "description": DESCRIPTION,
        "url": store_url(branch),
        "file": STORE_FILE.name,
        "version": 3,
        "revision": revision,
        "infoURL": f"https://github.com/{REPO}",
    }
    if SHEET_FILE.is_file():
        store_info["sheet"] = SHEET_FILE.name
        store_info["sheetURL"] = sheet_url(branch)
        info["icon_index"] = 0
        info["sheet_index"] = 0

    return {"storeInfo": store_info, "storeContent": [entry]}


def stamped(doc: dict, stamp: bool) -> dict:
    """Add last_updated, reusing the old one when nothing else changed.

    Without this every `make unistore` would dirty the working tree and tell every user there
    is an update when there is not.
    """
    now = datetime.now(timezone.utc).strftime(TIMESTAMP)
    previous = None
    if STORE_FILE.is_file():
        try:
            previous = json.loads(STORE_FILE.read_text())
        except json.JSONDecodeError:
            previous = None

    old_stamp = None
    if previous is not None:
        old_stamp = previous.get("storeContent", [{}])[0].get("info", {}).get("last_updated")
        candidate = json.loads(json.dumps(doc))
        candidate["storeContent"][0]["info"]["last_updated"] = old_stamp
        unchanged = bool(old_stamp) and candidate == previous
        if unchanged and not stamp:
            now = old_stamp
        elif old_stamp and now <= old_stamp:
            # Meta::UpdateAvailable wants a strictly greater string, and this format only has
            # minutes - two runs in the same minute would produce a store nobody is told
            # about. Step past the old stamp instead.
            bumped = datetime.strptime(old_stamp, TIMESTAMP).replace(tzinfo=timezone.utc)
            now = (bumped + timedelta(minutes=1)).strftime(TIMESTAMP)

    doc["storeContent"][0]["info"]["last_updated"] = now
    return doc


# --------------------------------------------------------------------------- checks


def simulate(steps: list[dict], answers: list[bool]) -> tuple[list[dict], list[str]]:
    """Universal-Updater's runFunctions, as far as control flow goes.

    Returns the steps that ran and the problems found on the way.
    """
    executed: list[dict] = []
    problems: list[str] = []
    pending = list(answers)
    i = 0
    while 0 <= i < len(steps):
        step = steps[i]
        kind = step["type"]
        if kind == "promptMessage":
            executed.append(step)
            answer = pending.pop(0) if pending else True
            if answer:
                i += 1
                continue
            if "count" not in step:
                return executed, problems     # no count means "no" cancels the script
            i += 1 + step["count"]
        elif kind == "skip":
            i += 1 + step["count"]
        else:
            executed.append(step)
            i += 1
        if i > len(steps):
            problems.append(f"jump out of range: landed on step {i} of {len(steps)}")
            return executed, problems
    return executed, problems


def check(version: str, branch: str, verify_release: bool) -> list[str]:
    problems: list[str] = []

    def bad(msg: str) -> None:
        problems.append(msg)

    if not STORE_FILE.is_file():
        return [f"no {STORE_FILE.relative_to(ROOT)} - run `make unistore` first"]
    doc = json.loads(STORE_FILE.read_text())

    store_info = doc.get("storeInfo", {})
    if store_info.get("version") != 3:
        bad(f"storeInfo.version is {store_info.get('version')!r}, must be 3")
    for key in ("title", "author", "url", "file", "revision"):
        if not store_info.get(key):
            bad(f"storeInfo.{key} is missing")
    if store_info.get("url") != store_url(branch):
        bad(f"storeInfo.url is {store_info.get('url')!r}, expected {store_url(branch)}")
    if not isinstance(store_info.get("revision"), int):
        bad("storeInfo.revision is not an int")
    elif not revision_of(version) <= store_info["revision"] < revision_of(version) + 100:
        # Equal to the version's own number normally; a little above it after a store-only
        # fix pushed with --revision. Anything else means the two have drifted apart.
        bad(f"storeInfo.revision {store_info['revision']} does not belong to version {version} "
            f"(expected {revision_of(version)}..{revision_of(version) + 99})")

    entries = doc.get("storeContent", [])
    if len(entries) != 1:
        return problems + [f"expected exactly 1 storeContent entry, found {len(entries)}"]
    entry = entries[0]
    info = entry.get("info", {})

    if info.get("title") != ENTRY_TITLE:
        bad(f"info.title is {info.get('title')!r} - it is frozen at {ENTRY_TITLE!r}")
    if "title_ids" in info:
        bad("info.title_ids present - it would mark the entry installed on every console")
    stamp = info.get("last_updated", "")
    if not TIMESTAMP_RE.match(stamp):
        bad(f"info.last_updated {stamp!r} is not '{TIMESTAMP}' - updates would never show")

    scripts = {name: value for name, value in entry.items() if name != "info"}
    expected_names = {INSTALL, UNINSTALL, FORCE_UNINSTALL}
    if set(scripts) != expected_names:
        missing = expected_names - set(scripts)
        extra = set(scripts) - expected_names
        bad(f"script names differ - missing {sorted(missing)}, unexpected {sorted(extra)}")

    known = {
        "promptMessage", "skip", "downloadRelease", "extractFile",
        "deleteFile", "rmdir", "mkdir", "move", "copy", "installCia", "downloadFile", "exit",
    }
    resolved = {}
    for name, value in scripts.items():
        steps = value["script"] if isinstance(value, dict) else value
        resolved[name] = steps
        for i, step in enumerate(steps):
            if step.get("type") not in known:
                bad(f"{name}[{i}]: unknown step type {step.get('type')!r}")
            if "_goto" in step or "_label" in step:
                bad(f"{name}[{i}]: unresolved jump marker leaked into the output")
            if "count" in step and (not isinstance(step["count"], int) or step["count"] < 1):
                bad(f"{name}[{i}]: count is {step['count']!r}")

    # Prompts wait inside the Queue menu, so the entry must be the thing that says so. If
    # this instruction is ever dropped while the scripts still ask questions, the console
    # looks like it did nothing at all - which is exactly how this went wrong once.
    if any(step["type"] == "promptMessage" and "count" in step
           for steps in resolved.values() for step in steps):
        # "черга" alternates to "черзі" in the locative, so match both stems.
        message = info.get("preinstall_message", "").lower()
        if not any(stem in message for stem in ("черг", "черз")):
            bad("the scripts ask questions but preinstall_message never mentions the queue")

    expected_dirs = set(removable_dirs())
    dirs = [s["directory"] for s in resolved.get(FORCE_UNINSTALL, []) if s["type"] == "rmdir"]
    if len(dirs) != len(set(dirs)):
        bad(f"{FORCE_UNINSTALL}: duplicate rmdir entries")
    if set(dirs) != expected_dirs:
        missing, extra = expected_dirs - set(dirs), set(dirs) - expected_dirs
        if missing:
            bad(f"{FORCE_UNINSTALL}: not removed: {sorted(missing)}")
        if extra:
            bad(f"{FORCE_UNINSTALL}: removes folders we never ship: {sorted(extra)}")

    whole_only = [
        "/luma/titles/0004001000022300",     # Health and Safety, reads a romfs blob off SD
        "/luma/titles/000400300000D002",     # swkbd
        "/luma/titles/000400300000C502",     # error applet
    ]
    for directory in whole_only:
        if directory not in expected_dirs:
            bad(f"{directory} must be in the wipe list - it is a whole-folder title")

    # Both branching scripts, walked the way the console walks them.
    for is_new3ds in (True, False):
        for is_ru in (True, False):
            answers = [is_new3ds, is_ru]
            model = "new3ds" if is_new3ds else "old3ds"
            slot = "ru" if is_ru else "en"

            executed, sim = simulate(resolved.get(INSTALL, []), answers)
            for problem in sim:
                bad(f"{INSTALL} {answers}: {problem}")
            kinds = [step["type"] for step in executed if step["type"] != "promptMessage"]
            if kinds != ["downloadRelease", "extractFile", "deleteFile"]:
                bad(f"{INSTALL} {answers}: ran {kinds}")
            else:
                download, extract, delete = [s for s in executed if s["type"] != "promptMessage"]
                want = asset_pattern(slot, model)
                if download["file"] != want:
                    bad(f"{INSTALL} {answers}: downloads {download['file']!r}, expected {want!r}")
                if len({download["output"], extract["file"], delete["file"]}) != 1:
                    bad(f"{INSTALL} {answers}: the three steps disagree about the temp file")
            if executed[-1].get("message") != DONE_NOTE:
                bad(f"{INSTALL} {answers}: did not end on the closing note")

            executed, sim = simulate(resolved.get(UNINSTALL, []), answers)
            for problem in sim:
                bad(f"{UNINSTALL} {answers}: {problem}")
            removals = [step for step in executed if step["type"] == "deleteFile"]
            listed = [step["file"] for step in removals]
            expected = installed_files(slot, model)
            if listed != expected:
                only_listed = set(listed) - set(expected)
                only_shipped = set(expected) - set(listed)
                if only_listed or only_shipped:
                    bad(f"{UNINSTALL} {answers}: deletes {len(only_listed)} file(s) we never "
                        f"ship and misses {len(only_shipped)}")
                else:
                    bad(f"{UNINSTALL} {answers}: right files, wrong order")
            hooks = [f for f in listed if f.endswith(("code.ips", "exheader.bin"))]
            if listed[:len(hooks)] != hooks:
                bad(f"{UNINSTALL} {answers}: hooks are not deleted first - a run that stops "
                    f"early could leave a title hooked to a file that is gone")
            if executed[-1].get("message") != REMOVED_NOTE:
                bad(f"{UNINSTALL} {answers}: did not end on the closing note")

    problems += check_sheet(store_info, info)
    problems += check_against_committed(doc)

    problems += check_archives(version, resolved.get(INSTALL, []))
    if verify_release:
        problems += check_release(install)
    return problems


def check_sheet(store_info: dict, info: dict) -> list[str]:
    """The icon sheet, if there is one.

    Store::GetIconValid() accepts a subtexture only up to 48x48 and silently swaps anything
    bigger for Universal-Updater's own "no icon" sprite, so an oversized icon looks like a
    store that simply has no icon. Read the size out of the .t3x header rather than trusting
    whatever went into tex3ds.
    """
    declared = "sheet" in store_info
    if not declared:
        if SHEET_FILE.is_file():
            return [f"{SHEET_FILE.name} exists but the store declares no sheet - regenerate it"]
        return []

    if not SHEET_FILE.is_file():
        return [f"the store declares sheet {store_info['sheet']!r} but {SHEET_FILE.name} is missing"]
    data = SHEET_FILE.read_bytes()
    if len(data) < 25 or data[:4] == b"\x89PNG":
        return [f"{SHEET_FILE.name} is not a .t3x - build it with `make unistore-icon`"]

    problems = []
    count = int.from_bytes(data[0:2], "little")
    index = info.get("icon_index", 0)
    if not 0 <= index < count:
        problems.append(f"info.icon_index is {index} but the sheet holds {count} subtexture(s)")
    else:
        width = int.from_bytes(data[5 + index * 20:7 + index * 20], "little")
        height = int.from_bytes(data[7 + index * 20:9 + index * 20], "little")
        if not (0 < width <= 48 and 0 < height <= 48):
            problems.append(
                f"the icon is {width}x{height}; Universal-Updater accepts up to 48x48 and "
                f"quietly shows its own placeholder instead"
            )
        else:
            print(f"icon: {width}x{height} from {SHEET_FILE.name}")
    return problems


def check_against_committed(doc: dict) -> list[str]:
    """Compare the store to the one already in git, the way a user's console will.

    Two silent failures live here. A store whose contents changed but whose revision did not
    is never refetched, so nobody ever sees the change. And a store refetched with an equal
    or older last_updated draws no update arrow, so nobody is told to run the script. Both
    look completely fine locally.
    """
    committed = subprocess.run(
        ["git", "show", f"HEAD:{STORE_FILE.relative_to(ROOT)}"],
        capture_output=True, text=True, cwd=ROOT,
    )
    if committed.returncode != 0:
        return []          # not committed yet - nothing to compare against

    try:
        previous = json.loads(committed.stdout)
    except json.JSONDecodeError:
        return ["the committed store is not valid JSON"]

    def stamp_of(store: dict) -> str:
        return store["storeContent"][0]["info"].get("last_updated", "")

    old_stamp, new_stamp = stamp_of(previous), stamp_of(doc)
    old_rev = previous.get("storeInfo", {}).get("revision")
    new_rev = doc.get("storeInfo", {}).get("revision")

    stripped_old = json.loads(json.dumps(previous))
    stripped_new = json.loads(json.dumps(doc))
    for store in (stripped_old, stripped_new):
        store["storeContent"][0]["info"]["last_updated"] = ""
        store["storeInfo"]["revision"] = 0

    if stripped_old == stripped_new:
        return []          # nothing changed, so no bump is expected either

    problems = []
    if not isinstance(new_rev, int) or not isinstance(old_rev, int) or new_rev <= old_rev:
        problems.append(
            f"the store changed but revision is still {new_rev} (committed: {old_rev}) - "
            f"Universal-Updater would never refetch it. Bump the version or pass --revision."
        )
    if new_stamp <= old_stamp:
        problems.append(
            f"the store changed but last_updated {new_stamp!r} is not newer than the "
            f"committed {old_stamp!r} - no update arrow would ever appear. Pass --stamp."
        )
    return problems


def check_archives(version: str, install: list[dict]) -> list[str]:
    """The store's regexes against the archives `make package` actually wrote."""
    problems: list[str] = []
    patterns = {s["file"] for s in install if s["type"] == "downloadRelease"}
    expected_old, expected_new = title_folders()

    # Take the extract rule from the store itself rather than restating it here - that is the
    # whole point of this check. "^luma/.*" would consume the entire member name and leave an
    # empty suffix, piling every file onto one path, and a test that hard-codes "^luma/"
    # would never notice.
    extracts = {(s["input"], s["output"]) for s in install if s["type"] == "extractFile"}
    if len(extracts) != 1:
        return [f"the install script has {len(extracts)} different extract rules: {sorted(extracts)}"]
    (rule, destination), = extracts
    try:
        member_re = re.compile(rule)
    except re.error as exc:
        return [f"extractFile input {rule!r} is not a valid regex: {exc}"]

    for slot in SLOTS:
        for model in MODELS:
            name = package.archive_name(slot, version, model)
            path = ROOT / name
            if not path.is_file():
                problems.append(f"{name} is not in the repo root - run `make package` first")
                continue

            want = asset_pattern(slot, model)
            matched = [p for p in patterns if re.fullmatch(p, name)]
            if matched != [want]:
                problems.append(f"{name} is matched by {matched}, expected only {want!r}")

            members = zipfile.ZipFile(path).namelist()
            tids = set()
            landings = set()
            for member in members:
                m = member_re.search(member)
                if not m:
                    if member != "README.txt":
                        problems.append(f"{name}: {member} is outside luma/ and would be skipped")
                    continue
                # Exactly what extractArchive() writes: output + whatever follows the match.
                landed = destination + member[m.end():]
                landings.add(landed)
                parts = landed.split("/")
                if len(parts) < 5 or parts[1] != "luma" or parts[2] != "titles":
                    problems.append(f"{name}: {member} would land on {landed!r}")
                    continue
                tids.add(parts[3])

            extracted = len([m for m in members if member_re.search(m)])
            if len(landings) != extracted:
                problems.append(
                    f"{name}: {extracted} members would be written to only {len(landings)} "
                    f"path(s) - the extract rule swallows part of the name it should keep"
                )

            expected = expected_new if model == "new3ds" else expected_old
            if tids != expected:
                problems.append(
                    f"{name}: ships {len(tids)} title folders, derivation says {len(expected)} "
                    f"(difference: {sorted(tids ^ expected)})"
                )
            if not tids <= set(t.rsplit('/', 1)[-1] for t in removable_dirs()):
                problems.append(f"{name}: ships folders the uninstall script does not remove")
    return problems


def check_release(install: list[dict]) -> list[str]:
    """Resolve the store's patterns against the real release, the way the console will.

    downloadRelease asks api.github.com for releases/latest and takes the first asset whose
    name the pattern matches. This asks the same endpoint, so it catches the one failure the
    local checks cannot see: a store pushed before its archives were uploaded.
    """
    problems: list[str] = []
    try:
        with urllib.request.urlopen(API_LATEST, timeout=20) as response:
            release = json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"note: could not reach {API_LATEST} ({exc}) - release check skipped")
        return problems

    if "assets" not in release:
        return [f"{API_LATEST}: {release.get('message', 'no assets in the response')}"]
    if release.get("draft") or release.get("prerelease"):
        problems.append(
            f"release {release.get('tag_name')} is a draft/prerelease - the store does not set "
            f"includePrereleases, so the console will not see it"
        )

    names = [asset["name"] for asset in release["assets"]]
    print(f"release {release.get('tag_name')}: {len(names)} assets")
    for step in install:
        if step["type"] != "downloadRelease":
            continue
        matched = [name for name in names if re.fullmatch(step["file"], name)]
        if len(matched) != 1:
            problems.append(
                f"pattern {step['file']!r} matches {matched or 'nothing'} in "
                f"{release.get('tag_name')} - the console would fail here"
            )
        else:
            print(f"  {step['file']} -> {matched[0]}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("version", nargs="?")
    ap.add_argument("--check", action="store_true", help="validate the written store")
    ap.add_argument("--stamp", action="store_true", help="refresh last_updated even if nothing changed")
    ap.add_argument("--revision", type=int, help="override the derived store revision")
    ap.add_argument("--notes", type=Path, help="release notes to embed")
    ap.add_argument("--no-notes", action="store_true")
    ap.add_argument("--branch", default="main",
                    help="serve the store off this branch instead of main (for testing)")
    ap.add_argument("--verify-release", action="store_true",
                    help="also resolve the download patterns against the published release")
    args = ap.parse_args()

    version = args.version or makefile_version()

    if args.check:
        problems = check(version, args.branch, args.verify_release)
        for problem in problems:
            print(f"  ✗ {problem}")
        if problems:
            print(f"{len(problems)} problem(s)")
            return 1
        print(f"{STORE_FILE.relative_to(ROOT)}: ok")
        return 0

    notes = "" if args.no_notes else release_notes(version, args.notes)
    revision = args.revision if args.revision is not None else revision_of(version)
    doc = stamped(build_store(version, revision, notes, args.branch), args.stamp)

    STORE_DIR.mkdir(exist_ok=True)
    STORE_FILE.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")

    entry = doc["storeContent"][0]
    print(f"{STORE_FILE.relative_to(ROOT)}: version {version}, revision {revision}, "
          f"updated {entry['info']['last_updated']}")
    if args.branch != "main":
        print(f"  served off branch {args.branch}: {store_url(args.branch)}")
    for name, value in entry.items():
        if name == "info":
            continue
        steps = value["script"] if isinstance(value, dict) else value
        print(f"  {name}: {len(steps)} steps")
    print(f"  {len(removable_dirs())} title folders in the wipe block")
    for slot in SLOTS:
        for model in MODELS:
            print(f"  asset {slot}/{model}: {asset_pattern(slot, model)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
