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

import smdh_names

TEXT_VA = 0x100000

# Exheader offsets: remaster version sits in the code set info, access info in the ARM11
# local system capabilities block.
REMASTER_VERSION_OFFSET = 0x0E
TEXT_SIZE_OFFSET = 0x18
BSS_SIZE_OFFSET = 0x3C
ACCESS_INFO_OFFSET = 0x248
DIRECT_SDMC_BIT = 7

# Luma writes its own LayeredFS payload into the .text padding whenever the padding is big
# enough for it, so a stub that shares that padding has to stay out of its way. It puts the
# payload at the *front* (`*payloadOffset = size` in findLayeredFsPayloadOffset), which is
# why the stub goes at the end.
LUMA_PAYLOAD_SIZE = 0x114

# The same function claims the front of the .rodata padding for its path string:
#
#     if(roundedRoSize - roSize >= 39) *pathOffset = roundedTextSize + roSize;
#     ...
#     memcpy(code + pathOffset, "lf:", 3);
#     memcpy(code + pathOffset + 3, path, sizeof(path));   // "/luma/titles/<16>/romfs"
#
# 39 bytes, and Luma writes them after the IPS is applied, so anything of ours that starts
# there is silently overwritten. Rounded up to a word, with a margin.
LUMA_PATH_SIZE = 48

# How much room the pane hook has when it composes a replacement plus the original's tail.
# Names are a few dozen code units; this only bounds a runaway string.
PANE_SCRATCH_UNITS = 0x100
# The buffer itself plus its terminator, rounded to a word - what .bss grows by.
PANE_SCRATCH_BYTES = (2 * PANE_SCRATCH_UNITS + 2 + 3) & ~3

# The first instruction of each HOME Menu function the branches replace.
ORIGINAL_THUNK_WORD = 0xE92D4008  # push {r3, lr}
ORIGINAL_CACHE_WORD = 0xE92D4FF0  # push {r4-r8, sb, sl, fp, lr}

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
        # This title cannot be fixed the way the HOME Menu was: it never reads an SMDH, it is
        # handed finished strings. So the application names are swapped at the one text
        # setter every string goes through - see _pane_hook().
        "pane_hook": {
            # One level below SetPaneText(): 8 call sites in three functions reach it, and
            # SetPaneText() is only one of them. The software card sets its panes through
            # another of the three, which is why hooking SetPaneText() left it in Russian.
            "set_text_off": 0x7BC28,      # SetText(window, text, pane, ...)
            "original_word": 0xE92D47F0,  # push {r4-r8, sb, sl, lr}
        },
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
    # Health & Safety Information (safe), EUR, title version 3. Same shape as Download Play:
    # its only fs:USER call is OpenFileDirectly (the wrapper at 0x21A18), there is no
    # FSUSER_OpenArchive anywhere in .text, so a mount stub would have nothing to call.
    #
    # Both ARCHIVE_ROMFS opens go through that one wrapper, and at both sites the file path
    # is already on the stack in the slots the redirect stub rewrites (type at sp+0xC as
    # `mov r3, #2` / `mov r1, #2`, pointer at sp+0x10, size 0xC at sp+0x14).
    "0004001000022300": {
        "title": "Health & Safety Information (safe) EUR",
        "title_version": 3,
        "code_sha256": "74c813cc1f00a67c06ad85e10723b1440949b2d448e2e1f5532d2a61fb57600c",
        "kind": "romfs_from_sd",
        "image_name": "safe_romfs.bin",
        "stub_off": 0x63A94,        # .text page padding, 0x63A94..0x64000
        "stub_room": 1388,
        "sites": [
            {"patch_at": 0x0A800, "return_to": 0x0A804},
            {"patch_at": 0x11234, "return_to": 0x11238},
        ],
    },
    # HOME Menu (Nintendo 3DS HOME Menu), EUR, title version 29.
    #
    # A different job from every other entry here: LayeredFS already works for this title
    # unaided, and this patch is about the application names HOME Menu displays. It reads
    # them from each title's SMDH - ExeFS:/icon in NAND, which LayeredFS cannot replace -
    # so instead the read itself is hooked. See SMDH_NAMES below.
    #
    # ReadTitleIcon() at 0xEA40 builds the ARCHIVE_SAVEDATA_AND_CONTENT path from the title
    # id and pulls all 0x36C0 bytes of the SMDH into the caller's buffer. It has exactly one
    # caller, the thunk at 0x131E60, which in turn has 18 - every screen that shows a name
    # goes through it, which is why one hook is enough.
    #
    # Registers at the thunk: r0 = buffer, r1 = mediatype, r2/r3 = title id. Confirmed at
    # two call sites: 0x120ABC (`ldrd r2, r3, [r4, #8]`, `ldrb r1, [r4, #0x10]`) and
    # 0xBB5EC (`mov r1, #1`, i.e. NAND). Success is a zero return - the failure paths hand
    # back 0xC8804631/0xC8804632 or the raw negative result.
    #
    # The stub sits at the *end* of the .text padding on purpose: the padding is 2548 bytes,
    # so Luma claims its front for the 0x114-byte LayeredFS payload, and leaving that front
    # untouched keeps both patches out of each other's way.
    "0004003000009802": {
        "title": "HOME Menu EUR",
        "title_version": 29,
        "code_sha256": "5f4d8d0e80d8e7d6fafcefa0630c5106473ade4658585cfb499a6ec3324d89a7",
        "kind": "smdh_names",
        "thunk_off": 0x131E60,     # the one caller of ReadTitleIcon(), itself called 18 times
        "reader_off": 0xEA40,      # ReadTitleIcon(buffer, mediatype, tid_lo, tid_hi)
        "cache_read_off": 0x147D64,  # CacheRead(cache, key, buffer) -> bool, out of Cache.dat
        "lang_index": 10,          # the SMDH language slot the mod overwrites: EU_Russian
        # The picture on the upper screen comes from the highlighted title's own
        # ExeFS:/banner, which HOME Menu opens itself - see docs/banner-ua.md. The open is
        # shared by every title, so the hook compares the title id first and only swaps the
        # System Settings one for a file on the SD card.
        "banner_hook": {
            "open_off": 0x61DE4,   # OpenTitleBanner(out, mediatype, tid_lo, tid_hi)
            "site_off": 0x61E64,   # `ldr r3, [pc, #0xb4]` - the archive id, last arg set
            "original_word": 0xE59F30B4,
            "return_to": 0x61E68,
            "title_id_slot": 0x38,  # `strd r2, r3, [sp, #0x38]` at the top of the open
            "titles": [
                {"title_id": 0x0004001000022000, "image_name": "banner_22000.bin"},
                {"title_id": 0x0004001000022200, "image_name": "banner_22200.bin"},
            ],
        },
    },
    # StreetPass Mii Plaza (MEET), EUR, title version 5. Verified working on hardware.
    #
    # The odd one out: Luma finds every symbol it needs in this title's own code, so no
    # stub is required - but its accessInfo is 0x0, without `DirectSdmc`, and the payload
    # Luma writes still has to open ARCHIVE_SDMC to read the replacement files. Every other
    # title Luma hooks unaided (HOME Menu, Mii Maker, Camera, Sound) already has that bit.
    # So this entry ships an exheader and nothing else - no code.ips, no offsets, and
    # therefore nothing tied to the build beyond the version check.
    "0004001000022800": {
        "title": "StreetPass Mii Plaza (MEET) EUR",
        "title_version": 5,
        "code_sha256": "2834311201bb3756ae8646a5046300b75d00a0f4b73509a79cd30ea5788f314f",
        "kind": "exheader_only",
    },
    # Mii Selector (appletEd), EUR, title version 3. Verified working on hardware.
    #
    # Same shape as the Friend List - no fsMountArchive, no DirectSdmc - but this title has
    # exactly one mount function, MountRomFs() at 0xD334, and it uses a 0x18 frame with
    # `out` in r4 and the nn::fs globals in r5. Hence the third stub variant. The branch
    # target is the result check at 0xD36C rather than the allocation that follows it, so a
    # failed OpenArchive still returns an error instead of building an archive object
    # around a garbage handle.
    #
    # The stub goes over throwFatalError(): the .text padding is 3048 bytes, far more than
    # the 0x114 Luma needs for its own payload, so Luma takes the padding and leaves this
    # function alone - no text.size override needed.
    "000400300000D102": {
        "title": "Mii Selector (appletEd) EUR",
        "title_version": 3,
        "code_sha256": "da40253f0e76ea840534816335176fece1e468419a5973221ea8e3c7ecfd259b",
        "variant": "r4_frame18",
        "stub_off": 0x94B4,      # throwFatalError(), which Luma leaves alone here
        "stub_room": 288,        # bytes until the next function's `push`
        "open_archive": 0x14030,  # the title's own FSUSER_OpenArchive IPC wrapper
        "mount_tail": 0xD36C,    # MountRomFs()'s result check, entered with r0 = result
        "globals_off": 0xD3D8,   # literal holding the nn::fs globals base (+0x10 = fs:USER session)
    },
    # Notifications (newslist), EUR, title version 4.
    #
    # Byte-for-byte the Mii Selector's shape: one mount function on a 0x18 frame with `out`
    # in r4 and the nn::fs globals in r5, so the same stub variant and the same choice of
    # branch target - the result check at 0xD... here 0x5A500, not the allocation after it.
    #
    # Stub over throwFatalError(): the .text padding is 2300 bytes, more than the 0x114
    # Luma needs, so Luma takes the padding and leaves the function alone.
    "000400300000A002": {
        "title": "Notifications (newslist) EUR",
        "title_version": 4,
        "code_sha256": "b3993f1e4fe5ed7e5760f0f4c3926c95b42ea8de53c25bb95864499342e5b228",
        "variant": "r4_frame18",
        "stub_off": 0x448F8,     # throwFatalError(), which Luma leaves alone here
        "stub_room": 424,        # bytes until the next function's `push`
        "open_archive": 0x5A5D8,  # the title's own FSUSER_OpenArchive IPC wrapper
        "mount_tail": 0x5A500,   # MountRomFs()'s result check, entered with r0 = result
        "globals_off": 0x5A56C,  # literal holding the nn::fs globals base (+0x10 = fs:USER session)
    },
    # Error applet (error), EUR, title version 7.
    #
    # This one has FSUSER_OpenArchive but no archive *object* anywhere: its mount path is a
    # retry loop that hands the raw handle to fsRegisterArchive, so there is no tail that
    # allocates the object Luma's payload expects. It goes the Download Play way instead -
    # its two ARCHIVE_ROMFS opens (0xBEA8 feeds the archive registered as "rom:", 0x11298
    # is the second reader) are pointed at an image on the SD card. Both sites lay the path
    # out in the slots the redirect stub rewrites: type 2 at sp+0xC, pointer at sp+0x10,
    # size 0xC at sp+0x14.
    "000400300000C502": {
        "title": "Error applet (error) EUR",
        "title_version": 7,
        "code_sha256": "940fad616707e1f1a943fe6a65dc9fa71fd193631d3f1db7d714b7f6dee26b46",
        "kind": "romfs_from_sd",
        "image_name": "error_romfs.bin",
        "stub_off": 0x55B8C,        # .text page padding, 0x55B8C..0x56000
        "stub_room": 1140,
        "sites": [
            {"patch_at": 0x0BEA8, "return_to": 0x0BEAC},
            {"patch_at": 0x11298, "return_to": 0x1129C},
        ],
    },
    # amiibo Settings (Cabinet), EUR, title version 1. Same shape as the Mii Selector and
    # Notifications: one mount function on a 0x18 frame, `out` in r4, globals in r5, and the
    # stub branches to its result check at 0x3D344 rather than the allocation after it.
    #
    # Stub over throwFatalError(): the .text padding is 968 bytes, more than the 0x114 Luma
    # needs, so Luma takes the padding and leaves the function alone.
    "000400300000B902": {
        "title": "amiibo Settings (Cabinet) EUR",
        "title_version": 1,
        "code_sha256": "316c8a1cb37c2aab7813a5546f355ab0bdd3f635fe56b606abf91bb191a1d2d9",
        "variant": "r4_frame18",
        "stub_off": 0x122A8,     # throwFatalError(), which Luma leaves alone here
        "stub_room": 284,        # bytes until the next function's `push`
        "open_archive": 0x4F5EC,  # the title's own FSUSER_OpenArchive IPC wrapper
        "mount_tail": 0x3D344,   # MountRomFs()'s result check, entered with r0 = result
        "globals_off": 0x3D3B0,  # literal holding the nn::fs globals base (+0x10 = fs:USER session)
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
PATH_EMPTY = 1
ORIGINAL_SITE_WORD = 0xE3A03003  # mov r3, #3  -> the ARCHIVE_ROMFS each site starts from

# The banner open sets an archive path too, which the romfs sites above do not: theirs is
# already empty, this one carries the title id, and ARCHIVE_SDMC wants it empty.
ARCHIVE_PATH_TYPE_SLOT = 0x00
ARCHIVE_PATH_PTR_SLOT = 0x04
ARCHIVE_PATH_SIZE_SLOT = 0x08
ARCHIVE_SAVEDATA_AND_CONTENT = 0x2345678A


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


COND_EQ, COND_NE = 0x0, 0x1


def _bc(cond: int, src: int, dst: int) -> int:
    return (cond << 28) | 0x0A000000 | (((dst - src - 8) >> 2) & 0xFFFFFF)


def _imm12(value: int) -> int:
    """Encode a data-processing immediate: an 8-bit value rotated right by an even amount."""
    for rot in range(16):
        shift = 2 * rot
        rotated = value if shift == 0 else ((value << shift) | (value >> (32 - shift))) & 0xFFFFFFFF
        if rotated <= 0xFF:
            return (rot << 8) | rotated
    raise ValueError(f"0x{value:X} is not an ARM immediate")


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


def _stub_r4_frame18(patch: dict, globals_value: int) -> list[int]:
    """Tail takes the result in r0, `out` in r4, globals in r5, on a 0x18 frame.

    The 0x18 frame leaves exactly one free word (sp+0x14) once the two stack arguments,
    the archive handle and the session handle have their slots, so the empty path goes
    there.
    """
    s = patch["stub_off"]
    return [
        0xE92D41F0,              # +00  push {r4,r5,r6,r7,r8,lr}  <- findFunctionStart lands here
        _b(s + 0x04, s + 0x18),  # +04  b    +0x18                 skips the signature block
        *SIGNATURE,              # +08  never executed
        0xE1A00000,              # +14  nop
        0xE24DD018,              # +18  sub  sp, sp, #0x18         the frame mount_tail expects
        0xE1A04000,              # +1C  mov  r4, r0                r4 = out
        0xE1A02001,              # +20  mov  r2, r1                r2 = archiveId (9 = SDMC)
        0xE3A03001,              # +24  mov  r3, #1                r3 = PATH_EMPTY
        0xE3A00000,              # +28  mov  r0, #0
        0xE58D0014,              # +2C  str  r0, [sp, #0x14]       empty path = one NUL byte
        0xE28D0014,              # +30  add  r0, sp, #0x14
        0xE58D0000,              # +34  str  r0, [sp]              stack arg: path pointer
        0xE3A00001,              # +38  mov  r0, #1
        0xE58D0004,              # +3C  str  r0, [sp, #4]          stack arg: path size
        0xE59F5014,              # +40  ldr  r5, [pc, #0x14]       r5 = nn::fs globals
        0xE5950010,              # +44  ldr  r0, [r5, #0x10]       fs:USER session handle
        0xE58D0010,              # +48  str  r0, [sp, #0x10]
        0xE28D1008,              # +4C  add  r1, sp, #8            out: archive handle
        0xE28D0010,              # +50  add  r0, sp, #0x10
        _bl(s + 0x54, patch["open_archive"]),  # +54  bl FSUSER_OpenArchive wrapper
        _b(s + 0x58, patch["mount_tail"]),     # +58  b  shared mount tail
        globals_value,           # +5C  literal
    ]


STUB_VARIANTS = {
    "r4_frame28": _stub_r4_frame28,
    "r4_frame18": _stub_r4_frame18,
    "sl_frame14": _stub_sl_frame14,
}


def _pane_hook(patch: dict, table_va: int, scratch_va: int, base: int) -> tuple[list[int], dict[str, int]]:
    """Swap the text argument of the title's string setter for a name we have a translation for.

    Entered in place of the setter's own prologue, so the incoming registers are the caller's,
    with r1 = the text. Two shapes of match, because the same string reaches the setter both
    on its own and with a second line appended - the software card draws the name and the
    publisher as one string:

        "Журнал действий"           -> r1 points at our replacement, nothing is copied
        "Журнал действий\nNintendo" -> replacement and the tail are composed into scratch

    A partial match is not a match: the candidate has to end, or break the line, exactly
    where the original does. The whole interface goes through this function, so anything
    looser would corrupt unrelated strings.

    Falls through into the prologue it replaced and then back into the setter, so there is no
    return path to arrange.
    """
    hook = patch["pane_hook"]

    def b(target: str):
        return lambda at, labels: _b(at, labels[target])

    def bc(cond: int, target: str):
        return lambda at, labels: _bc(cond, at, labels[target])

    def ldr_pc(reg: int, target: str):
        return lambda at, labels: 0xE59F0000 | (reg << 12) | (labels[target] - at - 8)

    blocks = {
        "pane_hook": [
            0xE92D403D,                          # push  {r0, r2, r3, r4, r5, lr}
            0xE3510000,                          # cmp   r1, #0
            bc(COND_EQ, "pane_out"),             # beq   pane_out           nothing to compare
            ldr_pc(3, "pane_table"),             # ldr   r3, [pc, #...]
        ],
        "pane_loop": [
            0xE1D300B0,                          # ldrh  r0, [r3]           length of the original
            0xE3500000,                          # cmp   r0, #0
            bc(COND_EQ, "pane_out"),             # beq   pane_out           end of table
            0xE2834004,                          # add   r4, r3, #4         the original
            0xE1A05001,                          # mov   r5, r1             the candidate
        ],
        "pane_cmp": [
            0xE0D420B2,                          # ldrh  r2, [r4], #2
            0xE0D5C0B2,                          # ldrh  ip, [r5], #2
            0xE152000C,                          # cmp   r2, ip
            bc(COND_EQ, "pane_same"),            # beq   pane_same
            # A space in the table also matches a line break, so the originals can be
            # written on one line without knowing where Nintendo broke them.
            0xE3520020,                          # cmp   r2, #0x20
            bc(COND_NE, "pane_next"),            # bne   pane_next
            0xE35C000A,                          # cmp   ip, #0xa
            bc(COND_NE, "pane_next"),            # bne   pane_next
        ],
        "pane_same": [
            0xE2500001,                          # subs  r0, r0, #1
            bc(COND_NE, "pane_cmp"),             # bne   pane_cmp
            # r4 -> the replacement, r5 -> whatever follows the matched text
            0xE1D5C0B0,                          # ldrh  ip, [r5]
            0xE35C0000,                          # cmp   ip, #0
            0x01A01004,                          # moveq r1, r4             an exact match
            bc(COND_EQ, "pane_out"),             # beq   pane_out
            0xE35C000A,                          # cmp   ip, #0xa           a line break
            bc(COND_NE, "pane_next"),            # bne   pane_next
        ],
        # Compose the replacement plus the tail into our own buffer. The limit is on top of
        # the exact-match path, which never copies at all, so it only bounds this one.
        "pane_join": [
            ldr_pc(0, "pane_scratch"),           # ldr   r0, [pc, #...]
            0xE1A01000,                          # mov   r1, r0             the swapped pointer
            0xE3A03C01,                          # mov   r3, #0x100         code units of room
        ],
        "pane_head": [
            0xE0D420B2,                          # ldrh  r2, [r4], #2
            0xE3520000,                          # cmp   r2, #0
            bc(COND_EQ, "pane_tail"),            # beq   pane_tail
            0xE0C020B2,                          # strh  r2, [r0], #2
            0xE2533001,                          # subs  r3, r3, #1
            bc(COND_NE, "pane_head"),            # bne   pane_head
            b("pane_trunc"),                     # b     pane_trunc
        ],
        "pane_tail": [
            0xE0D520B2,                          # ldrh  r2, [r5], #2
            0xE0C020B2,                          # strh  r2, [r0], #2
            0xE3520000,                          # cmp   r2, #0
            bc(COND_EQ, "pane_out"),             # beq   pane_out           the NUL is copied too
            0xE2533001,                          # subs  r3, r3, #1
            bc(COND_NE, "pane_tail"),            # bne   pane_tail
        ],
        "pane_trunc": [
            0xE3A02000,                          # mov   r2, #0
            0xE1C020B0,                          # strh  r2, [r0]
            b("pane_out"),                       # b     pane_out
        ],
        "pane_next": [
            0xE1D300B0,                          # ldrh  r0, [r3]           original length
            0xE1D320B2,                          # ldrh  r2, [r3, #2]       replacement length
            0xE0833080,                          # add   r3, r3, r0, lsl #1
            0xE0833082,                          # add   r3, r3, r2, lsl #1
            0xE2833004,                          # add   r3, r3, #4
            b("pane_loop"),                      # b     pane_loop
        ],
        "pane_out": [
            0xE8BD403D,                          # pop   {r0, r2, r3, r4, r5, lr}
            hook["original_word"],               # the setter's own prologue
            lambda at, labels: _b(at, hook["set_text_off"] + 4),
        ],
        "pane_table": [
            table_va,                            # literal
        ],
        "pane_scratch": [
            scratch_va,                          # literal
        ],
    }
    return _assemble(blocks, base)


def _banner_hook(patch: dict, entries: list[dict], base: int) -> tuple[list[int], dict[str, int]]:
    """Point the banners we translate at the SD card, and leave every other title alone.

    HOME Menu builds the whole FSUSER_OpenFileDirectly frame for ExeFS:/banner itself:
    archive 0x2345678A with the title id as a binary archive path, and a binary file path
    naming the ExeFS section. The last thing it does before the call is load the archive id,
    and that instruction is what the hook replaces - by then the frame is complete and only
    r0, r1 and r3 are still to be written, so r1, r3 and ip are free scratch here. r2 is not:
    it is already the wrapper's third argument.

    The hook walks a table of {title id, path, length}, one entry per banner we ship. On a
    match the frame is rewritten into an SD open: empty archive path (what ARCHIVE_SDMC
    expects), ASCII file path, archive id 9. Everything else falls through to `pass`, which
    loads the archive id the replaced instruction would have loaded, so those reads behave
    exactly as Nintendo wrote them.

    The title id is read back out of the frame rather than kept in a register, because the
    open stores it there on entry (`strd r2, r3, [sp, #0x38]`) and never touches it again.
    """
    hook = patch["banner_hook"]
    slot = hook["title_id_slot"]

    def b(target: str):
        return lambda at, labels: _b(at, labels[target])

    def bc(cond: int, target: str):
        return lambda at, labels: _bc(cond, at, labels[target])

    table: list[int] = []
    for entry in entries:
        table += [
            entry["title_id"] & 0xFFFFFFFF,
            entry["title_id"] >> 32,
            entry["path_va"],
            entry["path_len"],
        ]
    table.append(0)  # a zero title id ends the walk

    blocks = {
        "banner_hook": [
            lambda at, labels: 0xE59FC000 | (labels["banner_table"] - at - 8),  # ldr ip, table
        ],
        "banner_loop": [
            0xE59C3000,                               # ldr   r3, [ip]        entry title id
            0xE3530000,                               # cmp   r3, #0
            bc(COND_EQ, "banner_pass"),               # beq   pass            end of table
            0xE59D1000 | slot,                        # ldr   r1, [sp, #0x38]
            0xE1530001,                               # cmp   r3, r1
            0x059C3004,                               # ldreq r3, [ip, #4]    id high
            0x059D1000 | (slot + 4),                  # ldreq r1, [sp, #0x3c]
            0x01530001,                               # cmpeq r3, r1
            bc(COND_EQ, "banner_match"),              # beq   match
            0xE28CC010,                               # add   ip, ip, #16
            b("banner_loop"),                         # b     loop
        ],
        "banner_match": [
            0xE59C1008,                               # ldr   r1, [ip, #8]    the path
            0xE58D1000 | FILE_PATH_PTR_SLOT,          # str   r1, [sp, #0x10]
            0xE59C300C,                               # ldr   r3, [ip, #12]   its length
            0xE0811003,                               # add   r1, r1, r3      -> its NUL
            0xE58D1000 | ARCHIVE_PATH_PTR_SLOT,       # str   r1, [sp, #0x04]
            0xE2833001,                               # add   r3, r3, #1      with the NUL
            0xE58D3000 | FILE_PATH_SIZE_SLOT,         # str   r3, [sp, #0x14]
            0xE3A01000 | PATH_EMPTY,                  # mov   r1, #1
            0xE58D1000 | ARCHIVE_PATH_TYPE_SLOT,      # str   r1, [sp, #0x00]
            0xE58D1000 | ARCHIVE_PATH_SIZE_SLOT,      # str   r1, [sp, #0x08] size 1
            0xE3A01000 | PATH_ASCII,                  # mov   r1, #3
            0xE58D1000 | FILE_PATH_TYPE_SLOT,         # str   r1, [sp, #0x0c]
            0xE3A03000 | ARCHIVE_SDMC,                # mov   r3, #9
            b("banner_back"),                         # b     back
        ],
        "banner_pass": [
            lambda at, labels: 0xE59F3000 | (labels["banner_archive"] - at - 8),  # ldr r3, ..
        ],
        "banner_back": [
            lambda at, labels: _b(at, hook["return_to"]),
        ],
        "banner_archive": [
            ARCHIVE_SAVEDATA_AND_CONTENT,             # what the replaced instruction loaded
        ],
        "banner_table": [
            # A literal holding the entries' address. Labels are .text offsets; what the
            # hook loads has to be the address the code runs at.
            lambda at, labels: TEXT_VA + labels["banner_entries"],
        ],
        "banner_entries": table,
    }
    return _assemble(blocks, base)


def _assemble(blocks: dict[str, list], base: int) -> tuple[list[int], dict[str, int]]:
    """Lay out labelled blocks of words and resolve their branches.

    A word is either an int or a callable taking (address, labels) - which is how the
    branches get written as label arithmetic instead of hand-counted offsets.
    """
    labels: dict[str, int] = {}
    address = base
    for name, words in blocks.items():
        labels[name] = address
        address += 4 * len(words)

    out: list[int] = []
    address = base
    for words in blocks.values():
        for word in words:
            out.append(word(address, labels) if callable(word) else word)
            address += 4
    return out, labels


def _stub_smdh_names(patch: dict, table_va: int, base: int) -> tuple[list[int], dict[str, int]]:
    """Two hooks and the routine they share, as one blob for the .text padding.

    HOME Menu reads a title's SMDH twice over: once from `ExeFS:/icon` when it fills its
    icon cache, and from then on out of that cache - `Cache.dat` in its SD extdata, which
    holds all 0x36C0 bytes, every language slot included. That is why switching the console
    language relabels everything without the cache being rebuilt, and why hooking only the
    ExeFS read changes nothing on a console whose cache was built before the mod.

    So both readers are wrapped, and both hand the buffer to the same `rewrite`:

        icon_hook   over the ReadTitleIcon thunk        (a cache fill, or a cache miss)
        cache_hook  over the cache reader itself        (every ordinary boot)

    Nothing is written back - the copy on the SD card stays as Nintendo left it, so removing
    the mod restores the original names with no cache rebuild.
    """
    short_at, long_at = smdh_names.slot_offsets(patch["lang_index"])
    page, short_low, long_low = short_at & ~0xFF, short_at & 0xFF, long_at & 0xFF
    if long_at & ~0xFF != page:
        raise RuntimeError(f"slot {patch['lang_index']} spans two immediate pages")

    def bl(target: str):
        return lambda at, labels: _bl(at, labels[target])

    def b(target: str):
        return lambda at, labels: _b(at, labels[target])

    def bc(cond: int, target: str):
        return lambda at, labels: _bc(cond, at, labels[target])

    def ldr_pc(reg: int, target: str):
        return lambda at, labels: 0xE59F0000 | (reg << 12) | (labels[target] - at - 8)

    blocks = {
        # Wraps the thunk at thunk_off, so it is entered with the thunk's own registers:
        # r0 = buffer, r1 = mediatype, r2/r3 = title id, lr = the caller. The thunk's three
        # instructions are reproduced verbatim because ReadTitleIcon() takes a fifth
        # argument off the caller's stack and expects ip to be zero.
        "icon_hook": [
            0xE92D400D,                          # push  {r0, r2, r3, lr}   buffer, title id
            0xE92D4008,                          # push  {r3, lr}           the thunk's frame
            0xE3A0C000,                          # mov   ip, #0
            0xE58DC000,                          # str   ip, [sp]           its fifth argument
            lambda at, labels: _bl(at, patch["reader_off"]),  # bl ReadTitleIcon
            0xE28DD008,                          # add   sp, sp, #8
            0xE3500000,                          # cmp   r0, #0
            bc(COND_NE, "icon_out"),             # bne   icon_out           the read failed
            0xE89D0007,                          # ldm   sp, {r0, r1, r2}   buffer, id lo, hi
            bl("rewrite"),                       # bl    rewrite
            0xE3A00000,                          # mov   r0, #0             the caller's zero
        ],
        "icon_out": [
            0xE8BD800E,                          # pop   {r1, r2, r3, pc}
        ],
        # Wraps the cache reader: r0 = cache object, r1 = key (title id then mediatype),
        # r2 = destination buffer, and it answers 1 on a hit, 0 on a miss.
        "cache_hook": [
            0xE92D4007,                          # push  {r0, r1, r2, lr}
            bl("cache_body"),                    # bl    the reader's own code
            0xE3500000,                          # cmp   r0, #0
            bc(COND_EQ, "cache_out"),            # beq   cache_out          cache miss
            0xE59D3004,                          # ldr   r3, [sp, #4]       the key
            0xE59D0008,                          # ldr   r0, [sp, #8]       the buffer
            0xE5931000,                          # ldr   r1, [r3]           title id low
            0xE5932004,                          # ldr   r2, [r3, #4]       title id high
            bl("rewrite"),                       # bl    rewrite
            0xE3A00001,                          # mov   r0, #1             it was a hit
        ],
        "cache_out": [
            0xE8BD800E,                          # pop   {r1, r2, r3, pc}
        ],
        # The reader's replaced prologue, so its own epilogue returns to cache_hook: it pops
        # pc off the lr this push saves, and that lr is cache_hook's `bl`.
        "cache_body": [
            0xE92D4FF0,                          # push  {r4-r8, sb, sl, fp, lr}
            lambda at, labels: _b(at, patch["cache_read_off"] + 4),
        ],
        # rewrite(r0 = SMDH buffer, r1 = title id low, r2 = title id high): replace the
        # short and long description of the one language slot the mod overwrites.
        "rewrite": [
            0xE92D41F0,                          # push  {r4, r5, r6, r7, r8, lr}
            0xE1A04000,                          # mov   r4, r0             buffer
            0xE1A05001,                          # mov   r5, r1             title id low
            0xE20260FF,                          # and   r6, r2, #0xff      title id high byte
            ldr_pc(7, "table"),                  # ldr   r7, [pc, #...]     the name table
        ],
        "loop": [
            0xE5970000,                          # ldr   r0, [r7]           entry id low
            0xE3500000,                          # cmp   r0, #0
            bc(COND_EQ, "done"),                 # beq   done               end of table
            0xE5D71004,                          # ldrb  r1, [r7, #4]       entry id high byte
            0xE5D72005,                          # ldrb  r2, [r7, #5]       short length
            0xE5D73006,                          # ldrb  r3, [r7, #6]       long length
            0xE1500005,                          # cmp   r0, r5
            bc(COND_NE, "next"),                 # bne   next
            0xE1510006,                          # cmp   r1, r6
            bc(COND_EQ, "match"),                # beq   match
        ],
        "next": [
            0xE0877082,                          # add   r7, r7, r2, lsl #1
            0xE0877083,                          # add   r7, r7, r3, lsl #1
            0xE2877008,                          # add   r7, r7, #8
            b("loop"),                           # b     loop
        ],
        "match": [
            0xE2877008,                          # add   r7, r7, #8         -> short text
            0xE2840000 | _imm12(page),           # add   r0, r4, #page
            0xE2800000 | _imm12(short_low),      # add   r0, r0, #short
            0xE1B0C002,                          # movs  ip, r2
            bc(COND_EQ, "long"),                 # beq   long               nothing to write
        ],
        "copy_short": [
            0xE0D7E0B2,                          # ldrh  lr, [r7], #2
            0xE0C0E0B2,                          # strh  lr, [r0], #2
            0xE25CC001,                          # subs  ip, ip, #1
            bc(COND_NE, "copy_short"),           # bne   copy_short
            0xE3A0E000,                          # mov   lr, #0
            0xE1C0E0B0,                          # strh  lr, [r0]           terminate
        ],
        "long": [
            0xE2840000 | _imm12(page),           # add   r0, r4, #page
            0xE2800000 | _imm12(long_low),       # add   r0, r0, #long
            0xE1B0C003,                          # movs  ip, r3
            bc(COND_EQ, "done"),                 # beq   done
        ],
        "copy_long": [
            0xE0D7E0B2,                          # ldrh  lr, [r7], #2
            0xE0C0E0B2,                          # strh  lr, [r0], #2
            0xE25CC001,                          # subs  ip, ip, #1
            bc(COND_NE, "copy_long"),            # bne   copy_long
            0xE3A0E000,                          # mov   lr, #0
            0xE1C0E0B0,                          # strh  lr, [r0]
        ],
        "done": [
            0xE8BD81F0,                          # pop   {r4, r5, r6, r7, r8, pc}
        ],
        "table": [
            table_va,                            # literal
        ],
    }
    return _assemble(blocks, base)

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

    if patch.get("pane_hook"):
        # The pane hook composes strings into a buffer that starts where .bss ends, so .bss
        # has to grow by that much or the buffer is memory nobody mapped. The loader sizes
        # the region from this field, and the title itself never reads past its own bss.
        bss = struct.unpack_from("<I", out, BSS_SIZE_OFFSET)[0]
        struct.pack_into("<I", out, BSS_SIZE_OFFSET, bss + PANE_SCRATCH_BYTES)

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


def wants_names(tid: str) -> str | None:
    """Which application-name table this title's patch needs, if any."""
    patch = HOOK_PATCHES.get(tid.upper())
    if patch is None:
        return None
    if patch.get("kind") == "smdh_names":
        return "smdh"
    return "pane" if patch.get("pane_hook") else None


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


def banner_sd_path(title: dict) -> str:
    """Where the hook expects one replacement banner. Written by tools/build.py."""
    return f"/luma/titles/0004003000009802/{title['image_name']}"


def _verify_banner(
    patch: dict,
    code: bytes,
    records: list[tuple[int, bytes]],
    labels: dict[str, int],
    entries: list[dict],
) -> None:
    """Apply the records and walk the banner hook: in, through the table, and out.

    What would be silent here and fatal on a console: a hook that forgets to come back, a
    pass-through that hands FS something other than the archive id the replaced instruction
    was loading, or a table entry pointing at a path that is not where it says it is.
    """
    patched = bytearray(code)
    for offset, data in records:
        patched[offset:offset + len(data)] = data
    word = lambda off: struct.unpack_from("<I", patched, off)[0]  # noqa: E731

    hook = patch["banner_hook"]
    entry = _branch_target(word(hook["site_off"]), hook["site_off"])
    if entry != labels["banner_hook"]:
        raise RuntimeError(f"0x{hook['site_off']:X} does not branch into the banner hook")

    back = _branch_target(word(labels["banner_back"]), labels["banner_back"])
    if back != hook["return_to"]:
        raise RuntimeError(
            f"the banner hook returns to 0x{back:X}, expected 0x{hook['return_to']:X}"
        )

    # The pass-through must reproduce the archive id the original instruction loaded, so
    # read that literal out of the untouched code and compare.
    original = struct.unpack_from("<I", code, hook["site_off"])[0]
    literal_at = hook["site_off"] + 8 + (original & 0xFFF)
    archive_id = struct.unpack_from("<I", code, literal_at)[0]
    if archive_id != ARCHIVE_SAVEDATA_AND_CONTENT:
        raise RuntimeError(
            f"0x{literal_at:X} holds 0x{archive_id:08X}, not ARCHIVE_SAVEDATA_AND_CONTENT"
        )
    passthrough = word(labels["banner_pass"])
    reached = labels["banner_pass"] + 8 + (passthrough & 0xFFF)
    if passthrough & 0xFFFFF000 != 0xE59F3000 or word(reached) != archive_id:
        raise RuntimeError("the banner pass-through does not restore the original archive id")

    # The table the hook walks: four words an entry, a zero title id to stop on, and each
    # path where the entry claims and NUL-terminated where its length says.
    table_at = word(labels["banner_table"])
    for index, expected in enumerate(entries):
        at = table_at - TEXT_VA + index * 16
        title_id = word(at) | (word(at + 4) << 32)
        path_va, path_len = word(at + 8), word(at + 12)
        if title_id != expected["title_id"]:
            raise RuntimeError(
                f"table entry {index} is for {title_id:016X}, expected "
                f"{expected['title_id']:016X}"
            )
        if path_va != expected["path_va"] or path_len != expected["path_len"]:
            raise RuntimeError(f"table entry {index} does not point at its own path")
        if path_len + 1 > 0xFF:
            raise RuntimeError(f"{expected['path']!r} is too long for the frame's size slot")
        if not any(expected["path"].encode("ascii") + b"\0" in data for _, data in records):
            raise RuntimeError(f"{expected['path']!r} was never written into .rodata")
    if word(table_at - TEXT_VA + len(entries) * 16) != 0:
        raise RuntimeError("the banner table has no terminator")


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


def _pane_records(
    patch: dict, code: bytes, exheader: bytes, table: bytes
) -> tuple[list[tuple[int, bytes]], list[str]]:
    """The hook, its blob and its table, laid out around what Luma claims for itself."""
    hook = patch["pane_hook"]
    site = hook["set_text_off"]
    word = struct.unpack_from("<I", code, site)[0]
    if word != hook["original_word"]:
        raise RuntimeError(
            f"0x{site:X} holds 0x{word:08X}, expected 0x{hook['original_word']:08X} "
            f"- this is not the text setter the offsets were taken from"
        )

    text_size = struct.unpack_from("<I", exheader, TEXT_SIZE_OFFSET)[0]
    ro_address = struct.unpack_from("<I", exheader, 0x20)[0]
    ro_size = struct.unpack_from("<I", exheader, 0x28)[0]
    rounded = lambda v: (v + 0xFFF) & ~0xFFF  # noqa: E731

    table_off = rounded(text_size) + ro_size + LUMA_PATH_SIZE
    table_va = ro_address + ro_size + LUMA_PATH_SIZE
    ro_room = rounded(ro_size) - ro_size - LUMA_PATH_SIZE
    if len(table) > ro_room:
        raise RuntimeError(f"the name table is {len(table)} bytes, .rodata padding has {ro_room}")

    # A writable scratch buffer for the composed strings. NOT the .data page padding: the
    # loader lays .bss down immediately after .data, unaligned, so that padding is the first
    # few hundred bytes of .bss and belongs to the title. Writing UTF-16 there overwrote a
    # list head at 0x200B2C and the Activity Log took a data abort on `ldr r5, [r4]` with
    # r4 = 0x04410020 - two Cyrillic code units read as a pointer.
    #
    # So the buffer goes past the end of .bss instead, and patch_exheader() grows bss to
    # cover it. Everything up to that point is the title's own; everything after is ours.
    data_address = struct.unpack_from("<I", exheader, 0x30)[0]
    data_size = struct.unpack_from("<I", exheader, 0x38)[0]
    bss_size = struct.unpack_from("<I", exheader, BSS_SIZE_OFFSET)[0]
    scratch_va = data_address + data_size + bss_size

    text_room = rounded(text_size) - text_size
    sizing, _ = _pane_hook(patch, table_va, scratch_va, 0)
    blob_off = rounded(text_size) - len(sizing) * 4
    words, labels = _pane_hook(patch, table_va, scratch_va, blob_off)
    blob = b"".join(struct.pack("<I", w) for w in words)
    if len(blob) + LUMA_PAYLOAD_SIZE > text_room:
        raise RuntimeError(
            f"the pane hook is {len(blob)} bytes and Luma needs 0x{LUMA_PAYLOAD_SIZE:X} more, "
            f".text padding is {text_room}"
        )

    for what, offset, data in (("hook", blob_off, blob), ("table", table_off, table)):
        if any(code[offset:offset + len(data)]):
            raise RuntimeError(f"the {what} would overwrite code at 0x{offset:X}, not padding")

    records = [
        (site, struct.pack("<I", _b(site, labels["pane_hook"]))),
        (blob_off, blob),
        (table_off, table),
    ]
    log = [
        f"code.ips: SetPaneText at 0x{site:X} routed through a {len(blob)}-byte name hook "
        f"at 0x{blob_off:X} (va 0x{TEXT_VA + blob_off:X}), "
        f"{text_room - len(blob)} bytes of .text padding left for Luma's payload",
        f"code.ips: {len(table)}-byte name table at va 0x{table_va:X} "
        f"({ro_room} bytes available past Luma's path)",
        f"code.ips: {2 * PANE_SCRATCH_UNITS}-byte scratch at va 0x{scratch_va:X}, "
        f"past the title's own .bss",
        f"exheader.bin: bss grown by {PANE_SCRATCH_BYTES} bytes to cover it",
    ]
    return records, log


def _generate_smdh_names(
    patch: dict, code: bytes, exheader: bytes, version: int, table: bytes
) -> tuple[dict[str, bytes], list[str]]:
    """code.ips that routes both of HOME Menu's SMDH readers through the rewriting stub.

    Four records: one word over each reader's entry, the stub blob at the end of the .text
    padding, and the name table in the .rodata padding. No exheader - HOME Menu already has
    DirectSdmc, and nothing here needs Luma to find a symbol.
    """
    thunk = patch["thunk_off"]
    word = struct.unpack_from("<I", code, thunk)[0]
    if word != ORIGINAL_THUNK_WORD:
        raise RuntimeError(
            f"0x{thunk:X} holds 0x{word:08X}, expected 0x{ORIGINAL_THUNK_WORD:08X} (push {{r3, lr}}) "
            f"- this is not the thunk the offsets were taken from"
        )
    call = struct.unpack_from("<I", code, thunk + 0xC)[0]
    imm = (call & 0xFFFFFF) - (0x1000000 if call & 0x800000 else 0)
    if call >> 24 != 0xEB or thunk + 0xC + 8 + imm * 4 != patch["reader_off"]:
        raise RuntimeError(
            f"0x{thunk + 0xC:X} does not call ReadTitleIcon at 0x{patch['reader_off']:X}"
        )

    cache = patch["cache_read_off"]
    word = struct.unpack_from("<I", code, cache)[0]
    if word != ORIGINAL_CACHE_WORD:
        raise RuntimeError(
            f"0x{cache:X} holds 0x{word:08X}, expected 0x{ORIGINAL_CACHE_WORD:08X} "
            f"- this is not the cache reader the offsets were taken from"
        )

    text_size = struct.unpack_from("<I", exheader, TEXT_SIZE_OFFSET)[0]
    ro_address = struct.unpack_from("<I", exheader, 0x20)[0]
    ro_size = struct.unpack_from("<I", exheader, 0x28)[0]
    rounded = lambda v: (v + 0xFFF) & ~0xFFF  # noqa: E731

    # Past Luma's path string, which lands at the very start of the .rodata padding.
    table_off = rounded(text_size) + ro_size + LUMA_PATH_SIZE
    table_va = ro_address + ro_size + LUMA_PATH_SIZE
    ro_room = rounded(ro_size) - ro_size - LUMA_PATH_SIZE
    if len(table) > ro_room:
        raise RuntimeError(f"the name table is {len(table)} bytes, .rodata padding has {ro_room}")

    # The blob goes at the end of the .text padding, leaving the front to Luma's payload.
    # Its length is known before its address is, so it is laid out twice.
    text_room = rounded(text_size) - text_size
    sizing, _ = _stub_smdh_names(patch, table_va, 0)
    patch["stub_off"] = rounded(text_size) - len(sizing) * 4
    words, labels = _stub_smdh_names(patch, table_va, patch["stub_off"])
    stub = b"".join(struct.pack("<I", w) for w in words)

    # The banner hook, if this title has one, goes immediately below the name stub, and its
    # path string immediately past the name table. Same two-pass layout, same padding.
    banner = banner_off = None
    banner_entries: list[dict] = []
    banner_paths = bytearray()
    banner_labels: dict[str, int] = {}
    if patch.get("banner_hook"):
        paths_off = table_off + len(table)
        paths_va = table_va + len(table)
        for title in patch["banner_hook"]["titles"]:
            path = banner_sd_path(title)
            banner_entries.append(
                {
                    "title_id": title["title_id"],
                    "path": path,
                    "path_va": paths_va + len(banner_paths),
                    "path_len": len(path),
                }
            )
            banner_paths += path.encode("ascii") + b"\0"
        if len(table) + len(banner_paths) > ro_room:
            raise RuntimeError(
                f"the name table and {len(banner_entries)} banner paths need "
                f"{len(table) + len(banner_paths)} bytes, .rodata padding has {ro_room}"
            )
        sizing, _ = _banner_hook(patch, banner_entries, 0)
        banner_off = patch["stub_off"] - len(sizing) * 4
        banner_words, banner_labels = _banner_hook(patch, banner_entries, banner_off)
        banner = b"".join(struct.pack("<I", w) for w in banner_words)

    used = len(stub) + (len(banner) if banner else 0)
    if used + LUMA_PAYLOAD_SIZE > text_room:
        raise RuntimeError(
            f"stubs are {used} bytes and Luma needs 0x{LUMA_PAYLOAD_SIZE:X} more, "
            f".text padding is {text_room}"
        )

    for what, offset, blob in (("stub", patch["stub_off"], stub), ("table", table_off, table)):
        if any(code[offset:offset + len(blob)]):
            raise RuntimeError(f"the {what} would overwrite code at 0x{offset:X}, not padding")

    records = [
        (thunk, struct.pack("<I", _b(thunk, labels["icon_hook"]))),
        (cache, struct.pack("<I", _b(cache, labels["cache_hook"]))),
        (patch["stub_off"], stub),
        (table_off, table),
    ]
    _verify_smdh_names(patch, code, records, text_size, labels)

    if banner:
        site = patch["banner_hook"]["site_off"]
        word = struct.unpack_from("<I", code, site)[0]
        if word != patch["banner_hook"]["original_word"]:
            raise RuntimeError(
                f"0x{site:X} holds 0x{word:08X}, expected "
                f"0x{patch['banner_hook']['original_word']:08X} - this is not the archive id "
                f"the banner offsets were taken from"
            )
        if any(code[banner_off:banner_off + len(banner)]):
            raise RuntimeError(f"the banner hook would overwrite code at 0x{banner_off:X}")
        records += [
            (site, struct.pack("<I", _b(site, banner_labels["banner_hook"]))),
            (banner_off, banner),
            (paths_off, bytes(banner_paths)),
        ]
        _verify_banner(patch, code, records, banner_labels, banner_entries)

    log = [
        f"{patch['title']} title version {version}",
        f"code.ips: ReadTitleIcon thunk at 0x{thunk:X} -> 0x{labels['icon_hook']:X}, "
        f"icon cache reader at 0x{cache:X} -> 0x{labels['cache_hook']:X}",
        f"code.ips: {len(stub)}-byte stub blob at 0x{patch['stub_off']:X} "
        f"(va 0x{TEXT_VA + patch['stub_off']:X}), {text_room - len(stub)} bytes of .text "
        f"padding left for Luma's payload",
        f"code.ips: {len(table)}-byte name table at va 0x{table_va:X}, past the "
        f"{LUMA_PATH_SIZE} bytes Luma claims for its path ({ro_room} bytes available)",
    ]
    if banner:
        served = ", ".join(f"{e['title_id']:016X} -> {Path(e['path']).name}" for e in banner_entries)
        log.append(
            f"code.ips: banner open at 0x{patch['banner_hook']['site_off']:X} -> "
            f"{len(banner)}-byte hook at 0x{banner_off:X}, serving {served}"
        )
    return {"code.ips": make_ips(records)}, log


def _verify_smdh_names(
    patch: dict, code: bytes, records: list[tuple[int, bytes]], text_size: int, labels: dict[str, int]
) -> None:
    """Both readers must reach their hook, and Luma must still find every symbol it needs."""
    from layeredfs_check import find_symbols  # imported late: layeredfs_check imports build

    patched = bytearray(code)
    for offset, data in records:
        patched[offset:offset + len(data)] = data

    for what, site, hook in (
        ("ReadTitleIcon thunk", patch["thunk_off"], "icon_hook"),
        ("icon cache reader", patch["cache_read_off"], "cache_hook"),
    ):
        word = struct.unpack_from("<I", patched, site)[0]
        landed = _branch_target(word, site)
        if landed != labels[hook]:
            raise RuntimeError(
                f"the {what} branches to "
                f"{'0x%X' % landed if landed is not None else 'nowhere'}, not to {hook}"
            )

    # The cache reader's own prologue has to survive in the trampoline, or its epilogue would
    # pop a return address that was never pushed.
    if struct.unpack_from("<I", patched, labels["cache_body"])[0] != ORIGINAL_CACHE_WORD:
        raise RuntimeError("the cache trampoline does not start with the reader's own prologue")
    back = _branch_target(struct.unpack_from("<I", patched, labels["cache_body"] + 4)[0],
                          labels["cache_body"] + 4)
    if back != patch["cache_read_off"] + 4:
        raise RuntimeError(f"the cache trampoline continues at 0x{back:X}, not into the reader")

    symbols = find_symbols(bytes(patched), min(text_size, len(patched)))
    missing = [name for name, off in symbols.items() if off is None and name != "fsUnmountArchive"]
    if missing:
        raise RuntimeError(f"the patch cost Luma a LayeredFS symbol: {', '.join(missing)}")


def generate(
    tid: str, code_path: Path, exheader_path: Path, names: dict[str, bytes] | None = None
) -> tuple[dict[str, bytes], list[str]]:
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

    if patch.get("kind") == "smdh_names":
        if not (names or {}).get("smdh"):
            raise RuntimeError(f"{patch['title']} needs an SMDH name table and none was built")
        return _generate_smdh_names(patch, code, exheader, version, names["smdh"])

    if patch.get("kind") == "exheader_only":
        access = struct.unpack_from("<Q", exheader, ACCESS_INFO_OFFSET)[0]
        return {"exheader.bin": patch_exheader(tid, exheader)}, [
            f"{patch['title']} title version {version}",
            f"exheader.bin: DirectSdmc granted (accessInfo 0x{access:016x} -> "
            f"0x{access | (1 << DIRECT_SDMC_BIT):016x}); Luma finds every symbol it needs "
            f"in the title's own code, so no code.ips",
        ]

    globals_value = struct.unpack_from("<I", code, patch["globals_off"])[0]
    stub = build_stub(patch, globals_value)
    if len(stub) > patch["stub_room"]:
        raise RuntimeError(f"stub is {len(stub)} bytes, only {patch['stub_room']} are free")

    # Verify against the exheader we are about to ship, not the original: the scan range
    # is text.size, and for a stub in the .text padding that is the widened value.
    new_exheader = patch_exheader(tid, exheader)
    patch["text_size"] = struct.unpack_from("<I", new_exheader, TEXT_SIZE_OFFSET)[0]
    _verify(patch, code, stub)

    records = [(patch["stub_off"], stub)]
    pane_log: list[str] = []
    if patch.get("pane_hook"):
        if not (names or {}).get("pane"):
            raise RuntimeError(f"{patch['title']} needs a pane name table and none was built")
        extra, pane_log = _pane_records(patch, code, exheader, names["pane"])
        records += extra

    files = {
        "code.ips": make_ips(records),
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
    ] + pane_log
    return files, log
