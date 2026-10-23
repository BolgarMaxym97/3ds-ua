"""Generate the UniStore and the Universal-DB entry that hand out the installer app.

Usage:
    python3 tools/unistore.py            # version read from Makefile
    python3 tools/unistore.py 2.0.0
    python3 tools/unistore.py --udb      # unistore/universal-db.json for Universal-Team/db
    python3 tools/unistore.py --check

From 2.0.0 the mod is installed by its own app, "Українізатор 3DS" (installer/): a CIA that
carries every build and picks the files, the Luma settings and the font on the console. Both
stores therefore do one thing - put that CIA on the console - and everything the 1.x scripts
did (two questions, four download branches, a 32-folder rmdir wipe) moved into the app.

unistore/3ds-ua.unistore is the project's own store, served straight out of `main`. Users who
added it in the 1.x days keep it, so it stays alive: one entry, one script, the same three
steps Universal-DB generates for a CIA asset. Its download pattern leaves the version open,
so the store needs no edit between releases - only a fresh `last_updated` to draw the arrow.

unistore/universal-db.json is the submission for Universal-Team/db (source/apps/3ds-ua.json).
It carries no scripts: without a `scripts` key Universal-DB generates one per release asset,
and `download_filter` keeps that to the CIA - the four zips stay in the release for manual
installs (Universal-DB skips archives anyway unless the entry maps them with `archive`, see
generate.py). `unique_ids` is the app's own, from installer/cia.rsf.

Two things about Universal-Updater shape this file, both read out of its source:

`downloadRelease` matches the asset name with std::regex_match against the latest release,
so the pattern must cover the whole name and must not catch the zips.

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
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import package  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STORE_DIR = ROOT / "unistore"
STORE_FILE = STORE_DIR / "3ds-ua.unistore"
SHEET_FILE = STORE_DIR / "3ds-ua.t3x"
UDB_FILE = STORE_DIR / "universal-db.json"
RSF_FILE = ROOT / "installer" / "cia.rsf"

REPO = "BolgarMaxym97/3ds-ua"
# The person. REPO above keeps the account name because it is part of a URL; this one is
# shown to the user, and it lives in a single place so the store and the entry cannot drift.
AUTHOR = "Max Bolhar"
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


# Universal-Updater draws store text with whatever font the console has, and the uppercase
# Ukrainian letters І Ї Є Ґ are not in it - they reach the screen as "?", which is how
# "ЧЕРЗІ" arrived as "ЧЕРЗ?" and "РОСІЙСЬКУ" as "РОС?ЙСЬКУ". The lowercase ones do render
# for anyone running Universal-Updater in Ukrainian, so the fix is not the mod's homoglyph
# substitution (which would turn every і into a Latin i) but simply never writing those four
# capitals - no ALL-CAPS word that contains one. check() enforces it.
# Paths Universal-Updater checks to decide whether the entry is installed: the mod's own
# files, in the shared tree of every build, so a card set up by the app, by the 1.x scripts
# or by hand all count.
INSTALLED_FILES = [
    "/luma/titles/0004003000009802/banner_22800.bin",
    "/luma/titles/0004003000009B02/romfs/2000",
]

FORBIDDEN_GLYPHS = "ІЇЄҐ"

# The mod itself already rewrites these four when it builds the console's own menus, so the
# substitution below is not a workaround - it is what the user will literally see on screen,
# down to the Latin I in "Iнші налаштування".
CAPS_FIX = {k: v for k, v in
            json.loads((ROOT / "src" / "homoglyphs.json").read_text(encoding="utf-8"))
            ["variants"]["greek"].items() if k in FORBIDDEN_GLYPHS}


def drawable(text: str) -> str:
    """Store text with the four undrawable capitals swapped for the mod's own stand-ins."""
    return text.translate(str.maketrans(CAPS_FIX))


# Universal-Updater saves prompt answers under "<ENTRY_TITLE>/<name>", and Universal-DB keys
# the entry by it. Treat it as frozen.
ENTRY_TITLE = "Українізатор 3DS/2DS"

# Where the CIA is downloaded before it is installed and deleted again. /3ds/ exists on every
# CFW card, so downloadRelease never has to create the parent.
TEMP_CIA = "/3ds/3ds-ua-installer.cia"

# Universal-Updater renders release notes as plain text in a small box; past this much it is
# a scrolling wall nobody reads.
NOTES_LIMIT = 1200

TIMESTAMP = "%Y-%m-%d at %H:%M (UTC)"
TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2} at \d{2}:\d{2} \(UTC\)$")

INSTALL = "Встановити застосунок"
INSTALL_STEPS = ["downloadRelease", "installCia", "deleteFile"]

# Shown inline, right before the script is handed to the queue - the one moment the user is
# still looking at the screen that can tell them what comes next.
PREINSTALL = (
    "Встановиться застосунок \"Українізатор 3DS\".\n\n"
    "Коли черга закінчить, відкрийте його в меню HOME\n"
    "і натисніть \"Встановити\". Застосунок сам вибере\n"
    "файли для вашої консолі, увімкне потрібне в Luma\n"
    "і перезавантажить консоль. Мову міняти не треба.\n\n"
    "Потрібна Luma3DS v10.3 або новіша і консоль\n"
    "європейського регіону (EUR). Видалити українізатор -\n"
    "кнопкою \"Видалити\" в тому ж застосунку."
)

DESCRIPTION = (
    "Українська мова для системного інтерфейсу Nintendo 3DS/2DS."
)

# Universal-Updater does not read this field - it appears nowhere in its source. It belongs
# to Universal-DB's submission format, from which their site is built. Kept here so the two
# texts live together and the submission is filled from one place.
LONG_DESCRIPTION = (
    "Перекладає системний інтерфейс Nintendo 3DS, 3DS XL, 2DS, New 3DS, New 3DS XL і "
    "New 2DS XL українською: Меню HOME, Налаштування системи, Інтернет-браузер, eShop, "
    "Камеру, Звук, Mii Maker, Журнал дій, електронні довідники та решту системних "
    "застосунків.\n\n"
    "Ставиться застосунком «Українізатор 3DS»: відкрийте його й натисніть «Встановити». "
    "Він сам вибере файли для вашої консолі, увімкне потрібне в Luma, додасть у системний "
    "шрифт справжні літери і, ї, є, ґ (шрифт читається з SD-карти, у NAND нічого не "
    "пишеться) і перезавантажить консоль. Українська стає на місце російської або "
    "англійської мови, мову консолі міняти не треба. Оновлення, зміна мови й видалення - "
    "у тому ж застосунку.\n\n"
    "Потрібна Luma3DS v10.3 або новіша (для справжніх літер - v13.0) і консоль "
    "європейського (EUR) регіону."
)

# Universal-DB's own vocabulary: game, emulator, app, utility, save-tool, firm, luma3ds.
# "do not just make up new categories" - so the store's own ["translation", "system"] cannot
# be reused here.
UDB_CATEGORIES = ["utility"]

# Their guidelines allow self-declaring LLM content as "minor" only for a repository with no
# commits attributed to an LLM account. This one has them, so the honest answer is "yes".
UDB_LLM = "yes"


def unique_id() -> int:
    """The app's Unique ID, read from the .rsf that makerom builds the CIA with."""
    m = re.search(r"^\s*UniqueId\s*:\s*(0x[0-9A-Fa-f]+)", RSF_FILE.read_text(), re.M)
    if not m:
        raise SystemExit(f"no `UniqueId :` line in {RSF_FILE.relative_to(ROOT)}")
    return int(m.group(1), 16)


def installer_pattern() -> str:
    """The regex for the installer's release asset, whatever the version.

    Built from package.installer_name() so it cannot drift from the file `make installer-cia`
    writes. Anchored, because Universal-DB applies `download_filter` with re.findall.
    """
    sentinel = "@@VERSION@@"
    pattern = re.escape(package.installer_name(sentinel))
    # re.escape also escapes the hyphens. `\-` is a legal identity escape in the ECMAScript
    # grammar std::regex uses, but there is no reason to lean on that from here.
    return "^" + pattern.replace("\\-", "-").replace(re.escape(sentinel), ".*") + "$"


def install_steps() -> list[dict]:
    """Download the CIA, install it, tidy up - what Universal-DB generates for a CIA asset."""
    return [
        {
            "type": "downloadRelease",
            "repo": REPO,
            # std::regex_match covers the whole name on its own; the anchors stay harmless.
            "file": installer_pattern(),
            "output": TEMP_CIA,
            "message": "Завантаження застосунку...",
            "includePrereleases": False,
        },
        {"type": "installCia", "file": TEMP_CIA, "message": "Встановлення застосунку..."},
        {"type": "deleteFile", "file": TEMP_CIA},
    ]


def build_udb(version: str) -> dict:
    """The submission file for Universal-Team/db (source/apps/<slug>.json).

    Universal-DB builds its own store out of this, so nothing here is read by
    Universal-Updater directly - which is also why long_description belongs in it.
    """
    return {
        "github": REPO,
        "title": ENTRY_TITLE,
        "author": AUTHOR,
        "systems": ["3DS"],
        "categories": UDB_CATEGORIES,
        "description": DESCRIPTION,
        "long_description": LONG_DESCRIPTION,
        "website": f"https://github.com/{REPO}",
        "icon": f"https://raw.githubusercontent.com/{REPO}/main/assets/unistore-icon.png",
        "llm_generation": UDB_LLM,
        "preinstall_message": drawable(PREINSTALL),
        "unique_ids": [unique_id()],
        "installed_files": INSTALLED_FILES,
        "download_filter": installer_pattern(),
    }


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


def release_notes(version: str, path: Path | None) -> str:
    """The release notes, flattened - Universal-Updater renders plain text in a narrow box."""
    if path is None:
        path = ROOT / "releases" / f"release-{version}.md"
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
        "title": drawable(ENTRY_TITLE),
        "author": AUTHOR,
        "description": drawable(DESCRIPTION),
        "version": version,
        "category": ["translation", "system"],
        "console": ["3DS"],
        "license": "MIT",
        "color": "#005BBB",
        # Not drawable(): this text is rendered by Universal-DB's website, not by the
        # console, so it keeps proper Ukrainian capitals.
        "long_description": LONG_DESCRIPTION,
        "preinstall_message": drawable(PREINSTALL),
        "releasenotes": notes,
        "installed_files": INSTALLED_FILES,
        # No title_ids: CheckInstalled() resolves those with AM_GetTitleProductCode, which
        # would find the system titles on every console and mark the entry installed for all.
    }

    entry = {
        INSTALL: {"size": cia_size(version), "script": install_steps()},
        "info": info,
    }

    store_info = {
        "title": drawable(ENTRY_TITLE),
        "author": AUTHOR,
        "description": drawable(DESCRIPTION),
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


def cia_size(version: str) -> str:
    """The size line Universal-Updater shows next to the script, off the built CIA."""
    path = ROOT / package.installer_name(version)
    if not path.is_file():
        raise SystemExit(f"no {path.name} - run `make installer-cia` first")
    return f"~{round(path.stat().st_size / 1024 / 1024)} МБ"


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

    if info.get("title") != drawable(ENTRY_TITLE):
        bad(f"info.title is {info.get('title')!r} - it is frozen at {ENTRY_TITLE!r}")
    if len(info.get("description", "")) > 120:
        bad(f"info.description is {len(info['description'])} chars - it is the one line "
            f"Universal-Updater shows in the list; the long text goes in long_description")
    if "title_ids" in info:
        bad("info.title_ids present - it would mark the entry installed on every console")
    stamp = info.get("last_updated", "")
    if not TIMESTAMP_RE.match(stamp):
        bad(f"info.last_updated {stamp!r} is not '{TIMESTAMP}' - updates would never show")

    scripts = {name: value for name, value in entry.items() if name != "info"}
    if set(scripts) != {INSTALL}:
        bad(f"scripts are {sorted(scripts)}, expected only {INSTALL!r} - removal is the app's job")
    install = scripts.get(INSTALL, {}).get("script", [])
    kinds = [step.get("type") for step in install]
    if kinds != INSTALL_STEPS:
        bad(f"{INSTALL}: runs {kinds}, expected {INSTALL_STEPS}")
    else:
        download, cia, delete = install
        if len({download["output"], cia["file"], delete["file"]}) != 1:
            bad(f"{INSTALL}: the three steps disagree about the temp file")
        if download["file"] != installer_pattern():
            bad(f"{INSTALL}: downloads {download['file']!r}, expected {installer_pattern()!r}")

    # Every string the console will draw, checked for the four capitals its font lacks.
    visible = {"info.title": info.get("title", ""),
               "info.description": info.get("description", ""),
               "info.preinstall_message": info.get("preinstall_message", ""),
               f"script name {INSTALL!r}": INSTALL}
    for i, step in enumerate(install):
        if "message" in step:
            visible[f"{INSTALL}[{i}].message"] = step["message"]
    # long_description is deliberately absent from `visible`: the console never draws it.
    for where, text in visible.items():
        found = sorted({c for c in text if c in FORBIDDEN_GLYPHS})
        if found:
            bad(f"{where}: {''.join(found)} - the console font has no such glyph and draws "
                f"'?' instead; reword rather than shouting")

    problems += check_udb(version)
    problems += check_sheet(store_info, info)
    problems += check_against_committed(doc)
    problems += check_assets(version)
    if verify_release:
        problems += check_release(install)
    return problems


def check_udb(version: str) -> list[str]:
    """The written submission file is what this script would write now."""
    if not UDB_FILE.is_file():
        return [f"no {UDB_FILE.relative_to(ROOT)} - run `make udb`"]
    written = json.loads(UDB_FILE.read_text())
    if written != build_udb(version):
        return [f"{UDB_FILE.relative_to(ROOT)} is stale - run `make udb`"]
    if "scripts" in written or "archive" in written:
        return [f"{UDB_FILE.name}: scripts/archive would replace the scripts Universal-DB "
                f"generates for the CIA"]
    return []


def check_assets(version: str) -> list[str]:
    """The download pattern against the five files a release carries.

    Exactly the CIA must match - in Universal-Updater's regex_match and in Universal-DB's
    re.findall over `download_filter` alike - and none of the four zips.
    """
    problems: list[str] = []
    cia = package.installer_name(version)
    zips = [package.archive_name(slot, version, model)
            for slot in ("ru", "en") for model in ("old3ds", "new3ds")]
    for name in [cia, *zips]:
        if not (ROOT / name).is_file():
            problems.append(f"{name} is not in the repo root - run `make release` first")
    pattern = installer_pattern()
    for name in [cia, *zips]:
        hit = bool(re.fullmatch(pattern, name)) and bool(re.findall(pattern, name))
        if hit != (name == cia):
            problems.append(f"{pattern!r} {'matches' if hit else 'misses'} {name}")
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
    ap.add_argument("--udb", action="store_true",
                    help="write the Universal-DB submission file instead")
    ap.add_argument("--verify-release", action="store_true",
                    help="also resolve the download pattern against the published release")
    args = ap.parse_args()

    version = args.version or makefile_version()

    if args.check:
        problems = check(version, args.branch, args.verify_release)
        for problem in problems:
            print(f"  ✗ {problem}")
        if problems:
            print(f"{len(problems)} problem(s)")
            return 1
        print(f"{STORE_FILE.relative_to(ROOT)}, {UDB_FILE.relative_to(ROOT)}: ok")
        return 0

    if args.udb:
        STORE_DIR.mkdir(exist_ok=True)
        UDB_FILE.write_text(json.dumps(build_udb(version), ensure_ascii=False, indent="\t") + "\n")
        print(f"{UDB_FILE.relative_to(ROOT)}: submission for Universal-Team/db, "
              f"unique id 0x{unique_id():X}, assets {installer_pattern()}")
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
    print(f"  {INSTALL}: {entry[INSTALL]['size']}, asset {installer_pattern()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
