"""Inspect a freshly dumped romfs: language folders, message files, string counts.

Usage:
    python3 tools/dumpinfo.py work/000400300000D002
    python3 tools/dumpinfo.py work/*/          # every dump at once

Run this right after dumping a title to confirm the dump is complete and to see how
much text it holds before wiring it into TITLES.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lz11 import decompress  # noqa: E402
from msbt import parse  # noqa: E402


def count_strings(path: Path) -> tuple[int, str]:
    """-> (number of messages, note); the note explains why a file was skipped."""
    try:
        raw = path.read_bytes()
        data = decompress(raw) if path.name.endswith("_LZ.bin") else raw
        if data[:8] != b"MsgStdBn":
            return 0, f"not MSBT ({data[:4]!r})"
        return len(parse(data).texts), ""
    except Exception as exc:  # noqa: BLE001 - a dump can hold anything
        return 0, f"{type(exc).__name__}: {exc}"


def inspect(title_dir: Path) -> None:
    romfs = title_dir / "romfs"
    if not romfs.is_dir():
        print(f"{title_dir}: no romfs/ inside")
        return

    size = sum(p.stat().st_size for p in romfs.rglob("*") if p.is_file())
    print(f"\n=== {title_dir.name}  ({size / 1024:.0f} KiB)")

    message_dirs = sorted(p for p in romfs.iterdir() if p.is_dir() and p.name.startswith("message"))
    if not message_dirs:
        top = ", ".join(sorted(p.name for p in romfs.iterdir())[:12])
        print(f"  no message*/ folders. Top level: {top}")
        return

    for message_dir in message_dirs:
        langs = sorted(p.name for p in message_dir.iterdir() if p.is_dir())
        print(f"  {message_dir.name}/  languages: {len(langs)}")
        print(f"    {', '.join(langs)}")

        english = next((message_dir / lang for lang in langs if "English" in lang), None)
        if english is None:
            print("    !! no English folder - the mod needs one")
            continue

        total = 0
        for file in sorted(english.iterdir()):
            count, note = count_strings(file)
            total += count
            detail = f"{count} strings" if not note else note
            print(f"    {english.name}/{file.name}: {detail}")
        print(f"    -> {total} translatable strings")


def main() -> None:
    targets = sys.argv[1:] or ["work"]
    for target in targets:
        path = Path(target)
        if (path / "romfs").is_dir():
            inspect(path)
        else:
            for child in sorted(p for p in path.iterdir() if p.is_dir()):
                inspect(child)


if __name__ == "__main__":
    main()
