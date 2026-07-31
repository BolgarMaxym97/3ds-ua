"""Give Luma the `fsMountArchive` a title is missing, so LayeredFS can hook it.

Some system titles have no "mount archive by id" function at all, so
findLayeredFsSymbols() cannot find one and patchLayeredFs() returns false - which makes
the loader svcBreak() on every launch. The reason the function is absent is in the
exheader: those titles have no `DirectSdmc` right, so the SDK never linked SD-mounting
code into them.

Both halves can be supplied from the SD card, because loader's patchCode() runs

    applyCodeIpsPatch(progId, code, size);   // /luma/titles/<TID>/code.ips
    ...
    patchLayeredFs(...);                     // needs the symbol

in that order, and GetProgramInfoImpl() reads /luma/titles/<TID>/exheader.bin over the
real exheader before the process is created. So this module emits two files per title:

    code.ips        a stub that Luma resolves as fsMountArchive
    exheader.bin    the original exheader with the DirectSdmc bit set

The stub is written over throwFatalError() - the function Luma itself overwrites when it
needs room for its own payload - and is laid out so that

    findFunctionStart()  walks back from the signature words to the stub's `push`,
    the signature words  sit behind an unconditional branch and never execute,
    the executable part  builds the FSUSER_OpenArchive(archiveId, PATH_EMPTY) call the
                         title never makes itself, then jumps into the tail of one of the
                         title's own mount functions, which allocates the archive object
                         (vtable + fs session + handle) and stores it to *out.

Offsets are specific to one build of one title - not to a system version. What identifies
that build is the title's own `remaster_version` (exheader offset 0x0E), which counts how
many times Nintendo ever updated the title, plus the sha256 of its .code. Both are checked
before anything is generated, because an IPS applied at the wrong offset would corrupt the
title.
"""

from __future__ import annotations

import hashlib
import struct
from pathlib import Path

TEXT_VA = 0x100000

# Exheader offsets: remaster version sits in the code set info, access info in the ARM11
# local system capabilities block.
REMASTER_VERSION_OFFSET = 0x0E
TEXT_SIZE_OFFSET = 0x18
ACCESS_INFO_OFFSET = 0x248
DIRECT_SDMC_BIT = 7

# TID -> everything needed to build the stub. All offsets are .text offsets, i.e.
# virtual address minus TEXT_VA, which is also the offset inside code.bin and the
# offset an IPS record addresses.
HOOK_PATCHES: dict[str, dict] = {
    # Activity Log (PLOG), EUR, title version 2. Verified working on hardware.
    # Nintendo updated this title twice in its lifetime - HOME Menu is at 29 by comparison -
    # so this one build spans most system versions, including the final 11.17.0-50.
    "0004001000022200": {
        "title": "Activity Log (PLOG) EUR",
        "title_version": 2,
        "code_sha256": "a8a665bd0c807d9150b5024d3674d6c71088d7ef26c54af5f34ec98de439ca40",
        "variant": "r4_frame28",
        "stub_off": 0xB3FCC,     # throwFatalError(), which Luma leaves alone here
        "stub_room": 416,        # bytes until the next function's `push`
        "open_archive": 0xD40C,  # the title's own FSUSER_OpenArchive IPC wrapper
        "mount_tail": 0xD2B4,    # tail of MountSharedExtData(): allocates and stores the object
        "globals_off": 0xD328,   # literal holding the nn::fs globals base (+0x10 = fs:USER session)
    },
    # Instruction Manual (ebird), EUR, title version 5.
    #
    # This one cannot use throwFatalError(): its .text padding is 88 bytes, less than the
    # 0x114 Luma needs, so Luma claims throwFatalError() for its own payload and only 12
    # bytes of it would survive. The stub goes into that 88-byte page padding instead - it
    # is inside the mapped, executable .text pages and Luma has no use for it.
    #
    # findLayeredFsSymbols() only scans up to text.size, which stops short of the padding,
    # so the shipped exheader also rounds text.size up to the page boundary. That is free:
    # the loader derives everything from (size + 4095) >> 12, and 0xADFA8 and 0xAE000 both
    # come to 174 pages, so section addresses, the .code layout and the mapping are all
    # byte-for-byte what they were.
    "0004003000009B02": {
        "title": "Instruction Manual (ebird) EUR",
        "title_version": 5,
        "code_sha256": "cf4658f9f618a41f8d32ff7aed40d0ea565da78a2ace349cb93698ff5f7df5d8",
        "variant": "sl_frame14",
        "stub_off": 0xADFA8,        # start of the .text page padding
        "stub_room": 88,            # up to the 0xAE000 page boundary
        "text_size_override": 0xAE000,
        "open_archive": 0x65FC8,
        "mount_tail": 0x2F878,      # tail of MountSystemSaveData(), entered with r8 = result
        "globals_off": 0x2F8F0,
    },
}


def has_patch(tid: str) -> bool:
    return tid.upper() in HOOK_PATCHES


def _bl(src: int, dst: int) -> int:
    return 0xEB000000 | (((dst - src - 8) >> 2) & 0xFFFFFF)


def _b(src: int, dst: int) -> int:
    return 0xEA000000 | (((dst - src - 8) >> 2) & 0xFFFFFF)


SIGNATURE = (
    0xE5970010,  # Luma's fsMountArchive signature, word 1
    0xE1CD20D8,  #                                  word 2
    0xE58D0000,  #                                  word 3
)


def _stub_r4_frame28(patch: dict, globals_value: int) -> list[int]:
    """Tail takes the result in r0, `out` in r4, globals in r6, on a 0x28 frame."""
    s = patch["stub_off"]
    return [
        0xE92D41F0,              # +00  push {r4,r5,r6,r7,r8,lr}  <- findFunctionStart lands here
        _b(s + 0x04, s + 0x18),  # +04  b    +0x18                 skips the signature block
        *SIGNATURE,              # +08  never executed
        0xE1A00000,              # +14  nop
        0xE24DD028,              # +18  sub  sp, sp, #0x28         the frame mount_tail expects
        0xE1A04000,              # +1C  mov  r4, r0                r4 = out
        0xE1A02001,              # +20  mov  r2, r1                r2 = archiveId (9 = SDMC)
        0xE3A03001,              # +24  mov  r3, #1                r3 = PATH_EMPTY
        0xE3A05000,              # +28  mov  r5, #0
        0xE58D5018,              # +2C  str  r5, [sp, #0x18]       empty path = one NUL byte
        0xE28D0018,              # +30  add  r0, sp, #0x18
        0xE58D0000,              # +34  str  r0, [sp]              stack arg: path pointer
        0xE3A00001,              # +38  mov  r0, #1
        0xE58D0004,              # +3C  str  r0, [sp, #4]          stack arg: path size
        0xE59F6014,              # +40  ldr  r6, [pc, #0x14]       r6 = nn::fs globals
        0xE5960010,              # +44  ldr  r0, [r6, #0x10]       fs:USER session handle
        0xE58D000C,              # +48  str  r0, [sp, #0xc]
        0xE28D1010,              # +4C  add  r1, sp, #0x10         out: archive handle
        0xE28D000C,              # +50  add  r0, sp, #0xc
        _bl(s + 0x54, patch["open_archive"]),  # +54  bl FSUSER_OpenArchive wrapper
        _b(s + 0x58, patch["mount_tail"]),     # +58  b  shared mount tail
        globals_value,           # +5C  literal
    ]


def _stub_sl_frame14(patch: dict, globals_value: int) -> list[int]:
    """Tail takes the result in r8, `out` in sl, globals in sb, on a 0x14 frame.

    Tighter than the other variant because it has to fit in one page of .text padding:
    the session is passed as `sb + 0x10` instead of being copied onto the stack, and the
    two stack arguments go out in one `stm`.
    """
    s = patch["stub_off"]
    return [
        0xE92D4FF0,              # +00  push {r4,r5,r6,r7,r8,sb,sl,fp,lr}
        _b(s + 0x04, s + 0x14),  # +04  b    +0x14
        *SIGNATURE,              # +08  never executed
        0xE24DD014,              # +14  sub  sp, sp, #0x14
        0xE1A0A000,              # +18  mov  sl, r0                sl = out
        0xE1A02001,              # +1C  mov  r2, r1                r2 = archiveId (9 = SDMC)
        0xE3A03001,              # +20  mov  r3, #1                r3 = PATH_EMPTY
        0xE59F9024,              # +24  ldr  sb, [pc, #0x24]       sb = nn::fs globals
        0xE3A04000,              # +28  mov  r4, #0
        0xE58D4010,              # +2C  str  r4, [sp, #0x10]       empty path = one NUL byte
        0xE28D4010,              # +30  add  r4, sp, #0x10
        0xE3A05001,              # +34  mov  r5, #1
        0xE88D0030,              # +38  stm  sp, {r4, r5}          stack args: path, size
        0xE28D1008,              # +3C  add  r1, sp, #8            out: archive handle
        0xE2890010,              # +40  add  r0, sb, #0x10         &fs:USER session handle
        _bl(s + 0x44, patch["open_archive"]),  # +44  bl FSUSER_OpenArchive wrapper
        0xE1A08000,              # +48  mov  r8, r0                the tail reads the result in r8
        _b(s + 0x4C, patch["mount_tail"]),     # +4C  b  shared mount tail
        globals_value,           # +50  literal
    ]


STUB_VARIANTS = {
    "r4_frame28": _stub_r4_frame28,
    "sl_frame14": _stub_sl_frame14,
}


def build_stub(patch: dict, globals_value: int) -> bytes:
    """Assemble the replacement fsMountArchive. See the module docstring for the layout."""
    words = STUB_VARIANTS[patch["variant"]](patch, globals_value)
    return b"".join(struct.pack("<I", w) for w in words)


def make_ips(records: list[tuple[int, bytes]]) -> bytes:
    out = bytearray(b"PATCH")
    for offset, data in records:
        if not 0 <= offset < 0x1000000 or not 0 < len(data) < 0x10000:
            raise ValueError(f"record at 0x{offset:X} ({len(data)} bytes) is out of IPS range")
        out += bytes(((offset >> 16) & 0xFF, (offset >> 8) & 0xFF, offset & 0xFF))
        out += bytes(((len(data) >> 8) & 0xFF, len(data) & 0xFF))
        out += data
    return bytes(out + b"EOF")


def patch_exheader(tid: str, exheader: bytes) -> bytes:
    """Grant DirectSdmc, and widen text.size when the stub lives in the .text padding.

    Without DirectSdmc, FS refuses to open ARCHIVE_SDMC for the title. The text.size bump
    only ever rounds up to the page boundary the section already occupies, so it changes
    nothing about the layout - it only brings the padding inside the range Luma scans.
    """
    patch = HOOK_PATCHES[tid.upper()]
    out = bytearray(exheader)

    access = struct.unpack_from("<Q", out, ACCESS_INFO_OFFSET)[0]
    struct.pack_into("<Q", out, ACCESS_INFO_OFFSET, access | (1 << DIRECT_SDMC_BIT))

    override = patch.get("text_size_override")
    if override is not None:
        current = struct.unpack_from("<I", out, TEXT_SIZE_OFFSET)[0]
        if override < current or (override + 0xFFF) >> 12 != (current + 0xFFF) >> 12:
            raise RuntimeError(
                f"text.size override 0x{override:X} changes the page count of 0x{current:X} "
                f"- that would move .rodata and .data and corrupt the title"
            )
        struct.pack_into("<I", out, TEXT_SIZE_OFFSET, override)

    return bytes(out)


def patched_code(tid: str, code: bytes) -> bytes:
    """The title's .code as the loader sees it after applying our code.ips."""
    patch = HOOK_PATCHES[tid.upper()]
    globals_value = struct.unpack_from("<I", code, patch["globals_off"])[0]
    stub = build_stub(patch, globals_value)
    out = bytearray(code)
    out[patch["stub_off"]:patch["stub_off"] + len(stub)] = stub
    return bytes(out)


def _verify(patch: dict, code: bytes, stub: bytes) -> None:
    """Re-run Luma's own symbol search over the patched code and demand our stub wins."""
    from layeredfs_check import find_symbols  # imported late: layeredfs_check imports build

    patched = bytearray(code)
    patched[patch["stub_off"]:patch["stub_off"] + len(stub)] = stub
    symbols = find_symbols(bytes(patched), min(patch["text_size"], len(patched)))
    found = symbols["fsMountArchive"]
    if found != patch["stub_off"]:
        raise RuntimeError(
            f"stub is not what Luma would resolve: fsMountArchive -> "
            f"{'0x%X' % found if found is not None else 'NOT FOUND'}, expected 0x{patch['stub_off']:X}"
        )
    missing = [name for name, off in symbols.items() if off is None and name != "fsUnmountArchive"]
    if missing:
        raise RuntimeError(f"other LayeredFS symbols are missing: {', '.join(missing)}")


def generate(tid: str, code_path: Path, exheader_path: Path) -> tuple[dict[str, bytes], list[str]]:
    """Return {filename: contents} for the title's code.ips and exheader.bin, plus a log."""
    patch = dict(HOOK_PATCHES[tid.upper()])

    exheader = exheader_path.read_bytes()

    # Version first, sha256 second: the version says *which* build this is in terms a
    # person can act on, the hash says whether it is byte-for-byte the one measured.
    version = struct.unpack_from("<H", exheader, REMASTER_VERSION_OFFSET)[0]
    if version != patch["title_version"]:
        raise RuntimeError(
            f"{exheader_path} is title version {version}, the offsets were derived from "
            f"version {patch['title_version']} of {patch['title']}\n"
            f"  the patch cannot be used on this build - re-derive the offsets from this dump"
        )

    code = code_path.read_bytes()
    digest = hashlib.sha256(code).hexdigest()
    if digest != patch["code_sha256"]:
        raise RuntimeError(
            f"{code_path} reports title version {version} but does not match the dump the "
            f"offsets were derived from\n"
            f"  expected sha256 {patch['code_sha256']}\n"
            f"  got             {digest}\n"
            f"  re-derive the offsets before building"
        )

    globals_value = struct.unpack_from("<I", code, patch["globals_off"])[0]
    stub = build_stub(patch, globals_value)
    if len(stub) > patch["stub_room"]:
        raise RuntimeError(f"stub is {len(stub)} bytes, only {patch['stub_room']} are free")

    # Verify against the exheader we are about to ship, not the original: the scan range
    # is text.size, and for a stub in the .text padding that is the widened value.
    new_exheader = patch_exheader(tid, exheader)
    patch["text_size"] = struct.unpack_from("<I", new_exheader, TEXT_SIZE_OFFSET)[0]
    _verify(patch, code, stub)

    files = {
        "code.ips": make_ips([(patch["stub_off"], stub)]),
        "exheader.bin": new_exheader,
    }
    widened = patch.get("text_size_override")
    log = [
        f"{patch['title']} title version {version}",
        f"code.ips: {len(stub)}-byte fsMountArchive at 0x{patch['stub_off']:X} "
        f"(va 0x{TEXT_VA + patch['stub_off']:X}), verified against Luma's symbol search",
        "exheader.bin: DirectSdmc granted"
        + (f", text.size 0x{struct.unpack_from('<I', exheader, TEXT_SIZE_OFFSET)[0]:X} -> "
           f"0x{widened:X} (same {(widened + 0xFFF) >> 12}-page mapping)" if widened else ""),
    ]
    return files, log
