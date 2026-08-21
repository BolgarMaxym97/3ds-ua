"""Which language slot the mod takes over.

The console's language list is fixed - there is no room for a new entry - so Ukrainian has
to stand where one of the shipped languages stood. Which one is a build-time choice, and it
is the only difference between the two builds:

    ru   the Russian slot is overwritten; English and the rest stay as Nintendo shipped
         them. Output goes to dist/, the archive is 3ds-ua-from-ru-<version>.zip.
    en   the English slot is overwritten; Russian and the rest stay. Output goes to
         dist_en/, the archive is 3ds-ua-from-en-<version>.zip.

Everything the build touches picks its slot from here: the MSBT language folder, the SMDH
and `area` language index, the CSV column of the StreetPass Map, the CBMD banner slot, the
locale inside an electronic manual, and which spelling of an application name the HOME Menu
patch matches against. The translations themselves are the same in both builds - the budgets
they are validated against are the widest official localisation of each label, not the slot's
own text, so no string has to be rewritten to move slots.

The choice travels in the environment rather than through every call, because one build is
several processes (build.py, manual.py, package.py): they all read `UA_SLOT`, and `--slot`
on any of them sets it.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import cbmd  # noqa: E402
import csvtab  # noqa: E402
import smdh  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ENV_VAR = "UA_SLOT"
DEFAULT = "ru"


@dataclass(frozen=True)
class Slot:
    """One replaceable language, named the way each format names it."""

    key: str
    lang: str            # MSBT language folder, e.g. work/<tid>/romfs/message/EU_Russian/
    manual_lang: str     # the Instruction Manual applet spells the Russian one "EU_Russia"
    manual_slot: str     # locale inside a Manual.bcma document
    banner_slot: int     # CBMD block, HOME Menu's own numbering - see tools/cbmd.py
    csv_column: int      # column of the StreetPass Map tables - see tools/csvtab.py
    app_name_key: str    # the spelling pane_names matches against in src/app_names.json
    dist_name: str
    original: str        # what the replaced entry of the language picker says without the mod

    @property
    def smdh_index(self) -> int:
        """The SMDH language block, and the `area` name slot: one order serves both."""
        return smdh.LANG_INDEX[self.lang]

    @property
    def dist(self) -> Path:
        return ROOT / self.dist_name


SLOTS = {
    "ru": Slot(
        key="ru",
        lang="EU_Russian",
        manual_lang="EU_Russia",
        manual_slot="EUR_ru",
        banner_slot=cbmd.EUR_RU,
        csv_column=csvtab.RUSSIAN,
        app_name_key="ru",
        dist_name="dist",
        original="Русский",
    ),
    "en": Slot(
        key="en",
        lang="EU_English",
        manual_lang="EU_English",
        manual_slot="EUR_en",
        banner_slot=cbmd.EUR_EN,
        csv_column=csvtab.ENGLISH,
        app_name_key="en",
        dist_name="dist_en",
        original="English",
    ),
}


# One more axis, and a much smaller one: the console model. Everything a New 3DS needs and
# an Old 3DS must not get is built into <dist>/new3ds/ and laid over the rest by
# tools/package.py, which ships the two as separate archives. It is one folder rather than a
# second dist tree because exactly two titles differ - see write_loader_alias() in
# tools/build.py.
NEW3DS_DIR = "new3ds"


def current() -> Slot:
    key = os.environ.get(ENV_VAR) or DEFAULT
    if key not in SLOTS:
        raise SystemExit(f"{ENV_VAR}={key!r}: no such slot, pick one of {', '.join(SLOTS)}")
    return SLOTS[key]


def select(key: str) -> Slot:
    """Fix the slot for this process and everything it starts."""
    os.environ[ENV_VAR] = key
    return current()


def dist() -> Path:
    """Where this build writes - dist/ or dist_en/."""
    return current().dist


def new3ds_dist() -> Path:
    """The New 3DS half of this build - dist/new3ds/ or dist_en/new3ds/."""
    return current().dist / NEW3DS_DIR


def add_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--slot",
        choices=sorted(SLOTS),
        default=os.environ.get(ENV_VAR) or DEFAULT,
        help="which language the mod replaces (default: %(default)s)",
    )
