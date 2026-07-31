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
    # Friend List (friend), EUR, title version 6.
    #
    # Same shape as the Activity Log - no fsMountArchive, no DirectSdmc - but the stub uses
    # the Manual's tighter variant, because this title has a mount function whose tail takes
    # the result in r8 with `out` in sl on a 0x14 frame: MountSystemSaveData() at 0x4F58C,
    # whose OpenArchive retry loop ends at 0x4F634. All three of this title's mount functions
    # build the same archive object (vtable 0x201E4C), so any of their tails would do.
    #
    # The stub goes over throwFatalError(): the .text padding is 2724 bytes, far more than
    # the 0x114 Luma needs for its own payload, so Luma takes the padding and leaves this
    # function alone. No text.size override is needed - throwFatalError() is well inside the
    # range findLayeredFsSymbols() scans.
    "0004003000009F02": {
        "title": "Friend List (friend) EUR",
        "title_version": 6,
        "code_sha256": "a5d86ac04922f63feb0c3cfcc8390867f358ba8b3a3970acb211be7b8d9f923e",
        "variant": "sl_frame14",
        "stub_off": 0x78904,     # throwFatalError(), which Luma leaves alone here
        "stub_room": 284,        # bytes until the next function's `push`
        "open_archive": 0x6E41C,  # the title's own FSUSER_OpenArchive IPC wrapper
        "mount_tail": 0x4F634,   # tail of MountSystemSaveData(), entered with r8 = result
        "globals_off": 0x4F6AC,  # literal holding the nn::fs globals base (+0x10 = fs:USER session)
    },
    # Download Play (dlplay), EUR, title version 3.
    #
    # A different mechanism entirely - see ROMFS_FROM_SD below. This title cannot issue
    # FSUSER_OpenArchive at all (its whole fs:USER vocabulary is OpenFileDirectly plus the
    # FSFile sub-session), so there is nothing for a mount stub to call. Instead the two
    # places where it opens its own RomFS are pointed at an image on the SD card.
    #
    # No romfs/ folder ships for this title, so checkLumaDir() finds nothing,
    # patchLayeredFs() returns early and the loader never touches the code.
    "0004001000022100": {
        "title": "Download Play (dlplay) EUR",
        "title_version": 3,
        "code_sha256": "78eeb084a69f2ca509626735493d9c87fa23e7cc7e327044a8e197fd3c3051e9",
        "kind": "romfs_from_sd",
        "image_name": "dlplay_romfs.bin",
        "stub_off": 0x922E8,        # .text page padding; Luma has no use for it here
        "stub_room": 3352,
        # Both sites open ARCHIVE_ROMFS the same way. 0x14D3C feeds the archive registered
        # as "rom:", 0xDD24 is a second, independent reader of the same data - redirecting
        # only one would leave two readers on two images with different internal offsets.
        "sites": [
            {"patch_at": 0x14DD4, "return_to": 0x14DD8},
            {"patch_at": 0x0DD7C, "return_to": 0x0DD80},
        ],
    },
    # Software Keyboard (swkbd), EUR, title version 4. Same shape as Download Play.
    #
    # It has a third OpenFileDirectly call site at 0x6F7C0, but that one opens
    # ARCHIVE_SAVEDATA_AND_CONTENT (0x2345678A), not the RomFS - it is left alone.
    "000400300000D002": {
        "title": "Software Keyboard (swkbd) EUR",
        "title_version": 4,
        "code_sha256": "a0b78005b0a99116ca703bc9b7625ce1b0f2d4cc45f66fc6fb9ab8a34244d4f0",
        "kind": "romfs_from_sd",
        "image_name": "swkbd_romfs.bin",
        "stub_off": 0x9F074,        # .text page padding
        "stub_room": 3980,
        # 0x14944 feeds the archive registered as "rom:", 0xE958 is the second reader.
        "sites": [
            {"patch_at": 0x14944, "return_to": 0x14948},
            {"patch_at": 0x0E958, "return_to": 0x0E95C},
        ],
    },
}

# Stack layout the OpenFileDirectly wrapper reads its arguments from, shared by both sites.
FILE_PATH_TYPE_SLOT = 0x0C
FILE_PATH_PTR_SLOT = 0x10
FILE_PATH_SIZE_SLOT = 0x14
ARCHIVE_SDMC = 9
PATH_ASCII = 3
ORIGINAL_SITE_WORD = 0xE3A03003  # mov r3, #3  -> the ARCHIVE_ROMFS each site starts from


# GodMode9 names its output after the title and the mounted image, not after what the file
# is, so a dump legitimately arrives as `0004003000009F02.dec.code` + `extheader.bin` or as
# `code.bin` + `exthdr.bin`. Every tool resolves both through find_dump().
CODE_NAMES = ("code.bin", "code.dec.bin", ".code")
CODE_PATTERNS = ("*.code",)
EXHEADER_NAMES = ("exheader.bin", "exthdr.bin", "extheader.bin")
EXHEADER_PATTERNS = ("*.exthdr", "*exth*.bin")


def find_dump(title_dir: Path, names: tuple[str, ...], patterns: tuple[str, ...]) -> Path | None:
    """The first file in `title_dir` matching one of the accepted names, else None."""
    for name in names:
        candidate = title_dir / name
        if candidate.is_file():
            return candidate
    for pattern in patterns:
        matches = sorted(title_dir.glob(pattern))
        if matches:
            return matches[0]
    return None


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


def kind(tid: str) -> str:
    return HOOK_PATCHES[tid.upper()].get("kind", "mount_stub")


def _redirect_records(patch: dict, path_va: int, path_off: int, sd_path: str) -> list[tuple[int, bytes]]:
    """IPS records that make every ARCHIVE_ROMFS open read an image off the SD card.

    Each site is `mov r3, #3` immediately before the OpenFileDirectly call, with the file
    path already laid out on the stack. The site branches to a stub that swaps in
    ARCHIVE_SDMC and an ASCII path, then branches back to the next instruction.
    """
    encoded = sd_path.encode("ascii") + b"\0"
    records: list[tuple[int, bytes]] = [(path_off, encoded)]
    stub_at = patch["stub_off"]

    for site in patch["sites"]:
        words = [
            0xE3A03000 | ARCHIVE_SDMC,                    # +00  mov r3, #9
            0xE3A01000 | PATH_ASCII,                      # +04  mov r1, #3    PATH_ASCII
            0xE58D1000 | FILE_PATH_TYPE_SLOT,             # +08  str r1, [sp, #0xc]
            0xE59F100C,                                   # +0C  ldr r1, [pc, #0xc]
            0xE58D1000 | FILE_PATH_PTR_SLOT,              # +10  str r1, [sp, #0x10]
            0xE3A01000 | len(encoded),                    # +14  mov r1, #len (with the NUL)
            0xE58D1000 | FILE_PATH_SIZE_SLOT,             # +18  str r1, [sp, #0x14]
            _b(stub_at + 0x1C, site["return_to"]),        # +1C  b  back to the call setup
            path_va,                                      # +20  literal
        ]
        records.append((stub_at, b"".join(struct.pack("<I", w) for w in words)))
        records.append((site["patch_at"], struct.pack("<I", _b(site["patch_at"], stub_at))))
        stub_at += len(words) * 4

    used = stub_at - patch["stub_off"]
    if used > patch["stub_room"]:
        raise RuntimeError(f"stubs need {used} bytes, only {patch['stub_room']} are free")
    return records


def patched_code(tid: str, code: bytes) -> bytes:
    """The title's .code as the loader sees it after applying our code.ips."""
    patch = HOOK_PATCHES[tid.upper()]
    if patch.get("kind") == "romfs_from_sd":
        return code  # nothing here changes what Luma's symbol search would find
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


def _branch_target(word: int, at: int) -> int | None:
    """Where an unconditional `b` at .text offset `at` lands, or None if it is not one."""
    if word >> 24 != 0xEA:
        return None
    offset = word & 0xFFFFFF
    if offset & 0x800000:
        offset -= 0x1000000
    return at + 8 + offset * 4


def _verify_redirect(
    patch: dict, code: bytes, records: list[tuple[int, bytes]], path_va: int, sd_path: str
) -> None:
    """Apply the records and walk the result: each site must reach a stub and come back."""
    patched = bytearray(code)
    for offset, data in records:
        patched[offset:offset + len(data)] = data

    word = lambda off: struct.unpack_from("<I", patched, off)[0]  # noqa: E731

    for site in patch["sites"]:
        stub = _branch_target(word(site["patch_at"]), site["patch_at"])
        if stub is None or not patch["stub_off"] <= stub < patch["stub_off"] + patch["stub_room"]:
            raise RuntimeError(f"site 0x{site['patch_at']:X} does not branch into the stub area")
        if word(stub) != (0xE3A03000 | ARCHIVE_SDMC):
            raise RuntimeError(f"stub at 0x{stub:X} does not start by selecting ARCHIVE_SDMC")
        back = _branch_target(word(stub + 0x1C), stub + 0x1C)
        if back != site["return_to"]:
            raise RuntimeError(
                f"stub at 0x{stub:X} returns to 0x{back:X}, expected 0x{site['return_to']:X}"
            )
        if word(stub + 0x20) != path_va:
            raise RuntimeError(f"stub at 0x{stub:X} does not point at the path string")

    encoded = sd_path.encode("ascii") + b"\0"
    path_off = next(off for off, data in records if data == encoded)
    if bytes(patched[path_off:path_off + len(encoded)]) != encoded:
        raise RuntimeError("the path string did not land where the stubs point")


def sd_path_for(tid: str) -> str:
    return f"/luma/titles/{tid.upper()}/{HOOK_PATCHES[tid.upper()]['image_name']}"


def _generate_romfs_from_sd(
    tid: str, patch: dict, code: bytes, exheader: bytes, version: int
) -> tuple[dict[str, bytes], list[str]]:
    for site in patch["sites"]:
        word = struct.unpack_from("<I", code, site["patch_at"])[0]
        if word != ORIGINAL_SITE_WORD:
            raise RuntimeError(
                f"0x{site['patch_at']:X} holds 0x{word:08X}, expected 0x{ORIGINAL_SITE_WORD:08X} "
                f"(mov r3, #3) - this is not the ARCHIVE_ROMFS open the offsets were taken from"
            )

    # The path string goes in the .rodata page padding. Sections sit at page-aligned
    # offsets inside .code, so its file offset and its address both follow from the sizes.
    text_size = struct.unpack_from("<I", exheader, TEXT_SIZE_OFFSET)[0]
    ro_address = struct.unpack_from("<I", exheader, 0x20)[0]
    ro_size = struct.unpack_from("<I", exheader, 0x28)[0]
    rounded = lambda v: (v + 0xFFF) & ~0xFFF  # noqa: E731
    sd_path = sd_path_for(tid)
    room = rounded(ro_size) - ro_size
    if len(sd_path) + 1 > room:
        raise RuntimeError(f"path needs {len(sd_path) + 1} bytes, .rodata padding has {room}")

    path_va = ro_address + ro_size
    records = _redirect_records(patch, path_va, rounded(text_size) + ro_size, sd_path)
    _verify_redirect(patch, code, records, path_va, sd_path)
    files = {"code.ips": make_ips(records), "exheader.bin": patch_exheader(tid, exheader)}
    log = [
        f"{patch['title']} title version {version}",
        f"code.ips: {len(patch['sites'])} ARCHIVE_ROMFS opens redirected to ARCHIVE_SDMC, "
        f"stubs at 0x{patch['stub_off']:X} (va 0x{TEXT_VA + patch['stub_off']:X})",
        f"code.ips: path {sd_path!r} at va 0x{ro_address + ro_size:X} "
        f"({room} bytes of .rodata padding available)",
        "exheader.bin: DirectSdmc granted",
    ]
    return files, log


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

    if patch.get("kind") == "romfs_from_sd":
        return _generate_romfs_from_sd(tid, patch, code, exheader, version)

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
