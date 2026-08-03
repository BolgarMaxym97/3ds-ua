"""Build LayeredFS-ready files from the JSON translations.

Usage:
    python3 tools/build.py            # every title in TITLES
    python3 tools/build.py home_menu

How it works: the original MSBT from work/ is used as a template, texts are replaced
with the JSON ones (empty `ua` keeps the original), homoglyph substitution is applied,
the result is LZ11-packed into dist/luma/titles/<TID>/romfs/<same path>.

An optional `_all_langs.json` next to a title's strings holds labels that go into EVERY
language slot instead of only the replaced one - used so the language picker advertises
Ukrainian whatever language the console currently runs.

A title carrying a `blocked` reason is translated but never written to dist/ - see
skip_blocked() for why shipping it would brick the title.

A title carrying `hud_font` also gets a patched copy of the bitmap font that draws the
clock line on the top screen - see build_hud_font() and tools/bcfnt.py.

A title carrying `hook_patch` is one Luma cannot hook on its own: next to its romfs the
build also writes the code.ips and exheader.bin that make LayeredFS work at all. See
tools/luma_hook.py. Those two files are mandatory for such a title - romfs alone is the
exact situation `blocked` exists to prevent - so a missing dump aborts the build.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import area as area_mod  # noqa: E402
import banner as banner_mod  # noqa: E402
import csvtab  # noqa: E402
import bcfnt  # noqa: E402
import luma_hook  # noqa: E402
import msbt as msbt_mod  # noqa: E402
import romfs  # noqa: E402
import smdh as smdh_mod  # noqa: E402
import pane_names  # noqa: E402
import smdh_names  # noqa: E402
from store import open_store  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

# The country code the mod takes over: Russia's, because Nintendo's table has no Ukraine.
UKRAINE_CODE = 100

# Titles: strings project name -> target TIDs, language slot, dump used as source.
#
# `lang` is the language folder we replace: the Russian one, so Russian disappears from
# the console and Ukrainian takes its place while English stays untouched. Note the
# Instruction Manual spells it "EU_Russia" without the final "n".
#
# `ref_lang` is the folder extract.py reads the `en` reference from - the translation is
# written against English, not against the slot being overwritten.
TITLES = {
    "home_menu": {
        "tids": ["0004003000009802"],  # EUR; JPN 0004003000008202, USA 0004003000008F02 once tested
        "source_tid": "0004003000009802",
        "lang": "EU_Russian",
        "ref_lang": "EU_English",
        # `hook_patch` here ships only a code.ips, and not to make LayeredFS work - Luma
        # hooks this title unaided. It carries the application names, which HOME Menu reads
        # from NAND and LayeredFS therefore cannot reach. See tools/smdh_names.py.
        "hook_patch": True,
        "hud_font": "font/Hud_JP.bcfnt",
        # ON and OFF of the power-saving / wireless toggle are two states of one pane,
        # so the slot is as wide as the longer of the pair ("Desligado", not "Ligado").
        "budget_groups": [
            r"(?:ptt|lau)_light_(?:on|off)",
        ],
    },
    # Ships a whole RomFS image, like download_play - see the note there.
    "keyboard": {
        "tids": ["000400300000D002"],  # swkbd applet, EUR
        "source_tid": "000400300000D002",
        "lang": "EU_Russian",
        "ref_lang": "EU_English",
        "hook_patch": True,
    },
    # `hook_patch`: the title has no fsMountArchive of its own and no DirectSdmc right,
    # so LayeredFS only works once tools/luma_hook.py supplies both from the SD card.
    "activity_log": {
        "tids": ["0004001000022200"],
        "source_tid": "0004001000022200",
        "lang": "EU_Russian",
        "ref_lang": "EU_English",
        "hook_patch": True,
    },
    # This one ships a whole RomFS image instead of a romfs/ folder - the title cannot
    # mount an archive at all, so LayeredFS is out and tools/luma_hook.py points its own
    # RomFS opens at a file on the SD card instead. See ROMFS_FROM_SD there.
    "download_play": {
        "tids": ["0004001000022100"],
        "source_tid": "0004001000022100",
        "lang": "EU_Russian",
        "ref_lang": "EU_English",
        "hook_patch": True,
    },
    "manual": {
        "tids": ["0004003000009B02"],  # Instruction Manual applet, EUR
        "source_tid": "0004003000009B02",
        "lang": "EU_Russia",
        "ref_lang": "EU_English",
        "hook_patch": True,
    },
    # Same shape as the Activity Log: no fsMountArchive in .text and no DirectSdmc, so Luma
    # cannot hook it on its own - tools/luma_hook.py supplies both from the SD card.
    "friend_list": {
        "tids": ["0004003000009F02"],  # friend applet, EUR; JPN 0004003000008D02, USA 0004003000009602
        "source_tid": "0004003000009F02",
        "lang": "EU_Russian",
        "ref_lang": "EU_English",
        "hook_patch": True,
        "hud_font": "font/Hud_JP.bcfnt",
    },
    # `container`: the text lives inside an LZ11+darc archive instead of plain folders.
    # `{lang}` in the path means one archive per language.
    "system_settings": {
        "tids": ["0004001000022000"],
        "source_tid": "0004001000022000",
        "lang": "EU_Russian",
        "ref_lang": "EU_English",
        "container": "message_EU_LZ.bin",
        # Labels sharing one on-screen slot: the language picker rows and the
        # rating-name rows are as wide as their longest sibling, not their own original.
        "budget_groups": [
            r"(?:eu|us|tw)_\w+",
            r"par_(?:cob|oflc)_\d+",
        ],
        "hud_font": "font/Hud_JP.bcfnt",
        # `hook_patch` here ships only a code.ips, and not to make LayeredFS work - Luma
        # hooks this title unaided. It points the `area:` mount at the SD card so the
        # country and region lists of Profile settings can be replaced; those live in the
        # shared data archive 0004009B00010402, which LayeredFS cannot reach. See
        # build_area() and tools/area.py.
        "hook_patch": True,
        "area": "0004009B00010402",
    },
    "mii_maker": {
        "tids": ["0004001000022700"],
        "source_tid": "0004001000022700",
        "lang": "EU_Russian",
        "ref_lang": "EU_English",
        "container": "message/{lang}.arc",
        # This title keeps a full SMDH in its romfs, so LayeredFS can translate the name
        # the system shows for its data - see build_smdh() and tools/smdh.py.
        "smdh": ["icn/EU_appEdit.icn"],
    },
    # Same per-language shape as Mii Maker, but the archive is the header-less flat table
    # of tools/msgarc.py instead of a darc - store.py tells them apart by magic.
    "camera": {
        "tids": ["0004001000022400"],
        "source_tid": "0004001000022400",
        "lang": "EU_Russian",
        "ref_lang": "EU_English",
        "container": "msg/{lang}.LZ",
    },
    # The camera the HOME Menu opens on L+R - an applet of its own, separate from the
    # Camera application above, with the same flat msg/ table. Thumb-compiled, so Luma's
    # ARM signature search can never hook it: it ships a whole RomFS image read off the SD
    # card, like download_play and the error applet. See tools/luma_hook.py.
    "camera_applet": {
        "tids": ["0004003000009902"],  # camera applet, EUR
        "source_tid": "0004003000009902",
        "lang": "EU_Russian",
        "ref_lang": "EU_English",
        "container": "msg/{lang}.LZ",
        "hook_patch": True,
    },
    "sound": {
        "tids": ["0004001000022500"],
        "source_tid": "0004001000022500",
        "lang": "EU_Russian",
        "ref_lang": "EU_English",
        "container": "msg/{lang}.LZ",
    },
    # Plain layout like the HOME Menu: one uncompressed MEET.msbt per language folder.
    # `hook_patch` here ships only an exheader: Luma hooks the title unaided, but its
    # accessInfo has no DirectSdmc and Luma's payload still reads off the SD card.
    # `csv_tables`: the StreetPass Map names the places you met people in, and those names
    # live in UTF-16 CSV tables rather than MSBT - see build_csv().
    "mii_plaza": {
        "tids": ["0004001000022800"],
        "source_tid": "0004001000022800",
        "lang": "EU_Russian",
        "ref_lang": "EU_English",
        "hook_patch": True,
            "csv_tables": {
            "param/country.csv": "country.json",
            "param/region.csv": "region.json",
        },
},
    # Same per-language darc as Mii Maker, but the applet has no fsMountArchive of its
    # own, so it needs the tools/luma_hook.py treatment before it can ship.
    "mii_selector": {
        "tids": ["000400300000D102"],  # appletEd, EUR
        "source_tid": "000400300000D102",
        "lang": "EU_Russian",
        "ref_lang": "EU_English",
        "container": "message/{lang}.arc",
        "hook_patch": True,
    },
    # Notifications: message/ plus the same message_hud/ file the HOME Menu and the Friend
    # List carry - byte-identical, so the translation carries straight over.
    "notifications": {
        "tids": ["000400300000A002"],  # newslist applet, EUR
        "source_tid": "000400300000A002",
        "lang": "EU_Russian",
        "ref_lang": "EU_English",
        "hook_patch": True,
        "hud_font": "font/Hud_JP.bcfnt",
    },
    # `message_dirs`: this title keeps its MSBT under romfs/lang/<LANG>/, not message*/.
    "game_notes": {
        "tids": ["0004003000009C02"],  # Cherry applet, EUR
        "source_tid": "0004003000009C02",
        "lang": "EU_Russian",
        "ref_lang": "EU_English",
        "message_dirs": ["lang"],
        "hud_font": "lang/Hud.bcfnt",
    },
    # No archive object anywhere in this title, so a mount stub has nothing to jump into:
    # it ships a whole RomFS image read off the SD card, like download_play.
    "error_applet": {
        "tids": ["000400300000C502"],  # error applet, EUR
        "source_tid": "000400300000C502",
        "lang": "EU_Russian",
        "ref_lang": "EU_English",
        "hook_patch": True,
    },
    "browser": {
        "tids": ["0004003000009D02"],  # spider applet, EUR Old3DS; New3DS is 0004003020009D02
        "source_tid": "0004003000009D02",
        "lang": "EU_Russian",
        "ref_lang": "EU_English",
        "hud_font": "font/Hud.bcfnt",
    },
    "ar_games": {
        "tids": ["0004001000022E00"],
        "source_tid": "0004001000022E00",
        "lang": "EU_Russian",
        "ref_lang": "EU_English",
    },
    "nintendo_zone": {
        "tids": ["0004001000022B00"],
        "source_tid": "0004001000022B00",
        "lang": "EU_Russian",
        "ref_lang": "EU_English",
        "smdh": ["saveicon_EU.icn"],
    },
    # `message_dirs` with a nested path: the eShop puts a region folder between message/
    # and the language, and its MSBT are LZ11-packed (`.msbt.lz`).
    "eshop": {
        "tids": ["0004001000022900"],
        "source_tid": "0004001000022900",
        "lang": "EU_Russian",
        "ref_lang": "EU_English",
        "message_dirs": ["message/europe"],
        "hud_font": "font/Hud.bcfnt",
        # `hook_patch` ships an exheader.bin and nothing else: Luma hooks this title itself,
        # but its accessInfo has no `DirectSdmc`, so its LayeredFS payload could not read the
        # replacement files off the SD card at all.
        "hook_patch": True,
    },
    # The eShop applet (`mint`): the in-app purchase and update flow a title hands off to,
    # not the eShop application itself. StreetPass Mii Plaza's Update button is one caller -
    # `Boot_txt01_08` is the "Updating..." dialog it draws on the Touch Screen.
    #
    # `hook_patch`: the title has all four fs:USER commands but no `fsMountArchive`, so Luma
    # finds four of its five symbols and the loader would svcBreak() on every launch if a
    # romfs/ folder shipped alone. Same class as the Activity Log and the Friend List, i.e.
    # a mount stub, not a whole RomFS image from SD - see tools/luma_hook.py.
    "mint": {
        "tids": ["000400300000D602"],  # eShop applet (mint), EUR
        "source_tid": "000400300000D602",
        "lang": "EU_Russian",
        "ref_lang": "EU_English",
        "hook_patch": True,
    },
    # The system error-message database: a shared data archive, the same class of title as
    # the system font and the `area` region manifest, dumped from CTRNAND. Its 13 files are
    # named after the error module (`90000_msbt_LZ.bin` holds 009-xxxx) and every label is
    # the error number itself, so 009-1003 is label `91003` in `90000_msbt_LZ`.
    #
    # `message_dirs [""]`: the language folders sit at the root of this romfs.
    #
    # The error applet and Miiverse both mount it as `msg:` and pick the file by console
    # region - EUR is 0004009B00012102, and that is the one every EUR console carries. No
    # title mounts it any other way, so translating this one archive translates the body of
    # every error code the system can show.
    #
    # Luma's LayeredFS cannot deliver it - the archive is not a process, and the reads that
    # would have to be hooked carry a binary path, not one of the mount prefixes Luma looks
    # for. So `ships_to` writes the rebuilt archive into each reader's own folder instead,
    # where the code patch of tools/luma_hook.py (`msg_hook`) points the read.
    "error_strings": {
        "tids": ["0004009B00012102"],  # error-message database, EUR
        "source_tid": "0004009B00012102",
        "lang": "EU_Russian",
        "ref_lang": "EU_English",
        "message_dirs": [""],
        "ships_to": ["000400300000C502", "000400300000BE02"],
    },
    # Miiverse (`cave`): the applet behind the HOME Menu icon and behind the in-game Miiverse
    # button, and the same binary draws the Nintendo Network ID pages. Luma hooks it unaided -
    # all five FS symbols are there - so it ships a plain romfs/.
    #
    # The service is dead since 2017, so only its start-up and error path is reachable now:
    # `ErrorMsg_Title`, `Opening_*`, `StartUp_*` and the "Miiverse is closing" lines.
    "miiverse": {
        "tids": ["000400300000BE02"],  # Miiverse applet, EUR
        "source_tid": "000400300000BE02",
        "lang": "EU_Russian",
        "ref_lang": "EU_English",
        # `hook_patch` ships an exheader.bin and nothing else: Luma hooks the code itself,
        # but the title has no `DirectSdmc`, so its payload could not read the SD card.
        "hook_patch": True,
    },
    # Miiverse posting applet: the keyboard-and-canvas overlay a game opens to write a post.
    "miiverse_post": {
        "tids": ["000400300000BA02"],  # Miiverse posting applet, EUR
        "source_tid": "000400300000BA02",
        "lang": "EU_Russian",
        "ref_lang": "EU_English",
        "hook_patch": True,   # exheader.bin only, same reason as the Miiverse applet
    },
    # 3DS Memo: `message_dirs` because this title spells the folder `mes/`, and its MSBT are
    # not packed. Like download_play it ships a whole RomFS image read off the SD card - see
    # tools/luma_hook.py for why a mount stub is out.
    "memolib": {
        "tids": ["000400300000F602"],  # memolib applet, EUR
        "source_tid": "000400300000F602",
        "lang": "EU_Russian",
        "ref_lang": "EU_English",
        "message_dirs": ["mes"],
        "hook_patch": True,
    },
    # Circle Pad Pro applet: the calibration screens, reachable only with the accessory
    # attached. Ships a whole RomFS image too - untested on hardware, since testing it needs
    # the accessory.
    "extrapad": {
        "tids": ["000400300000CD02"],  # extrapad applet, EUR
        "source_tid": "000400300000CD02",
        "lang": "EU_Russian",
        "ref_lang": "EU_English",
        "hook_patch": True,
    },
    "data_transfer": {
        "tids": ["0004001000022A00"],
        "source_tid": "0004001000022A00",
        "lang": "EU_Russian",
        "ref_lang": "EU_English",
        "message_dirs": ["CARDBOARD/message", "CARDBOARD/message/HUD"],
        "hud_font": "font/Hud.bcfnt",
    },
    # `lang_files`: no language folders at all - the language is part of the file name.
    "face_raiders": {
        "tids": ["0004001000022D00"],
        "source_tid": "0004001000022D00",
        "lang": "EU_Russian",
        "ref_lang": "EU_English",
        "lang_files": "hal/msg/StgFace/StgFace{lang}.msbt",
    },
    "amiibo_settings": {
        "tids": ["000400300000B902"],  # Cabinet applet, EUR
        "source_tid": "000400300000B902",
        "lang": "EU_Russian",
        "ref_lang": "EU_English",
        "hook_patch": True,
    },
    # No fsMountArchive and no FSUSER_OpenArchive at all, so LayeredFS is out: this title
    # ships a whole RomFS image read off the SD card, like download_play and keyboard.
    "health_safety": {
        "tids": ["0004001000022300"],
        "source_tid": "0004001000022300",
        "lang": "EU_Russian",
        "ref_lang": "EU_English",
        "hook_patch": True,
    },
}


def load_homoglyphs() -> dict[str, str]:
    data = json.loads((ROOT / "src" / "homoglyphs.json").read_text(encoding="utf-8"))
    table = dict(data["variants"][data["default"]])
    table.pop("_comment", None)
    for key, value in data.get("also_missing", {}).items():
        if key != "_comment":
            table[key] = value
    return table


def apply_homoglyphs(text: str, table: dict[str, str]) -> str:
    return text.translate(str.maketrans(table))


def load_all_langs(strings_dir: Path) -> dict[str, dict[str, str]]:
    """Labels that must appear in every language slot: {json key: {label: text}}."""
    path = strings_dir / "_all_langs.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {key: value for key, value in data.items() if not key.startswith("_")}


def patch_other_langs(
    store, cfg: dict, overrides: dict[str, dict[str, str]], table: dict[str, str]
) -> list[str]:
    """Apply cross-language overrides to every slot except the one build_title handles.

    ContainerStore keeps a single parsed archive, so repeated outputs() calls accumulate
    into the same file - that is what makes one shared container hold all eight patched
    slots. The last returned blob therefore carries every language's change.
    """
    stats: list[str] = []
    blobs: dict[str, bytes] = {}

    for lang in store.languages():
        if lang == cfg["lang"]:
            continue
        updates: dict[str, bytes] = {}
        for key, data in store.read(lang).items():
            labels = overrides.get(key)
            if not labels:
                continue
            msbt = msbt_mod.parse(data)
            patched = 0
            for label, text in labels.items():
                if label in msbt.labels:
                    msbt.texts[msbt.labels[label]] = apply_homoglyphs(text, table)
                    patched += 1
            if patched:
                updates[key] = msbt_mod.build(msbt)
                stats.append(f"{key} [{lang}]: {patched} cross-language labels")
        if updates:
            blobs |= store.outputs(lang, updates)

    return stats, blobs


def skip_blocked(name: str, cfg: dict) -> list[str]:
    """Keep a title Luma cannot hook out of dist/ - shipping it bricks that title.

    Luma's loader ends patchCode() with `if(!patchLayeredFs(...)) goto error;` and the
    error label is `svcBreak(USERBREAK_ASSERT)`. The check that leads there only runs
    when /luma/titles/<TID>/romfs exists, so a romfs folder for a title whose code has
    no hookable FS symbols (or no room for the redirect payload) turns every launch of
    that title into an exception screen. Output from an earlier build is removed too,
    otherwise `make package` would keep shipping it.
    """
    lines = [f"{name}: SKIPPED - {cfg['blocked']}"]
    for tid in cfg["tids"]:
        stale = ROOT / "dist" / "luma" / "titles" / tid
        if stale.is_dir():
            shutil.rmtree(stale)
            lines.append(f"  removed stale {stale.relative_to(ROOT)}")
    return lines


def app_name_tables(table: dict[str, str]) -> tuple[dict[str, bytes], list[str]]:
    """The two shapes of application-name table, from the one list in src/app_names.json.

    A title that reads SMDHs itself gets the table keyed by title id, and its buffer is
    rewritten. One that only ever receives finished strings gets the table keyed by the
    Russian name, and the pointer handed to its text setter is swapped instead.
    """
    entries = {
        tid: entry
        for tid, entry in json.loads((ROOT / "src" / "app_names.json").read_text(encoding="utf-8")).items()
        if not tid.startswith("_")
    }
    translated = {
        tid: {key: apply_homoglyphs(value, table) for key, value in entry.items() if key.startswith("ua")}
        for tid, entry in entries.items()
    }
    smdh_blob, smdh_log = smdh_names.build_table(translated)

    # The originals are compared against what the title holds in memory, so they stay as
    # Nintendo wrote them - no homoglyphs on that side.
    # `ru` is the short name, `ru_long` the one carrying a second line - the software card
    # in the Activity Log draws the long one, the lists draw the short one.
    def spellings(entry: dict, key: str) -> list[str]:
        value = entry.get(key)
        if not value:
            return []
        return [value] if isinstance(value, str) else list(value)

    pairs = [
        (original, apply_homoglyphs(replacement, table))
        for entry in entries.values()
        for key, replacement in (("ru", entry.get("ua")), ("ru_long", entry.get("ua_long") or entry.get("ua")))
        if replacement
        for original in spellings(entry, key)
    ]
    pane_blob, pane_log = pane_names.build_table(pairs)

    return {"smdh": smdh_blob, "pane": pane_blob}, [
        f"app names: {len(smdh_log)} titles, {len(smdh_blob)}-byte SMDH table, "
        f"{len(pane_log)} substitutions, {len(pane_blob)}-byte pane table"
    ]


def prepare_hook_patch(name: str, tid: str, names: dict[str, bytes] | None = None) -> tuple[dict[str, bytes], list[str]]:
    """Build the code.ips + exheader.bin that let Luma hook LayeredFS into `tid`.

    Anything missing is fatal on purpose, and this runs before the build writes anything:
    a title whose romfs reaches dist/ without the code patch is exactly the launch-time
    svcBreak() the patch exists to avoid.
    """
    if not luma_hook.has_patch(tid):
        raise SystemExit(f"{name}: {tid} needs a hook patch but tools/luma_hook.py has no entry for it")

    dump = ROOT / "work" / tid
    code = luma_hook.find_dump(dump, luma_hook.CODE_NAMES, luma_hook.CODE_PATTERNS)
    exheader = luma_hook.find_dump(dump, luma_hook.EXHEADER_NAMES, luma_hook.EXHEADER_PATTERNS)
    missing = [what for what, path in (("code", code), ("exheader", exheader)) if path is None]
    if missing:
        raise SystemExit(
            f"{name}: cannot build the LayeredFS hook for {tid}, no {' and no '.join(missing)} "
            f"file in work/{tid}/ (see docs/dump-code.md)"
        )

    return luma_hook.generate(tid, code, exheader, names)


def write_banner(tid: str) -> list[str]:
    """The replacement banner that title's hook reads off the SD card.

    It belongs to another title entirely - the picture is System Settings' - but it is
    HOME Menu that opens it, so it ships in HOME Menu's folder next to its code.ips.
    """
    hook = luma_hook.HOOK_PATCHES[tid.upper()].get("banner_hook")
    if not hook:
        return []
    written = []
    for title in hook["titles"]:
        blob = banner_mod.build(f"{title['title_id']:016X}")
        dest = ROOT / "dist" / "luma" / "titles" / tid / title["image_name"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(blob)
        written.append(f"{dest.relative_to(ROOT)} ({len(blob)} bytes)")
    return written


def write_romfs_image(tid: str, romfs_dir: Path, overrides: dict[str, bytes]) -> list[str]:
    """Rebuild the title's whole RomFS with the translations swapped in.

    Every language stays in the image, only the replaced slot's files differ - that is what
    keeps "switch the console language back" working as a way to undo the mod.
    """
    image = romfs.build(romfs_dir, overrides)
    read_back = romfs.read(image)
    for rel_path, blob in overrides.items():
        if read_back.get("/" + rel_path) != blob:
            raise SystemExit(f"{tid}: {rel_path} did not survive the RomFS rebuild")

    name = luma_hook.HOOK_PATCHES[tid.upper()]["image_name"]
    dest = ROOT / "dist" / "luma" / "titles" / tid / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(image)
    return [
        f"  RomFS image: {len(read_back)} files, {len(overrides)} replaced, "
        f"read back and compared",
        f"{dest.relative_to(ROOT)} ({len(image)} bytes)",
    ]


def write_shared_image(reader_tid: str, romfs_dir: Path, overrides: dict[str, bytes]) -> list[str]:
    """A shared data archive, rebuilt with the translations, next to the title that reads it.

    The error-message database belongs to no process of its own, so it ships inside the
    folder of each title whose code patch points at it - see msg_hook in tools/luma_hook.py.
    """
    hook = luma_hook.HOOK_PATCHES[reader_tid.upper()]["msg_hook"]
    image = romfs.build(romfs_dir, overrides)
    read_back = romfs.read(image)
    for rel_path, blob in overrides.items():
        if read_back.get("/" + rel_path) != blob:
            raise SystemExit(f"{reader_tid}: {rel_path} did not survive the RomFS rebuild")

    written = []
    for title in hook["titles"]:
        dest = ROOT / "dist" / "luma" / "titles" / reader_tid / title["image_name"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(image)
        written.append(
            f"  RomFS image: {len(read_back)} files, {len(overrides)} replaced, "
            f"read back and compared"
        )
        written.append(f"{dest.relative_to(ROOT)} ({len(image)} bytes)")
    return written


def build_csv(cfg: dict, romfs: Path, table: dict[str, str]) -> tuple[dict[str, bytes], list[str]]:
    """Translate the Russian column of the StreetPass Map's country and region tables.

    The map names the places you met people in, and those names live in UTF-16 CSV rather
    than MSBT - one column per language, Russian at index 11. Rows are keyed by
    "<country code>:<address id>", which is the same id the `area` archive numbers its
    regions with, so the two tables cannot drift apart.

    Country code 100 was Russia and is Ukraine now, exactly as in the `area` archive. Its
    region block is not translated but rebuilt: the 83 Russian rows go, and 27 Ukrainian
    ones take ids 2..28 - the same ids, in the same order, as the region file the country
    list hands to Ukraine. Every language column of those rows gets the transliteration and
    the Russian one the Ukrainian name, because the rows are Ukraine's now.
    """
    files = cfg.get("csv_tables")
    if not files:
        return {}, []

    strings = ROOT / "src" / "strings" / "plaza_map"
    render = lambda text: apply_homoglyphs(text, table)  # noqa: E731
    regions = json.loads((ROOT / "src" / "strings" / "area" / "EU_100.json").read_text(encoding="utf-8"))
    ukraine = {int(i) + 1: entry for i, entry in regions.items() if i.isdigit()}

    blobs, log = {}, []
    for rel, json_name in files.items():
        names = json.loads((strings / json_name).read_text(encoding="utf-8"))
        parsed = csvtab.load(romfs / rel)
        keep: list[csvtab.Row] = []
        rebuilt = 0
        for row in parsed.rows:
            if not row.is_row:
                keep.append(row)
                continue
            key = csvtab.key_of(row)
            code = int(row.fields[csvtab.COUNTRY_ID])
            if code == UKRAINE_CODE and key not in names:
                # A Russian region row: dropped, and the Ukrainian ones are appended below.
                continue
            entry = names.get(key)
            if entry is None:
                raise SystemExit(f"mii_plaza: {rel} row {key} has no translation in {json_name}")
            row.fields[csvtab.RUSSIAN] = render(entry["ua"])
            keep.append(row)
            if code == UKRAINE_CODE and json_name == "region.json":
                template = row
                for index, region in sorted(ukraine.items()):
                    fields = list(template.fields)
                    fields[csvtab.ADDRESS] = region["latin"]
                    fields[csvtab.ADDRESS_ID] = str(index)
                    for slot in range(csvtab.ENGLISH, len(fields)):
                        fields[slot] = render(region["ua"]) if slot == csvtab.RUSSIAN else region["latin"]
                    keep.append(csvtab.Row("", fields))
                    rebuilt += 1
        parsed.rows = keep
        blobs[rel] = parsed.build()
        note = f", {rebuilt} Ukrainian region rows rebuilt" if rebuilt else ""
        log.append(f"{rel}: {len(names)} names translated{note}")
    return blobs, log


def build_area(cfg: dict, tid: str, table: dict[str, str]) -> list[str]:
    """Write the `area` archive next to the title, with the EU lists translated.

    The whole dumped archive ships, all six console regions of it: the code patch makes the
    `area:` mount unconditional, so a console that reports a region other than EU has to
    find its files here too. Only the two EU files differ from the dump.

    Country code 100 was Russia and is now Ukraine, which is the same trade the language
    slot makes - Nintendo's country table has no Ukraine in any region. Its region list is
    therefore not translated but replaced: 83 Russian regions out, 27 Ukrainian ones in, so
    that file is re-emitted at the new size and the country record's own count follows.
    """
    source = ROOT / "work" / cfg["area"] / "romfs"
    if not source.is_dir():
        raise SystemExit(
            f"system_settings: the country lists need the `area` archive dumped to "
            f"work/{cfg['area']}/romfs/ (see docs/dumping.md)"
        )

    strings = ROOT / "src" / "strings" / "area"
    countries = json.loads((strings / "EU_country.json").read_text(encoding="utf-8"))
    regions = json.loads((strings / "EU_100.json").read_text(encoding="utf-8"))
    render = lambda text: apply_homoglyphs(text, table)  # noqa: E731

    country = area_mod.load(source / "EU" / "country_LZ.bin")
    area_mod.set_names(
        country,
        {int(code): entry["ua"] for code, entry in countries.items() if code.isdigit()},
        render=render,
    )
    area_mod.resort(country)
    area_mod.set_sub_count(country, UKRAINE_CODE, len(regions) - 1)

    ukraine = area_mod.resize(area_mod.load(source / "EU" / f"{UKRAINE_CODE}_LZ.bin"), len(regions) - 1)
    # JSON keys are 1..27 in list order; the records they land in are numbered from 2.
    names = {int(i) + 1: entry for i, entry in regions.items() if i.isdigit()}
    # The Russian slot carries the Ukrainian names; every other slot carries the
    # transliteration, because this file's records are Ukraine's now and leaving Russian
    # regions in the other languages would be worse than a name no EUR console displays.
    for slot in range(area_mod.NAME_SLOTS):
        ua = slot == area_mod.RU_SLOT
        key = "ua" if ua else "latin"
        area_mod.set_names(ukraine, {i: e[key] for i, e in names.items()}, slot=slot, render=render)
        area_mod.resort(ukraine, slot=slot)

    dest = ROOT / "dist" / "luma" / "titles" / tid / "area"
    replaced = {
        "EU/country_LZ.bin": country,
        f"EU/{UKRAINE_CODE}_LZ.bin": ukraine,
    }
    written = 0
    for path in sorted(source.rglob("*_LZ.bin")):
        rel = path.relative_to(source).as_posix()
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if rel in replaced:
            area_mod.save(replaced[rel], target)
        else:
            target.write_bytes(path.read_bytes())
        written += 1

    return [
        f"  area: {len(countries) - 1} EU countries translated, code {UKRAINE_CODE} is now "
        f"{countries[str(UKRAINE_CODE)]['ua']} with {len(regions) - 1} regions "
        f"(was {countries[str(UKRAINE_CODE)]['ru']}, 83)",
        f"{dest.relative_to(ROOT)}/ ({written} files)",
    ]


def build_smdh(name: str, cfg: dict, romfs: Path, table: dict[str, str]) -> tuple[dict[str, bytes], list[str]]:
    """Patched copies of the SMDH files a title keeps in its romfs.

    Only the language slot the mod overwrites is touched, and only its short and long
    description - the icon bitmaps come straight from the original file.
    """
    paths = cfg.get("smdh")
    if not paths:
        return {}, []
    entries = json.loads((ROOT / "src" / "strings" / name / "_smdh.json").read_text(encoding="utf-8"))
    index = smdh_mod.LANG_INDEX[cfg["lang"]]
    out: dict[str, bytes] = {}
    stats: list[str] = []
    for rel in paths:
        entry = entries.get(rel)
        if not entry or not entry.get("ua"):
            continue
        original = (romfs / rel).read_bytes()
        short = apply_homoglyphs(entry["ua"], table)
        long = apply_homoglyphs(entry.get("ua_long") or entry["ua"], table)
        out[rel] = smdh_mod.patch(original, index, short, long)
        stats.append(f"{rel}: SMDH {smdh_mod.LANGUAGES[index]} -> {entry['ua']!r}")
    return out, stats


def load_hud_glyphs() -> dict[int, tuple[list[list[tuple[int, int]]], int, int, int]]:
    """The added HUD glyphs, as tools/bcfnt.py wants them.

    The bitmaps are an asset rather than something generated here: drawing them needs
    Pillow and an outline font out of another title's romfs, neither of which a build has
    any business depending on. See tools/hud_glyphs.py for how they are made.

    Each pixel is a (luminance, alpha) pair: the letters are white with a one-pixel black
    outline, so alpha carries the whole silhouette and luminance only the white core.
    """
    data = json.loads((ROOT / "assets" / "hud_glyphs.json").read_text(encoding="utf-8"))
    return {
        int(code, 16): (
            [
                [(int(l, 16), int(a, 16)) for l, a in zip(core, silhouette)]
                for core, silhouette in zip(glyph["luminance"], glyph["alpha"])
            ],
            glyph["left"],
            glyph["glyph_width"],
            glyph["char_width"],
        )
        for code, glyph in data["glyphs"].items()
    }


def build_hud_font(cfg: dict, romfs: Path) -> tuple[dict[str, bytes], list[str]]:
    """A copy of the title's HUD font with the letters Ukrainian weekdays need.

    The clock line on the top screen is not drawn with the system font - every applet that
    shows it carries its own 15x17 bitmap subset, and the Cyrillic in that subset covers
    the Russian abbreviations only. `Нд` has no glyphs there at all, which is why Sunday
    renders as empty parentheses.
    """
    rel = cfg.get("hud_font")
    if not rel:
        return {}, []

    font = bcfnt.parse((romfs / rel).read_bytes())
    glyphs = load_hud_glyphs()
    bcfnt.add_glyphs(font, glyphs)
    added = " ".join(f"{chr(code)} U+{code:04X}" for code in sorted(glyphs))
    return {rel: bcfnt.build(font)}, [f"{rel}: HUD font + {added}"]


def build_title(name: str, table: dict[str, str]) -> list[str]:
    cfg = TITLES[name]
    if cfg.get("blocked"):
        return skip_blocked(name, cfg)

    wants_names = cfg.get("hook_patch") and any(luma_hook.wants_names(tid) for tid in cfg["tids"])
    names, names_stats = app_name_tables(table) if wants_names else (None, [])
    hooks = (
        {tid: prepare_hook_patch(name, tid, names) for tid in cfg["tids"]}
        if cfg.get("hook_patch")
        else {}
    )

    lang = cfg["lang"]
    romfs = ROOT / "work" / cfg["source_tid"] / "romfs"
    store = open_store(cfg, romfs)
    strings_dir = ROOT / "src" / "strings" / name

    all_langs = load_all_langs(strings_dir)
    cross_stats, cross_blobs = patch_other_langs(store, cfg, all_langs, table)

    updates: dict[str, bytes] = {}
    stats: list[str] = list(cross_stats)
    for key, data in sorted(store.read(lang).items()):
        json_file = strings_dir / f"{key}.json"
        if not json_file.exists():
            continue
        entries = json.loads(json_file.read_text(encoding="utf-8"))
        msbt = msbt_mod.parse(data)

        translated = 0
        for index in range(len(msbt.texts)):
            label = msbt.label_of(index) or f"__index_{index}"
            entry = entries.get(label)
            if not entry or not entry.get("ua"):
                continue
            msbt.texts[index] = apply_homoglyphs(entry["ua"], table)
            translated += 1

        for label, text in all_langs.get(key, {}).items():
            if label in msbt.labels:
                msbt.texts[msbt.labels[label]] = apply_homoglyphs(text, table)

        updates[key] = msbt_mod.build(msbt)
        stats.append(f"{key}: {translated}/{len(msbt.texts)} translated")

    csv_blobs, csv_stats = build_csv(cfg, romfs, table)
    stats += csv_stats
    smdh_blobs, smdh_stats = build_smdh(name, cfg, romfs, table)
    hud_blobs, hud_stats = build_hud_font(cfg, romfs)
    stats += smdh_stats + hud_stats + names_stats
    outputs = cross_blobs | store.outputs(lang, updates) | csv_blobs | smdh_blobs | hud_blobs
    written: list[str] = []
    for reader in cfg.get("ships_to", []):
        written += write_shared_image(reader, romfs, outputs)
    for tid in cfg["tids"] if not cfg.get("ships_to") else []:
        if luma_hook.has_patch(tid) and luma_hook.kind(tid) == "romfs_from_sd":
            # A whole image, not loose files: this title reads its RomFS off the SD card.
            written += write_romfs_image(tid, romfs, outputs)
            continue
        for rel_path, blob in outputs.items():
            dest = ROOT / "dist" / "luma" / "titles" / tid / "romfs" / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(blob)
            written.append(f"{dest.relative_to(ROOT)} ({len(blob)} bytes)")

    for tid in cfg["tids"]:
        if cfg.get("area"):
            written += build_area(cfg, tid, table)

    for tid, (files, log) in hooks.items():
        written += [f"  {line}" for line in log]
        written += write_banner(tid)
        for filename, blob in files.items():
            dest = ROOT / "dist" / "luma" / "titles" / tid / filename
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(blob)
            written.append(f"{dest.relative_to(ROOT)} ({len(blob)} bytes)")

    return stats + written


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("titles", nargs="*", default=None, help="names from TITLES; all of them when omitted")
    args = ap.parse_args()

    table = load_homoglyphs()
    names = args.titles or list(TITLES)
    for name in names:
        for line in build_title(name, table):
            print(line)


if __name__ == "__main__":
    main()
