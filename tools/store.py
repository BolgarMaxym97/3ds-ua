"""Uniform access to a title's message files, whichever layout it uses.

Three layouts appear in 3DS system titles:

  plain        romfs/message*/<LANG>/<file>.msbt          HOME Menu, keyboard, Activity Log
  container    romfs/<file>  -> LZ11 -> darc -> <dir>/<LANG>/<file>.msbt   System Settings
  per-language romfs/message/<LANG>.arc -> LZ11 -> darc -> <file>.msbt     Mii Maker
               romfs/msg/<LANG>.LZ -> LZ11 -> flat archive -> <file>.msbt  Camera, Sound

The per-language archive comes in two formats, told apart by the `darc` magic: the darc
of Mii Maker and the header-less flat table of Camera and Sound (see tools/msgarc.py).

A store hides that difference behind three calls:

    store.languages()                  -> ["EU_English", "EU_Russian", ...]
    store.read(lang)                   -> {key: raw MSBT bytes}
    store.outputs(lang, {key: bytes})  -> {romfs-relative path: file bytes}

`key` matches the JSON file name in src/strings/<title>/ (`<message_dir>__<file_stem>`),
so the same keys work across extract, validate and build.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import darc as darc_mod  # noqa: E402
import msgarc as msgarc_mod  # noqa: E402
from lz11 import compress, decompress  # noqa: E402

MSBT_MAGIC = b"MsgStdBn"


def open_store(cfg: dict, romfs: Path) -> Store:
    container = cfg.get("container")
    if container is None:
        return PlainStore(romfs)
    if "{lang}" in container:
        return PerLanguageStore(romfs, container)
    return ContainerStore(romfs, container)


def _unpack(raw: bytes) -> bytes:
    return decompress(raw) if raw[:1] == b"\x11" else raw


def _repack(original: bytes, data: bytes) -> bytes:
    return compress(data) if original[:1] == b"\x11" else data


def _archive_module(data: bytes):
    """Which archive format an unpacked per-language container is in."""
    return darc_mod if data[: len(darc_mod.MAGIC)] == darc_mod.MAGIC else msgarc_mod


class Store:
    def languages(self) -> list[str]:
        raise NotImplementedError

    def read(self, lang: str) -> dict[str, bytes]:
        raise NotImplementedError

    def outputs(self, lang: str, updates: dict[str, bytes]) -> dict[str, bytes]:
        raise NotImplementedError


class PlainStore(Store):
    """One MSBT per file on disk, grouped by language folder."""

    def __init__(self, romfs: Path) -> None:
        self.romfs = romfs
        self.message_dirs = sorted(
            p.name for p in romfs.iterdir() if p.is_dir() and p.name.startswith("message")
        )

    def languages(self) -> list[str]:
        langs: set[str] = set()
        for message_dir in self.message_dirs:
            langs |= {p.name for p in (self.romfs / message_dir).iterdir() if p.is_dir()}
        return sorted(langs)

    def read(self, lang: str) -> dict[str, bytes]:
        out: dict[str, bytes] = {}
        for message_dir in self.message_dirs:
            lang_dir = self.romfs / message_dir / lang
            if not lang_dir.is_dir():
                continue
            for file in sorted(lang_dir.iterdir()):
                data = _unpack(file.read_bytes())
                if data[:8] == MSBT_MAGIC:
                    out[f"{message_dir}__{file.name.split('.')[0]}"] = data
        return out

    def outputs(self, lang: str, updates: dict[str, bytes]) -> dict[str, bytes]:
        out: dict[str, bytes] = {}
        for message_dir in self.message_dirs:
            lang_dir = self.romfs / message_dir / lang
            if not lang_dir.is_dir():
                continue
            for file in sorted(lang_dir.iterdir()):
                key = f"{message_dir}__{file.name.split('.')[0]}"
                if key not in updates:
                    continue
                raw = file.read_bytes()
                out[f"{message_dir}/{lang}/{file.name}"] = _repack(raw, updates[key])
        return out


class ContainerStore(Store):
    """A single LZ11+darc archive holding <dir>/<LANG>/<file>.msbt for every language."""

    def __init__(self, romfs: Path, container: str) -> None:
        self.romfs = romfs
        self.container = container
        self.raw = (romfs / container).read_bytes()
        self.archive = darc_mod.parse(_unpack(self.raw))

    def languages(self) -> list[str]:
        return sorted({parts[-2] for parts, _ in self._msbt_entries()})

    def read(self, lang: str) -> dict[str, bytes]:
        return {
            f"{parts[-3]}__{parts[-1].split('.')[0]}": entry.data
            for parts, entry in self._msbt_entries()
            if parts[-2] == lang
        }

    def outputs(self, lang: str, updates: dict[str, bytes]) -> dict[str, bytes]:
        for parts, entry in self._msbt_entries():
            if parts[-2] != lang:
                continue
            key = f"{parts[-3]}__{parts[-1].split('.')[0]}"
            if key in updates:
                entry.data = updates[key]
        return {self.container: _repack(self.raw, darc_mod.build(self.archive))}

    def _msbt_entries(self) -> list[tuple[list[str], darc_mod.Entry]]:
        out = []
        for path, entry in self.archive.files():
            if entry.data[:8] == MSBT_MAGIC:
                out.append((path.split("/"), entry))
        return out


class PerLanguageStore(Store):
    """One LZ11+darc archive per language, e.g. message/EU_English.arc."""

    def __init__(self, romfs: Path, template: str) -> None:
        self.romfs = romfs
        self.template = template
        self.message_dir = str(Path(template).parent)
        pattern = Path(template.format(lang="*")).name
        self.archives = sorted((romfs / self.message_dir).glob(pattern))

    def languages(self) -> list[str]:
        return sorted(p.name.split(".")[0] for p in self.archives)

    def read(self, lang: str) -> dict[str, bytes]:
        data = _unpack(self._path(lang).read_bytes())
        archive = _archive_module(data).parse(data)
        return {
            f"{self.message_dir}__{path.split('/')[-1].split('.')[0]}": entry.data
            for path, entry in archive.files()
            if entry.data[:8] == MSBT_MAGIC
        }

    def outputs(self, lang: str, updates: dict[str, bytes]) -> dict[str, bytes]:
        raw = self._path(lang).read_bytes()
        data = _unpack(raw)
        module = _archive_module(data)
        archive = module.parse(data)
        for path, entry in archive.files():
            key = f"{self.message_dir}__{path.split('/')[-1].split('.')[0]}"
            if key in updates:
                entry.data = updates[key]
        return {self.template.format(lang=lang): _repack(raw, module.build(archive))}

    def _path(self, lang: str) -> Path:
        return self.romfs / self.template.format(lang=lang)
