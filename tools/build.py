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
import luma_hook  # noqa: E402
import msbt as msbt_mod  # noqa: E402
import romfs  # noqa: E402
from store import open_store  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

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
    },
    "mii_maker": {
        "tids": ["0004001000022700"],
        "source_tid": "0004001000022700",
        "lang": "EU_Russian",
        "ref_lang": "EU_English",
        "container": "message/{lang}.arc",
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


def prepare_hook_patch(name: str, tid: str) -> tuple[dict[str, bytes], list[str]]:
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

    return luma_hook.generate(tid, code, exheader)


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


def build_title(name: str, table: dict[str, str]) -> list[str]:
    cfg = TITLES[name]
    if cfg.get("blocked"):
        return skip_blocked(name, cfg)

    hooks = {tid: prepare_hook_patch(name, tid) for tid in cfg["tids"]} if cfg.get("hook_patch") else {}

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

    outputs = cross_blobs | store.outputs(lang, updates)
    written: list[str] = []
    for tid in cfg["tids"]:
        if luma_hook.has_patch(tid) and luma_hook.kind(tid) == "romfs_from_sd":
            # A whole image, not loose files: this title reads its RomFS off the SD card.
            written += write_romfs_image(tid, romfs, outputs)
            continue
        for rel_path, blob in outputs.items():
            dest = ROOT / "dist" / "luma" / "titles" / tid / "romfs" / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(blob)
            written.append(f"{dest.relative_to(ROOT)} ({len(blob)} bytes)")

    for tid, (files, log) in hooks.items():
        written += [f"  {line}" for line in log]
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
