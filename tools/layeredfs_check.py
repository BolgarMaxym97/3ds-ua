"""Predict whether Luma3DS can hook LayeredFS into a title, without crashing the console.

Luma's loader ends patchCode() with

    if(isApp || isApplet) { ... if(!patchLayeredFs(...)) goto error; }
    error: svcBreak(USERBREAK_ASSERT);

and patchLayeredFs() only runs when /luma/titles/<TID>/romfs exists. So shipping a romfs
folder for a title whose code cannot be hooked turns every launch of that title into an
exception screen - the file contents are irrelevant, the loader never reads them.

This is a port of the two checks that decide it, from sysmodules/loader/source/patcher.c:
findLayeredFsSymbols() and findLayeredFsPayloadOffset().

For a title listed in tools/luma_hook.py the verdict is about the *patched* code: the
loader applies /luma/titles/<TID>/code.ips before it searches for the symbols, so the
unpatched dump is not what ever runs.

Usage:
    python3 tools/layeredfs_check.py work/000400300000D002

Expects the title's executable and exheader in that directory, under any of the names
GodMode9 produces:

    code:     code.bin | *.code | code.dec.bin
    exheader: exheader.bin | exthdr.bin | *.exthdr

A BLZ-compressed .code is unpacked automatically; a file already decompressed by
GodMode9's "Extract .code" is used as is. See tools/dump.md for the dumping steps.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import luma_hook  # noqa: E402
from build import TITLES  # noqa: E402

ROMFS_REDIR_PATCH_SIZE = 0xB4  # size of Luma's redirect payload
PATH_STRING_SIZE = 39          # "/luma/titles/<16 hex>/romfs" plus terminator


def blz_decompress(data: bytes) -> bytes:
    """Nintendo backwards-LZ used for ExeFS .code. Returns data unchanged if not packed."""
    if len(data) < 8:
        return data
    footer = data[-8:]
    extra_size = struct.unpack_from("<I", footer, 4)[0]
    if extra_size == 0:
        return data

    header_size = footer[3]
    compressed_end = struct.unpack_from("<I", footer, 0)[0] & 0x00FFFFFF
    if not (8 <= header_size <= 0x20) or compressed_end > len(data):
        return data

    out = bytearray(data)
    out.extend(b"\x00" * (extra_size - 8 if extra_size > 8 else 0))
    total = len(data) + extra_size - header_size

    src = len(data) - header_size
    dst = total
    stop = len(data) - compressed_end

    out = bytearray(data + b"\x00" * (total - len(data)))
    while src > stop:
        src -= 1
        flags = out[src]
        for bit in range(8):
            if src <= stop:
                break
            if not (flags << bit) & 0x80:
                src -= 1
                dst -= 1
                out[dst] = out[src]
                continue
            src -= 2
            pos = ((out[src] << 8) | out[src + 1]) & 0x0FFF
            length = (out[src] >> 4) + 3
            for _ in range(length):
                dst -= 1
                out[dst] = out[dst + pos + 2]

    return bytes(out[:total])


def find_function_start(code: bytes, pos: int) -> int | None:
    """Walk back to the nearest `push {...}` (0xE92D in the top half-word)."""
    while pos >= 4:
        pos -= 4
        if struct.unpack_from("<H", code, pos + 2)[0] == 0xE92D:
            return pos
    return None


def find_symbols(code: bytes, size: int) -> dict[str, int | None]:
    """Port of findLayeredFsSymbols(): five FS wrappers matched by instruction signatures."""
    found: dict[str, int | None] = {
        "fsMountArchive": None,
        "fsRegisterArchive": None,
        "fsTryOpenFile": None,
        "fsOpenFileDirectly": None,
        "fsUnmountArchive": None,
    }

    def word(offset: int) -> int:
        return struct.unpack_from("<I", code, offset)[0]

    for addr in range(0, size - 3, 4):
        value = word(addr)
        target = None

        if value == 0xE5970010 and addr <= size - 12 and found["fsMountArchive"] is None:
            if word(addr + 4) == 0xE1CD20D8 and (word(addr + 8) & 0xFFFFFF) == 0x008D0000:
                target = "fsMountArchive"
        elif value == 0xE24DD028 and addr <= size - 16 and found["fsMountArchive"] is None:
            if word(addr + 4) == 0xE1A04000 and word(addr + 8) == 0xE59F60A8 and word(addr + 12) == 0xE3A0C001:
                target = "fsMountArchive"
        elif value == 0xE2844001 and addr <= size - 12 and found["fsUnmountArchive"] is None:
            if word(addr + 4) == 0xE3540020 and word(addr + 8) == 0x3AFFFFF0:
                target = "fsUnmountArchive"
        elif value == 0xE353003A and addr <= size - 12 and found["fsUnmountArchive"] is None:
            if (word(addr + 4) & 0xFFFFFF0F) == 0x0A000009 and (word(addr + 8) & 0xFFFF0FF0) == 0xE1A00400:
                target = "fsUnmountArchive"
        elif value == 0xE3500008 and addr <= size - 12 and found["fsRegisterArchive"] is None:
            if (word(addr + 4) & 0xFFF00FF0) == 0xE1800400 and (word(addr + 8) & 0xFFF00FF0) == 0xE1800FC0:
                target = "fsRegisterArchive"
        elif value == 0xE351003A and addr <= size - 0x40 and found["fsTryOpenFile"] is None:
            if word(addr + 4) == 0x1AFFFFFC and word(addr + 0x34) == 0xE590C000 and word(addr + 0x3C) == 0xE12FFF3C:
                target = "fsTryOpenFile"
        elif value == 0x08030204 and found["fsOpenFileDirectly"] is None:
            target = "fsOpenFileDirectly"

        if target:
            start = find_function_start(code, addr)
            if start is not None:
                found[target] = start

    return found


def find_payload_space(code: bytes, text_size: int, ro_size: int, data_size: int) -> tuple[bool, bool, str]:
    """Port of findLayeredFsPayloadOffset(): room for the payload and for the path string."""
    rounded_text = (text_size + 0xFFF) & ~0xFFF
    rounded_ro = (ro_size + 0xFFF) & ~0xFFF
    rounded_data = (data_size + 0xFFF) & ~0xFFF

    if rounded_text - text_size >= ROMFS_REDIR_PATCH_SIZE:
        payload, payload_via = True, ".text padding"
    else:
        payload, payload_via = _find_throw_fatal_error(code, text_size), "throwFatalError()"

    if rounded_ro - ro_size >= PATH_STRING_SIZE:
        path, path_via = True, ".rodata padding"
    elif rounded_data - data_size >= PATH_STRING_SIZE:
        path, path_via = True, ".data padding"
    else:
        path = any(
            struct.unpack_from("<I", code, addr)[0] == 0xE3A00B42 and find_function_start(code, addr) is not None
            for addr in range(0, text_size - 3, 4)
        )
        path_via = "function with 0xE3A00B42"

    return payload, path, f"payload via {payload_via}, path via {path_via}"


def _find_throw_fatal_error(code: bytes, size: int) -> bool:
    svc_connect_to_port = None
    for addr in range(4, size - 3, 4):
        if struct.unpack_from("<I", code, addr)[0] == 0xEF00002D:
            svc_connect_to_port = addr - 4
            break
    if svc_connect_to_port is None:
        return False

    for i in range(4, size - 3, 4):
        branch = 0xEB000000 | (((svc_connect_to_port - i - 8) >> 2) & 0xFFFFFF)
        if struct.unpack_from("<I", code, i)[0] != branch:
            continue
        func = find_function_start(code, i)
        if func is None:
            continue
        pos = func + 4
        while pos <= size - 4 and struct.unpack_from("<H", code, pos + 2)[0] != 0xE92D:
            if struct.unpack_from("<I", code, pos)[0] == 0xE200167E:
                func = None
                break
            pos += 4
        if func is not None:
            return True
    return False


def find_input(title_dir: Path, names: tuple[str, ...], patterns: tuple[str, ...]) -> Path | None:
    for name in names:
        candidate = title_dir / name
        if candidate.is_file():
            return candidate
    for pattern in patterns:
        matches = sorted(title_dir.glob(pattern))
        if matches:
            return matches[0]
    return None


def check(title_dir: Path) -> bool | None:
    """True/False for a verdict, None when there is no dump to judge - not the same thing."""
    code_path = find_input(title_dir, ("code.bin", "code.dec.bin", ".code"), ("*.code",))
    exheader_path = find_input(title_dir, ("exheader.bin", "exthdr.bin"), ("*.exthdr",))
    if code_path is None or exheader_path is None:
        missing = "code" if code_path is None else "exheader"
        print(f"{title_dir.name}: no {missing} file found, skipped (see docs/dump-code.md)")
        return None

    exheader = exheader_path.read_bytes()
    text_size = struct.unpack_from("<I", exheader, 0x18)[0]
    ro_size = struct.unpack_from("<I", exheader, 0x28)[0]
    data_size = struct.unpack_from("<I", exheader, 0x38)[0]
    compressed = bool(exheader[0x0D] & 1)

    code = code_path.read_bytes()
    # GodMode9's "Extract .code" already unpacks, so trust the section sizes over the flag:
    # a file that is at least text+ro+data long cannot still be compressed.
    sections = text_size + ro_size + data_size
    if compressed and len(code) < sections:
        code = blz_decompress(code)
        state = "BLZ-unpacked here"
    else:
        state = "already decompressed"

    print(f"=== {title_dir.name}")
    print(f"  {code_path.name} + {exheader_path.name}: {len(code)} bytes ({state}), "
          f"text {text_size}, ro {ro_size}, data {data_size}")
    if len(code) < sections:
        print(f"  !! code is shorter than text+ro+data ({sections}) - wrong or still-packed file")
        return False

    # A title with a hook patch never runs unpatched: loader applies our code.ips before
    # it looks for the symbols, so that is the code the verdict has to be about.
    if luma_hook.has_patch(title_dir.name):
        code = luma_hook.patched_code(title_dir.name, code)
        print(f"  code.ips from tools/luma_hook.py applied")

    symbols = find_symbols(code, min(text_size, len(code)))
    got = {name: off for name, off in symbols.items() if off is not None}
    # fsUnmountArchive is the one Luma tolerates missing
    required = len(got) == 5 or (len(got) == 4 and symbols["fsUnmountArchive"] is None)
    for name, off in symbols.items():
        print(f"    {name:20} {'0x%06X' % off if off is not None else 'NOT FOUND'}")

    payload, path, how = find_payload_space(code, min(text_size, len(code)), ro_size, data_size)
    print(f"    payload space        {'ok' if payload else 'NOT FOUND'}")
    print(f"    path string space    {'ok' if path else 'NOT FOUND'}   ({how})")

    ok = required and payload and path
    print(f"  -> {'LayeredFS OK - safe to ship' if ok else 'LOADER WOULD CRASH - mark blocked'}")
    return ok


def shipped_titles() -> dict[str, str]:
    """TID -> title name, only for titles the build actually writes to dist/."""
    return {
        tid: name
        for name, cfg in TITLES.items()
        if not cfg.get("blocked")
        for tid in cfg["tids"]
    }


def main() -> None:
    targets = sys.argv[1:] or [str(p) for p in sorted(Path("work").iterdir()) if p.is_dir()]
    shipped = shipped_titles()
    conflicts = []

    for target in targets:
        path = Path(target)
        ok = check(path)
        if ok is None:
            continue
        name = shipped.get(path.name)
        if name and not ok:
            conflicts.append(
                f"{name} ({path.name}) is shipped but would crash - add `blocked` in TITLES, "
                f"or a hook patch in tools/luma_hook.py"
            )
        elif name is None and ok and path.name in {tid for cfg in TITLES.values() for tid in cfg["tids"]}:
            conflicts.append(f"{path.name} is marked blocked but looks hookable - re-test it on hardware")

    if conflicts:
        print("\nmismatch with TITLES:")
        for line in conflicts:
            print(f"  !! {line}")
        sys.exit(1)

    print("\nverdicts agree with TITLES")


if __name__ == "__main__":
    main()
