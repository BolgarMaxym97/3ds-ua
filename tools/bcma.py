"""BCMA (`Manual.bcma`) reader and writer — the electronic manual container.

Three levels: an uncompressed DARC holding LZ10-compressed DARCs holding BCLYT pages and
BCLIM textures. Members are named `<REG>_<la>_<part>.arc` (`EUR_ru_large.arc`) plus the
shared `BcmaInfo.arc`, `Common_texture.arc` and the icons.

    Manual.bcma  (darc)
      BcmaInfo.arc            (lz10 -> darc)  BcmaInfo.bclyt: language list, page counts
      EUR_ru_index.arc        (lz10 -> darc)  Index.bclyt: the contents screen
      EUR_ru_large.arc        (lz10 -> darc)  Page_NNN_large_*.bclyt: pages, large font
      EUR_ru_small.arc        (lz10 -> darc)  the same pages, small font
      EUR_ru_texture.arc      (lz10 -> darc)  the screenshots on those pages
      Common_texture.arc  icon_05.arc

Only the members that are retranslated are unpacked and recompressed; everything else is
copied through byte for byte.

Usage:
    python3 tools/bcma.py <Manual.bcma>              # list members
    python3 tools/bcma.py <Manual.bcma> EUR_ru_large # list the pages inside one member
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import darc  # noqa: E402
import lz10  # noqa: E402

MEMBER_RE = re.compile(r"^(?P<region>[A-Z]{3})_(?P<lang>[a-z]{2})_(?P<part>[a-z]+)\.arc$")
TEXT_PARTS = ("index", "large", "small")


class Bcma:
    def __init__(self, data: bytes) -> None:
        self._archive = darc.parse(data)
        self._members = {e.name: e for e in self._archive.entries if not e.is_dir}

    @property
    def members(self) -> list[str]:
        return list(self._members)

    def locales(self) -> list[str]:
        """-> ['EUR_de', 'EUR_en', ...] — every region/language pair with pages."""
        found = set()
        for name in self._members:
            match = MEMBER_RE.match(name)
            if match and match["part"] in TEXT_PARTS:
                found.add(f"{match['region']}_{match['lang']}")
        return sorted(found)

    def read(self, member: str) -> dict[str, bytes]:
        """Unpack one `.arc` member -> {file name: contents}."""
        inner = darc.parse(lz10.decompress(self._members[self._key(member)].data))
        return {e.name.lstrip("./"): e.data for e in inner.entries if not e.is_dir}

    def write(self, member: str, files: dict[str, bytes]) -> None:
        """Repack one `.arc` member from {file name: contents}, keeping the file order."""
        key = self._key(member)
        inner = darc.parse(lz10.decompress(self._members[key].data))
        for entry in inner.entries:
            if entry.is_dir:
                continue
            name = entry.name.lstrip("./")
            if name not in files:
                raise KeyError(f"{member}: {name} missing from the rebuild")
            entry.data = files[name]
        self._members[key].data = lz10.compress(darc.build(inner))

    def build(self) -> bytes:
        return darc.build(self._archive)

    def _key(self, member: str) -> str:
        name = member if member.endswith(".arc") else f"{member}.arc"
        if name not in self._members:
            raise KeyError(f"no member {name} (have {', '.join(self._members)})")
        return name


def load(path: str | Path) -> Bcma:
    return Bcma(Path(path).read_bytes())


def main() -> None:
    manual = load(sys.argv[1])
    if len(sys.argv) > 2:
        for name, data in manual.read(sys.argv[2]).items():
            print(f"  {name:34} {len(data):7} bytes")
        return

    print(f"locales: {', '.join(manual.locales())}")
    for name in manual.members:
        print(f"  {name}")
    same = manual.build() == Path(sys.argv[1]).read_bytes()
    print(f"round-trip {'byte-identical' if same else 'differs (recompressed)'}")


if __name__ == "__main__":
    main()
