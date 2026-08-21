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
import os
import struct
from pathlib import Path

import smdh_names
import variant

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

# Stands in for a branch whose target only the build knows - see patched_code().
PLACEHOLDER_BRANCH = 0xEAFFFFFE  # b .

# The first instruction of each HOME Menu function the branches replace.
ORIGINAL_THUNK_WORD = 0xE92D4008  # push {r3, lr}
ORIGINAL_CACHE_WORD = 0xE92D4FF0  # push {r4-r8, sb, sl, fp, lr}

# System Settings reaches its SMDH reader through two thunks that differ in one immediate:
# push {r3, lr}; mov ip, #mediatype; str ip, [sp]; bl reader; pop {r3, pc}.
THUNK_SET_MEDIATYPE = 0xE3A0C000    # mov ip, #<mediatype>, the immediate masked off
THUNK_STORE_MEDIATYPE = 0xE58DC000  # str ip, [sp]
THUNK_RETURN_WORD = 0xE8BD8008      # pop {r3, pc}
THUNK_CALL_OFFSET = 0xC             # the `bl` the wrapper takes over

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
    # The manual document itself is not this title's romfs: ebird mounts the *documented*
    # title's content as `man:` and opens `man:/Manual.bcma`. Luma's LayeredFS payload hooks
    # fsOpenFileDirectly/fsTryOpenFile and redirects any path that starts with `rom:` or with
    # the one "update romfs" mount it found in .text - and it looks for those by name:
    # ro2:, rom2:, rex:, patch:, ext:. None of them appears in ebird, `man:` does.
    #
    # So the mount is renamed. `rex:` is the same four bytes, the mount name and the path
    # are patched in place, and Luma then serves `rex:/Manual.bcma` from
    # /luma/titles/0004003000009B02/romfs/Manual.bcma - falling back to the real manual on
    # its own when that file is absent, which is what its payload does when the SD open
    # fails. Luma's search pattern is a NUL followed by the name, so the copy at 0x481D4
    # (the one preceded by a terminator) is the one it finds.
    #
    # What this does not do yet is tell the titles apart: every manual on the console reads
    # the same replacement file. Making it per-title means building the name from the title
    # id the mount already has in hand - see the path-building code at 0x1480BC.
    "0004003000009B02": {
        "title": "Instruction Manual (ebird) EUR",
        "title_version": 5,
        "mount_rename": {
            "old": b"man:",
            "new": b"rex:",
            # the mount name, the path it is used in, and the .rodata copy the unmount reads
            "offsets": [0x481C0, 0x481D4, 0xAE6A0],
        },
        # ... and one file per documented title instead of one file for the whole console.
        #
        # The path stops being a constant. The 28 words at 0x480BC used to take the string
        # `man:/Manual.bcma`, widen it to UTF-16 into the stack buffer at sp+28 with a
        # multibyte converter, and hand that to fsTryOpenFile. They now do this instead:
        #
        #     ldr r0, =globals; ldr r0, [r0]; ldr r0, [r0, #4]; ldr r2, [r0]
        #         the documented title's id, read exactly where the mount above reads it
        #     walk `titles` for its low word; not there -> keep `rex:/Manual.bcma`
        #     there -> snprintf(sp+96, 48, "rex:/%08x.bcma", low word)
        #     widen whichever string that left into sp+28, leaving r4 on the terminator
        #     for the store that follows the block
        #
        # The table is the point. Luma's payload falls back to the original archive when the
        # SD file will not open - but it retries with the *same* path, and the manual content
        # of a title holds `Manual.bcma` and nothing else. Ask it for `00009d02.bcma` and the
        # fallback fails too, which turns every untranslated title's manual into a load
        # error. So a title only gets its own name if this build actually ships a file for
        # it; everything else keeps the constant name and therefore keeps its own manual.
        #
        # Only the low word of the title id goes into the name and the table - the high word
        # is 00040030 or 00040010 for every system title, and two 32-bit varargs would need
        # the caller's stack slot saved and restored, which does not fit in 28 words.
        "manual_path": {
            # Verified on hardware: the Browser and System Settings manuals come off the SD
            # card in Ukrainian, every other title keeps its own. MANUAL_PATCH still selects
            # the two cut-down builds the bisect used, in case this ever needs splitting again:
            #   MANUAL_PATCH=copy    only the UTF-16 widening loop is replaced
            #   MANUAL_PATCH=rodata  that, plus the path string moved to .rodata
            "enabled": True,
            "block_off": 0x480BC,
            "globals_literal": 0x481C8,  # -> 0x1CE788, the object holding {title id, media}
            "snprintf": 0x57EDC,         # (char *out, size_t size, const char *fmt, ...)
            "scratch": 96,               # ascii scratch, inside the path buffer at sp+28
            "scratch_size": 48,
            # The 20 bytes the dead `man:/Manual.bcma` leaves behind: `rex:` for Luma's mount
            # search to find (the byte before it is already a terminator), then three literals.
            "pool_off": 0x481D4,
            "pool_room": 20,
            "pool_ends_at": 0xE92D4070,  # the next function's push, a guard for the offsets
            # .rodata page padding: rodata ends at 0x1BCBA8 and the page at 0x1BD000. Luma
            # claims the first 48 bytes for its own LayeredFS path, so ours start past that.
            # The room stops where the SMDH name table starts (0xBCD10): 8 bytes of table
            # plus a 19-byte path per title, and 8 more to terminate it, so 0x138 holds
            # eleven titles - which is what this build ships and what the padding allows:
            # the two tables together are 977 of the 1064 bytes between 0xBCBD8 and the
            # 0xBD000 page boundary, and a twelfth title would cost about 100 more.
            "rodata_off": 0xBCBD8,
            # 0x150 of the 0x428-byte padding, the rest goes to the SMDH name table that
            # starts at 0xBCD28. 18 bytes a title (8 of table, a 10-byte path) means this
            # holds eighteen, which is about what the name table holds too - the two grow
            # at the same rate, so the split is even rather than first-come.
            "rodata_room": 0x150,
            "fallback": b"rex:/Manual.bcma\0",   # the string in .text, left where it is
            "second_site": 0x48294,              # the caller's `sub r1, pc, #200`
            "second_site_word": 0xE24F10C8,
            # The titles this build ships a manual for. tools/manual.py checks it matches.
            "titles": [
                "0004003000009D02",
                # New 3DS ships its own browser, with its own document - see docs/dump-new3ds.md.
                "0004003020009D02",
                "0004001000022000",
                "0004001000022200",
                "0004001000022100",
                "0004001000022400",
                "0004001000022500",
                "0004001000022700",
                "0004001000022800",
                "0004001000022900",
                "0004001000022D00",
                "0004001000022E00",
            ],
        },
        # The name across the top of every manual page is not in the document: it is the
        # short description out of the *documented* title's SMDH, which ebird reads itself
        # from ExeFS:/icon in NAND. LayeredFS cannot reach that, so the read is hooked and
        # the buffer's slot for the language this build replaces is overwritten (see
        # tools/variant.py) - the same table and the same routine HOME Menu's patch uses,
        # see SMDH_NAMES there.
        #
        # One reader, one caller, and no cache of any kind:
        #
        #   15E38  the caller: allocates 0x36C0, takes the title id and mediatype out of
        #          the globals object the manual mount reads too, and calls
        #   15E84  bl 0x12F5B8, the reader: opens `icon` of that title and pulls all
        #          0x36C0 bytes in; r0 = buffer, r1 = mediatype, r2/r3 = title id
        #   15F84  the buffer's whole 0x2000-byte title array is copied into the viewer's
        #          own object, every language slot at once, and the name is picked from it
        #          later - so rewriting the slot right after the read is enough.
        #
        # Where the blob goes needs saying. This title's .text padding is 88 bytes and the
        # mount stub already has 84 of them, and Luma claims throwFatalError() (0x1A434,
        # 288 bytes) for its own 0x114-byte payload, which leaves 12. So the blob goes over
        # a function that is in .text and dead: 0x2C6E8 is a second copy of the icon-tile
        # copier that is also inlined at 0x115F04, and nothing in the image reaches it -
        # no `bl`, no `b`, no absolute pointer in .text, .rodata or .data, and the one
        # computed jump in this title (0x8FC90) branches inside its own table. The sha256
        # below pins those 636 bytes, so a different build fails the build instead of
        # taking the patch on top of live code.
        "smdh_hook": {
            "site_off": 0x15E84,        # `bl` to the reader, the one call it ever gets
            "reader_off": 0x2F5B8,      # ReadTitleIcon(buffer, mediatype, tid_lo, tid_hi)
            "reads": "the manual's SMDH read",
            "effect": "the name above the page is the one the HOME Menu shows",
            "stub_off": 0x2C6E8,        # the dead icon-tile copier
            "stub_room": 636,           # up to the next function at 0x2C964
            "dead_sha256": "c8a3a2b26f7efa67ed864551c80362cc996116ffb5ff17b654287ed0d282502f",
            # .rodata padding again, past the manual-path table at 0xBCBD8 with room for it
            # to grow: the table there is 8 bytes per title plus a 10-byte path each.
            # Short descriptions only here (see build_table(short_only=True)) - the viewer
            # never prints the long one, and carrying it cost as much again.
            "rodata_off": 0xBCD28,
            "rodata_room": 0x2D8,       # up to the 0xBD000 page boundary
        },
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
    # eShop applet (mint), EUR, title version 22 - the in-app purchase and update flow, the
    # one StreetPass Mii Plaza's Update button hands off to. Verified working on hardware.
    #
    # Same shape as the Friend List, down to the byte: its FSUSER_OpenArchive IPC wrapper at
    # 0x2E758 is identical to the Friend List's 0x6E41C, and the mount function at 0x2D8D4
    # opens the archive, allocates the object (vtable, fs:USER session at globals+0x10, the
    # u64 handle off sp+8) and stores it with `str r0, [sl]`. So the tail takes the result in
    # r8 with `out` in sl on a 0x14 frame - the sl_frame14 variant, entered at the result
    # check that follows the OpenArchive retry loop.
    #
    # The stub goes over throwFatalError(): the .text padding is 1880 bytes (0x1018A8 to the
    # 0x102000 page boundary), more than the 0x114 Luma needs, so Luma takes the padding and
    # leaves this function alone. No text.size override is needed.
    "000400300000D602": {
        "title": "eShop applet (mint) EUR",
        "title_version": 22,
        "code_sha256": "3968a6fb1af36187b02b586781e7aad27c34761341713967521c6a87881341d5",
        "variant": "sl_frame14",
        "stub_off": 0x87814,     # throwFatalError(), which Luma leaves alone here
        "stub_room": 284,        # bytes until the next function's `push`
        "open_archive": 0x2E758,  # the title's own FSUSER_OpenArchive IPC wrapper
        "mount_tail": 0x2D97C,   # tail of the mount function, entered with r8 = result
        "globals_off": 0x2D9F4,  # literal holding the nn::fs globals base (+0x10 = fs:USER session)
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
    # Health & Safety Information (ssafe), EUR New 3DS, remaster version 0. The Old 3DS entry
    # above stays exactly as it is: the two titles live side by side, one per console.
    #
    # New 3DS does not ship the `safe` application at all. What it ships under this title id
    # is the Instruction Manual viewer (`ebird`) with a document of its own: the romfs is
    # byte for byte the applet's, plus manual/Manual.bcma and manual/ManualEn.bcma, and the
    # EUR document - the one with a Russian locale in it - is content index 1.
    #
    # Same mechanism as its Old 3DS namesake and for the same reason: no FSUSER_OpenArchive
    # anywhere in .text (the whole fs:USER vocabulary here is the OpenFileDirectly wrapper at
    # 0x6858C), so a mount stub would have nothing to call and Luma's symbol search comes up
    # empty. Both ARCHIVE_ROMFS opens are pointed at an image on the SD card instead, with
    # the path slots in the same places as everywhere else (type at sp+0xC, pointer at
    # sp+0x10, size at sp+0x14), and no romfs/ folder ships, so patchLayeredFs() never runs.
    #
    # `code_edits` is what puts the document inside that image. LoadManual() at 0x55148 picks
    # between two paths: `man:/Manual.bcma`, the EUR document in content index 1, which no
    # redirect of ours can reach - and `rom:/manual/Manual.bcma`, its own romfs, which is the
    # image we ship. So the branch is forced down the `rom:` side and both spellings there
    # are pointed at the same file. What the console then reads is the document this build
    # writes into the image - the stub the title carries at that path is a 3117-byte
    # placeholder with a Japanese locale and nothing else in it.
    #
    # The name across the top of the page comes from the same place the Instruction Manual's
    # does - the documented title's `ExeFS:/icon`, read once at 0x161BC - so it needs the same
    # wrapper. Here the documented title is this one, and the id it asks for is the *Old 3DS*
    # one: the pair hardcoded at 0x61F8C is `00022300`/`00040010`, and `20022300` appears
    # nowhere in .text. Which is also the id the console launches it under, and why the name
    # stayed Russian while everything the build replaces came out Ukrainian - the SMDH is in
    # NAND, out of reach of any file on the card.
    #
    # `titles` is what goes into the table: both spellings of the pair, so the lookup matches
    # whichever the runtime hands over. The wrapper and the table are placed by
    # _place_smdh_hook() rather than written down here - they go in the paddings the romfs
    # redirect leaves behind, and both depend on how long the table is.
    "0004001020022300": {
        "title": "Health & Safety Information (ssafe) EUR New3DS",
        "title_version": 0,
        "code_sha256": "1e6c6bafb3060b9268dfe41a22e8d9ca80d96110569862be3990349f5e8c2c19",
        "kind": "romfs_from_sd",
        "image_name": "ssafe_romfs.bin",
        "smdh_hook": {
            "site_off": 0x161BC,      # the `bl` to the reader, the one call it ever gets
            "reader_off": 0x32740,    # ReadTitleIcon(buffer, mediatype, tid_lo, tid_hi)
            "reads": "the document's SMDH read",
            "effect": "the name above the page is the one the HOME Menu shows",
            "titles": ["0004001000022300", "0004001020022300"],
        },
        "stub_off": 0xAA474,        # .text page padding, 0xAA474..0xAB000 (2956 bytes)
        "stub_room": 2956,
        "sites": [
            {"patch_at": 0x04B70, "return_to": 0x04B74},
            {"patch_at": 0x0AFA8, "return_to": 0x0AFAC},
        ],
        "code_edits": [
            {
                "off": 0x55224,
                "expect": b"\x04\x00\x00\x0a",   # beq 0x5523C - taken when man: is not used
                "write": b"\x04\x00\x00\xea",    # b   0x5523C - always build a rom: path
                "why": "the manual comes off the SD image, not out of content index 1",
            },
            {
                "off": 0x55264,
                "expect": b"\xa0\x10\x8f\xe2",   # add r1, pc, #0xa0 -> "manual/ManualEn.bcma"
                "write": b"\xb8\x10\x8f\xe2",    # add r1, pc, #0xb8 -> "manual/Manual.bcma"
                "why": "one document in the image serves both spellings of the path",
            },
        ],
    },
    # 3DS Memo (memolib), EUR, title version 3 - the memo pad Miiverse and the Friend List
    # open for a handwritten post. Same shape as Download Play: its whole fs:USER vocabulary
    # is OpenFileDirectly (the wrapper at 0x15C50), with no OpenArchive/OpenFile/CloseArchive
    # anywhere in .text, so a mount stub would have nothing to call.
    #
    # Both of the wrapper's callers pass ARCHIVE_ROMFS and lay the file path out in the slots
    # the redirect stub rewrites: type at sp+0xC, pointer at sp+0x10, size 0xC at sp+0x14.
    # r1 and r3 are the only registers the stub touches, and both sites reload them after the
    # displaced `mov r3, #3`, so nothing live is lost.
    "000400300000F602": {
        "title": "3DS Memo (memolib) EUR",
        "title_version": 3,
        "code_sha256": "c198a6833cab9ce51c436020dc09b9fbbd548394f551bc5cc7d7224eeac0177d",
        "kind": "romfs_from_sd",
        "image_name": "memolib_romfs.bin",
        "stub_off": 0x56A0C,        # .text page padding, 0x56A0C..0x57000
        "stub_room": 1524,
        "sites": [
            {"patch_at": 0x03900, "return_to": 0x03904},
            {"patch_at": 0x09710, "return_to": 0x09714},
        ],
    },
    # Circle Pad Pro applet (extrapad), EUR, title version 4. Same shape again, and this one
    # is missing `fsUnmountArchive` as well - the one symbol Luma tolerates not finding, so
    # the redirect is the only route regardless.
    #
    # Its OpenFileDirectly wrapper is at 0x325A8 and its two callers are the same pair of
    # frames as 3DS Memo's, down to the instruction words.
    "000400300000CD02": {
        "title": "Circle Pad Pro applet (extrapad) EUR",
        "title_version": 4,
        "code_sha256": "0b6322653e8c53c671ae2e4a4f6289c42315a2ce591ab2212598d8dc6c33fd7d",
        "kind": "romfs_from_sd",
        "image_name": "extrapad_romfs.bin",
        "stub_off": 0x55350,        # .text page padding, 0x55350..0x56000
        "stub_room": 3248,
        "sites": [
            {"patch_at": 0x08024, "return_to": 0x08028},
            {"patch_at": 0x11AD8, "return_to": 0x11ADC},
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
        # The picture on the upper screen comes from the highlighted title's own
        # ExeFS:/banner, which HOME Menu opens itself - see docs/banner-ua.md. The open is
        # shared by every title, so the hook compares the title id first and swaps only the
        # ones listed below for a file on the SD card.
        "banner_hook": {
            "open_off": 0x61DE4,   # OpenTitleBanner(out, mediatype, tid_lo, tid_hi)
            "site_off": 0x61E64,   # `ldr r3, [pc, #0xb4]` - the archive id, last arg set
            "original_word": 0xE59F30B4,
            "return_to": 0x61E68,
            "title_id_slot": 0x38,  # `strd r2, r3, [sp, #0x38]` at the top of the open
            "titles": [
                {"title_id": 0x0004001000022000, "image_name": "banner_22000.bin"},
                {"title_id": 0x0004001000022100, "image_name": "banner_22100.bin"},
                {"title_id": 0x0004001000022200, "image_name": "banner_22200.bin"},
                {"title_id": 0x0004001000022300, "image_name": "banner_22300.bin"},
                {"title_id": 0x0004001000022800, "image_name": "banner_22800.bin"},
                {"title_id": 0x0004001000022E00, "image_name": "banner_22E00.bin"},
                # New 3DS ships Health and Safety as a title of its own, and its icon is the
                # one HOME Menu highlights there - the Old 3DS entry above never matches on
                # that console, and this one never matches on Old 3DS. Both stay listed.
                #
                # It reads the same file: the two banners hold the same nine language CGFX
                # byte for byte (only the common block, which no EUR language is ever drawn
                # with, differs), so there is nothing to rebuild for it. tools/build.py
                # writes one file per image name, not one per title.
                {"title_id": 0x0004001020022300, "image_name": "banner_22300.bin"},
            ],
        },
        # The built-in tips of the Notifications applet were copied into the news module's
        # savedata when they were delivered, so they keep whatever language the console was
        # set to then - see tools/news_tips.py. The hook rewrites them in place through the
        # news:s wrappers this title already carries; the only thing missing from the title
        # are the two setters, which _news_hook() marshals itself.
        "news_hook": {
            "site_off": 0xB4440,       # CheckTips(this, arg) - iterates all 17 tips
            "original_word": 0xE92D47F0,  # push {r4, r5, r6, r7, r8, sb, sl, lr}
            "return_to": 0xB4444,
            "get_header_off": 0x7FCAC,  # GetNotificationHeader(slot, buffer) -> result
            "get_message_off": 0x1295D8,  # GetMessage(label, archive) -> const u16*
            "open_news_off": 0x2DE28,   # srvGetServiceHandle(&handle, "news:s")
            "write_db_off": 0x7FB80,    # WriteNewsDBSavedata()
            "handle_va": 0x33D28C,      # where the title keeps its news:s session
            "set_header_cmd": 0x00070082,   # news:s SetNotificationHeader
            "set_message_cmd": 0x00080082,  # news:s SetNotificationMessage
            "slots": 100,               # the database holds 100, ids 0..99
            # First word of every function called above. An offset that has drifted lands on
            # something else, and the build says so instead of the console doing it.
            "expects": {
                "get_header_off": 0xE92D4008,   # push {r3, lr}
                "get_message_off": 0xE92D4010,  # push {r4, lr}
                "open_news_off": 0xE59F1004,    # ldr r1, [pc, #4] - a thunk, not a prologue
                "write_db_off": 0xE92D4010,     # push {r4, lr}
            },
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
    # Miiverse (cave), EUR, title version 4 - and the posting applet below. Verified working
    # on hardware: the closing message and the body of 015-5004 both come out Ukrainian. Both are the
    # StreetPass Mii Plaza case: Luma finds all five symbols in their own code, so no stub is
    # needed, but their accessInfo is 0x1 and 0x0 - no `DirectSdmc` - and the payload Luma
    # writes still has to open ARCHIVE_SDMC to read the replacement files. So each ships an
    # exheader and nothing else: no code.ips, no offsets, nothing tied to the build beyond
    # the version check.
    "000400300000BE02": {
        "title": "Miiverse (cave) EUR",
        "title_version": 4,
        "code_sha256": "dddda779b7398d6840263cf5be69796ce01a39bcba78708151ae325d2e0d7ba3",
        "kind": "exheader_only",
        # The error-message archive read: `ldr r3, =ARCHIVE_SAVEDATA_AND_CONTENT`, the last
        # argument the frame still needs before FSUSER_OpenFileDirectly. The archive path
        # buffer at sp+0x60 already holds {title id low, title id high} of whatever shared
        # archive is being read, which is what the hook compares - the EULA archive comes
        # through the same call and has to keep coming through untouched.
        # Miiverse draws its own error screens rather than going through the error applet,
        # so it needs its own copy of the hook - the reader function is the same SDK one,
        # byte for byte, at another address.
        #
        # Both blobs go past what Luma claims for itself, because LayeredFS *does* run for
        # this title: the payload takes the first 0x114 bytes of the .text padding and the
        # path string the first 48 of the .rodata padding.
        "msg_hook": {
            "site_off": 0xA07F8,
            "original_word": 0xE59F30DC,  # ldr r3, [pc, #0xdc]
            "return_to": 0xA07FC,
            "title_id_slot": 0x60,
            "titles": [{"title_id": 0x0004009B00012102, "image_name": "msg_romfs.bin"}],
            "stub_off": 0x28DB9C,   # .text padding 0x28DA88..0x28E000, past Luma's 0x114
            "stub_room": 1124,
            "rodata_off": 0x699D8,  # .rodata padding, past the 48 bytes Luma claims
        },
        # The clock line's weekday, the same case as `act` and the same one byte - see the
        # long note on `reader_policy` there. This applet shares the browser shell, so the
        # font open sits at the same place in the same function, only at another address, and
        # the reader jump table numbers its classes the same way: 0 is RomReader.
        #
        # Unlike `act` this needs no mount rename at all. `rom:` is the title's own romfs and
        # LayeredFS serves it unaided; the renaming there was only ever about reaching an
        # archive that belongs to no process.
        "reader_policy": (0x0AA260, b"\x04\x20\xa0\xe3", b"\x00\x20\xa0\xe3"),
    },
    "000400300000BA02": {
        "title": "Miiverse posting applet EUR",
        "title_version": 0,
        "code_sha256": "ad1608dd233fbef3e77f27185dbe8e8d81a9b45b58e5098e99d980d754c455d5",
        "kind": "exheader_only",
    },
    # Nintendo Network ID Settings (`act`), EUR, title version 3. Third title on the same
    # browser shell, and the same case again: Luma finds all five symbols in its own code,
    # accessInfo is 0x1 - no `DirectSdmc` - so an exheader and nothing else.
    #
    # It lives in 00040010, not among the applets: 1:/title/00040030 holds 22 titles on a
    # EUR console and none of them is `act`. The one that names it is System Settings, which
    # carries 000400100002C100 as a pair of literals in the pool at 0xD0F08.
    #
    # No `msg_hook` here, and that is a gap rather than a conclusion: like Miiverse this
    # title knows the shared archives - 0xE60C8 holds the table {12102, 12402, 12502,
    # 12602} - but whether it reads error text out of them itself, the way Miiverse does,
    # was never traced. If a smoke test turns up a Russian error body, that is where to
    # look; everything cave.msbt draws is Ukrainian either way.
    "000400100002C100": {
        "title": "Nintendo Network ID Settings (act) EUR",
        "title_version": 3,
        "code_sha256": "cc5422a94cdd348d08bf7d9818c9ac18ea27234aadddcf5d404390d152185745",
        "kind": "exheader_only",
        # The account screens - User Information, Password Settings, Change Mii, the sign-in
        # page, every dialog - are an HTML app: `index_<lang>.html` plus `js/`, `css/` and one
        # `json/message_<lang>.json` of 313 keyed strings. None of it is in this title. It
        # lives in the shared archive 0004001B00018002, which the title mounts as `content:`
        # (the scheme table at 0xE607C pairs `content:` with 0004001B00018002, `dll:` with
        # 0004001B00018202 and `msg:` with 0004009B000122xx). A mitmproxy capture of a full
        # walk through every tab settles it: thirteen requests, all XML API and one Mii
        # image, not a single HTML fetch. The pages are local.
        #
        # LayeredFS cannot reach that archive by title id - it redirects a *process's* reads,
        # and 0004001B00018002 has no process. But Luma's payload keys off the mount prefix
        # in the path, and it accepts one "update" prefix it finds in the title's own .text
        # among `ro2: rom2: rex: patch: ext:`. This title carries none of the five, so the
        # `content:` strings are renamed to `rex:` - the same trick the Instruction Manual
        # patch plays on `man:`, and with no prefix of Luma's to collide with. Every read
        # through the mount then looks for /luma/titles/<TID>/romfs/<path> first and falls
        # back to the real archive when the file is absent, so only the translated pages
        # ship. See build_nnid_html() and build_nnid_json() in tools/build.py.
        #
        # The mount name and the three URL scheme spellings and the URL template all move
        # together - the applet mounts under one and addresses the pages through the others.
        # Each replacement is padded with NULs to the original's length so nothing shifts.
        "mount_rename": [
            (0x07A82C, b"file:///content:/", b"file:///rex:/\0\0\0\0"),
            (0x0D5D5C, b"file:/content:", b"file:/rex:\0\0\0\0"),
            (0x0D5D6C, b"file://content:", b"file://rex:\0\0\0\0"),
            (0x0D5D7C, b"file:///content:", b"file:///rex:\0\0\0\0"),
            (0x0E6084, b"content:", b"rex:\0\0\0\0"),
        ],
        # The clock line's weekday. `hud.msbt` says `Нд`, and the console drew nothing: the
        # HUD font is a 67-glyph subset whose whole Cyrillic alphabet is `ВПСЧбнрст` - exactly
        # the seven Russian weekday abbreviations and not one letter more. `Н` and `д` are
        # absent, and no Ukrainian spelling of Sunday can be made from what is there.
        #
        # The mod already adds both glyphs to `Hud.bcfnt` (see build_hud_font), and all nine
        # copies of that font across the system are byte-identical - but this title's copy is
        # in neither its own romfs nor `content:`. It comes from `dll:`, and Luma serves one
        # update mount per title, already spent on `content:`.
        #
        # So the *reader* moves instead of the file. 0x10D180 is a jump table over the six
        # reader classes `sys::file` provides, each named outright by the RTTI behind its
        # vtable (typeinfo at vptr-4, its name one word in):
        #
        #   0  RomReader                          `rom:`, the title's own romfs
        #   1  SDReader                           the SD card, by absolute path
        #   2  DataPubReader
        #   3  SharedDataReader<MsgPolicy>        `msg:`
        #   4  SharedDataReader<DllPolicy>        `dll:`   <- the font open passes this
        #   5  SharedDataReader<ContentPolicy>    `content:`
        #
        # The open at 0x09BDE8 passes 4. Passing 0 reads `/font/Hud.bcfnt` from `rom:`, which
        # LayeredFS serves out of /luma/titles/<TID>/romfs/ - the folder the build already
        # writes the patched font into. One byte, no stub.
        #
        # Passing 5 was tried first and the applet died on a data abort at 0x2C, a null the
        # caller never checks: `content:` is not mounted yet when fonts load. `rom:` is - it
        # is the title's own, mounted before anything else runs.
        #
        # The real romfs has no `font/` directory, so there is no fallback behind this: the
        # build must always ship the font. build_hud_font() is what guarantees that.
        "reader_policy": (0x09BDD8, b"\x04\x20\xa0\xe3", b"\x00\x20\xa0\xe3"),
    },
    # Nintendo eShop, EUR, title version 29. The same case as StreetPass Mii Plaza and the
    # two Miiverse applets: Luma hooks the code unaided, but accessInfo is 0x240001
    # (CategorySysApplication, Shop, SeedDB - no `DirectSdmc`), so without this exheader the
    # payload Luma writes cannot open ARCHIVE_SDMC and the shipped romfs is never read.
    "0004001000022900": {
        "title": "Nintendo eShop EUR",
        "title_version": 29,
        "code_sha256": "34a50e03d648bd85f34c3e3acd00b8a67f18c002f994c9d3292966dbc14c58d7",
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
        # The error-message archive read: `ldr r3, =ARCHIVE_SAVEDATA_AND_CONTENT`, the last
        # argument the frame still needs before FSUSER_OpenFileDirectly. The archive path
        # buffer at sp+0x60 already holds {title id low, title id high} of whatever shared
        # archive is being read, which is what the hook compares - the EULA archive comes
        # through the same call and has to keep coming through untouched.
        # This applet draws the error screens for the whole system, so its copy of the hook
        # is the one that translates 009-1003 and every other code an application throws.
        # Verified working on hardware: 009-1003 out of the Plaza's update flow.
        "msg_hook": {
            "site_off": 0x3FFA4,
            "original_word": 0xE59F30DC,  # ldr r3, [pc, #0xdc]
            "return_to": 0x3FFA8,
            "title_id_slot": 0x60,
            "titles": [{"title_id": 0x0004009B00012102, "image_name": "msg_romfs.bin"}],
            # Behind the two romfs redirect stubs (36 bytes each) in the same .text padding.
            "stub_off": 0x55BD4,
            "stub_room": 1068,
            # Past error_romfs.bin's own path string at the front of the .rodata padding.
            "rodata_off": 0x7D48,
        },
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
    # Camera applet (the camera the HOME Menu opens on L+R), EUR, title version 2.
    # Verified working on hardware.
    #
    # The only Thumb-compiled title in this table, which decides everything about it:
    #
    #   - Luma's five signatures are ARM instruction words, so findLayeredFsSymbols() finds
    #     nothing here and never will. Planting ARM stubs would not help either - Luma hooks
    #     the title's *own* fsRegisterArchive/fsTryOpenFile so that the title's file opens
    #     land on the SD card, and this title's are Thumb functions at other addresses.
    #     LayeredFS is out; this goes the Download Play way instead.
    #   - Its FS wrappers build the IPC header at run time from (cmd id, normal, translate)
    #     in registers instead of loading a literal, so there is no 0x08030204 in .code to
    #     search for. The wrappers were found by walking the callers of svcSendSyncRequest
    #     (the ARM leaf `svc 0x32 ; bx lr` at 0x7EE1C) instead.
    #
    # Both ARCHIVE_ROMFS opens go through FSUSER_OpenFileDirectly at 0x7F068: the reader
    # behind "rom:" calls it at 0x2048, the second reader at 0xCF08. Neither the title's
    # three FSUSER_OpenArchive calls (archive 7 and 8, plus one generic wrapper) nor its
    # single FSUSER_OpenFile touch the RomFS, so those two sites are all of it.
    #
    # That wrapper's caller frame lays the arguments out exactly like the ARM titles above -
    # file path type at sp+0xC, pointer at sp+0x10, size at sp+0x14 - and the archive path
    # is already the empty one MakeEmptyPath() at 0x7F0F8 builds, which is what ARCHIVE_SDMC
    # wants too. The stub goes in the .text page padding; with no romfs/ folder shipped,
    # patchLayeredFs() returns early and Luma never claims any of it.
    "0004003000009902": {
        "title": "Camera applet EUR",
        "title_version": 2,
        "code_sha256": "948f1a67417e5b54f0793e8b9e639bd03210da71a4fbdc02ca1868556c8f551a",
        "kind": "romfs_from_sd",
        "encoding": "thumb",
        "image_name": "camera_applet_romfs.bin",
        "stub_off": 0xCB9F0,        # .text page padding, 0xCB9F0..0xCC000
        "stub_room": 1552,
        "sites": [{"patch_at": 0x02044}, {"patch_at": 0x0CF04}],
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
        # The Cyrillic keyboard is not something the MSBT can switch on by itself - see
        # _lang_swap_records().
        "lang_swap": {
            "russian": 12,              # EU_Russian in the title's own language order
            "languages": {"ru": 12, "en": 5},
            # `mov r0, r4 ; pop {r4, r5, r6, lr} ; b SetLanguage` - the tail of the routine
            # that turns the console's language and region into the applet's own index.
            "tail_call_off": 0x07E80,
            "set_language_off": 0x11D5C,  # SetLanguage(index): three instructions and a literal
            "set_language": [
                0xE59F1004,             # ldr r1, [pc, #4]   =0x1B773C
                0xE5810008,             # str r0, [r1, #8]   the language global, va 0x1B7744
                0xE12FFF1E,             # bx  lr
            ],
            "table_va": 0x1A0008,       # .rodata: one MSBT folder name per language index
            "folders": {5: "EU_English", 12: "EU_Russian"},
            "stub_off": 0x9F0BC,        # .text page padding, past the two redirect stubs
        },
    },
    # System Settings (mset), EUR, title version 12.
    #
    # Not a LayeredFS hook at all: Luma hooks this title unaided, its exheader already
    # grants DirectSdmc, and its romfs is replaced the ordinary way. This patch exists for
    # the one screen LayeredFS cannot reach - the country and region lists in Profile
    # settings, which do not live in this title's romfs. The code mounts a *shared data
    # archive* and reads them from there:
    #
    #     0xBED4  ldr r2, =0x00010402      \
    #     0xBED8  ldr r3, =0x0004009B       |  0x0004009B00010402, the `area` archive
    #     0xBEDC  ldr r0, ="area:"          |
    #     0xBEE8  bl  0x1C7C6C              /  MountByTitleId(name, tidLo, tidHi, ...)
    #     0xBEF4  ldr r0, =0x297900            the table of paths, one per console region
    #     0xBEFC  ldr r0, [r0, r1, lsl #2]     "area:/EU/country_LZ.bin"
    #     0xBF04  bl  0x1C7BB4                 load the whole file
    #     0xBF10  bl  0x1C7A54                 Unmount("area:")
    #
    # LayeredFS redirects a title's own romfs and nothing else, so `area:` is out of its
    # reach. What is in reach is the mount itself: the title already carries
    #
    #     0x1A1654  MountSdmc(const char *name)   mov r1, #9 (ARCHIVE_SDMC); OpenArchive;
    #                                             register under `name`
    #
    # used seventeen times for its own SD access, and it takes the mount name in r0 - which
    # is what both `area:` sites already have there. So the whole patch is to retarget two
    # `bl` instructions from MountByTitleId to MountSdmc, after which `area:/...` resolves
    # against the SD card, and to repoint the path tables at strings under
    # /luma/titles/0004001000022000/area/. The tid loads into r2/r3 become dead; the stack
    # arguments the caller writes are ignored; the unmount is the same call either way.
    #
    # Both path tables are repointed for every console region, not just EU: the mount is
    # unconditional, so a console reporting any other region has to find its files on the
    # SD card too. The build ships the whole dumped archive, so it does.
    "0004001000022000": {
        "title": "System Settings (mset) EUR",
        "title_version": 12,
        "code_sha256": "3dbb076b95304d3612b7b746a2927576b84bd83bd2b2db9f71c41cf732737cec",
        "kind": "area_from_sd",
        # .text offsets, like every other patch here: va 0x1C7C6C and va 0x1A1654.
        "mount_by_title_id": 0x0C7C6C,
        "mount_sdmc": 0x0A1654,
        "mount_sites": [0x0BEE8, 0x942C4],  # the country list and the region list
        # Two tables of 7 pointers in .data, indexed by console region. EU appears twice -
        # Nintendo's own duplicate - and both entries are repointed.
        "path_tables": {
            "country": (0x197900, "country_LZ.bin"),
            "region": (0x19791C, "%d_LZ.bin"),
        },
        "path_regions": ["JP", "US", "EU", "EU", "CN", "KR", "TW"],
        "sd_dir": "/luma/titles/0004001000022000/area",
        # .rodata page padding: ro ends at 0x1924F0 and the page at 0x193000. Luma claims
        # the first 48 bytes for its own LayeredFS path, so the strings start past that.
        "rodata_padding_off": 0x1924F0,
        "rodata_padding_room": 0xB10,
        # Data Management lists every installed title by name, and those names are not in
        # this title's romfs either: it reads each one's SMDH itself, out of `ExeFS:/icon` in
        # NAND, which LayeredFS cannot reach. So the read is hooked and the buffer's slot for
        # the language this build replaces is overwritten - the same table and the same
        # routine HOME Menu's patch uses, see SMDH_NAMES there.
        #
        # One reader, two thunks, ten call sites, and no cache of any kind (the only 'cache'
        # in the image is an SDK log string, and every consumer allocates 0x36C0 bytes and
        # reads afresh - unlike HOME Menu, whose Cache.dat needed a second hook):
        #
        #   1B10BC  the reader: builds the ARCHIVE_SAVEDATA_AND_CONTENT path from the title
        #           id and pulls all 0x36C0 bytes of `icon` in. r0 = buffer, r2/r3 = title
        #           id, and the mediatype is a fifth argument at [sp, #0x38] - the wrinkle
        #           `stack_arg` exists for. Its failure paths hand back 0xC8804631/0xC8804632,
        #           the same pair HOME Menu's copy of this SDK routine returns.
        #   19AC04  thunk, mediatype 1 (NAND): push {r3, lr}; mov ip, #1; str ip, [sp]; bl
        #   1A13D0  thunk, mediatype 0 (SD card and cartridges): the same five instructions
        #
        # Hooking the two `bl`s inside the thunks covers all ten sites at once. The table is
        # keyed by title id, so the SD-card and cartridge names the second thunk fetches are
        # left exactly as they are.
        "smdh_hook": {
            "thunks": [0x9AC04, 0xA13D0],  # the `bl` this hook takes over is 12 bytes in
            "reader_off": 0xB10BC,
            "stack_arg": True,
            "reads": "the Data Management SMDH reads",
            "effect": "the software list names titles the way the HOME Menu does",
        },
    },
}

# Stack layout the OpenFileDirectly wrapper reads its arguments from, shared by both sites.
FILE_PATH_TYPE_SLOT = 0x0C
FILE_PATH_PTR_SLOT = 0x10
FILE_PATH_SIZE_SLOT = 0x14
ARCHIVE_SDMC = 9
NOP = 0xE1A00000  # mov r0, r0
PATH_ASCII = 3
PATH_EMPTY = 1
ORIGINAL_SITE_WORD = 0xE3A03003  # mov r3, #3  -> the ARCHIVE_ROMFS each site starts from

# A Thumb title cannot spare a single 16-bit instruction for a branch, so its sites are the
# last two instructions before the call instead of the `mov r3, #3`, and the stub reproduces
# the second one. Both sites of the Camera applet hold the same pair.
ORIGINAL_THUMB_SITE_WORD = 0x94079505  # str r5, [sp, #0x14] ; str r4, [sp, #0x1c]
THUMB_STORE_ATTRIBUTES = 0x9407        # str r4, [sp, #0x1c] - the displaced instruction

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


COND_EQ, COND_NE, COND_MI = 0x0, 0x1, 0x4


def _bc(cond: int, src: int, dst: int) -> int:
    return (cond << 28) | 0x0A000000 | (((dst - src - 8) >> 2) & 0xFFFFFF)


def _blc(cond: int, src: int, dst: int) -> int:
    return (cond << 28) | 0x0B000000 | (((dst - src - 8) >> 2) & 0xFFFFFF)


def _thumb_bl(src: int, dst: int) -> bytes:
    """Thumb-1 `bl` pair. Range is +-4 MB, which every site here is well inside of."""
    offset = dst - (src + 4)
    if not -(1 << 22) <= offset < (1 << 22) or offset & 1:
        raise ValueError(f"0x{src:X} -> 0x{dst:X} is not a reachable Thumb bl")
    hi = 0xF000 | ((offset >> 12) & 0x7FF)
    lo = 0xF800 | ((offset >> 1) & 0x7FF)
    return struct.pack("<HH", hi, lo)


def _thumb_bl_target(data: bytes, src: int) -> int | None:
    hi, lo = struct.unpack("<HH", data)
    if hi & 0xF800 != 0xF000 or lo & 0xF800 != 0xF800:
        return None
    offset = ((hi & 0x7FF) << 12) | ((lo & 0x7FF) << 1)
    if offset & (1 << 22):
        offset -= 1 << 23
    return src + 4 + offset


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


def _news_hook(patch: dict, entries: list[dict], base: int) -> tuple[list[int], dict[str, int]]:
    """Rewrite the notifications the HOME Menu delivered before the mod into Ukrainian.

    The built-in tips live in the news module's NAND savedata, copied there once by
    AddNotification, so LayeredFS never sees them - see tools/news_tips.py for why. This
    hook wraps the tip dispatcher, the function that decides which tips are due, because
    that is a place where the message archives are loaded for certain: the dispatcher is
    about to look tip text up itself.

    One pass over all 100 slots per call. For each slot: read the 0x70 header, hash the
    stored title, and on a table hit ask HOME Menu's own message lookup for our text. The
    lookup answers in the console's language and resolves the model suffix (`_flw`, `_sac`,
    `_jan`) on its own, which is why the table stores plain `new_tipsN` labels and the patch
    carries no Ukrainian text of its own.

    Nothing is written unless the Ukrainian title the lookup returned is the one this build
    shipped, so a console running in English is left alone. After a rewrite the stored title
    is Ukrainian and hashes to nothing in the table, which is what keeps the next pass from
    touching it again - no marker anywhere, and removing the mod leaves the console with
    Ukrainian notifications rather than a broken database.
    """
    hook = patch["news_hook"]
    slots = hook["slots"]

    def bl(target: str):
        return lambda at, labels: _bl(at, labels[target])

    def b(target: str):
        return lambda at, labels: _b(at, labels[target])

    def bc(cond: int, target: str):
        return lambda at, labels: _bc(cond, at, labels[target])

    def call(key: str):
        return lambda at, labels: _bl(at, hook[key])

    def ldr_pc(reg: int, target: str):
        return lambda at, labels: 0xE59F0000 | (reg << 12) | (labels[target] - at - 8)

    table: list[int] = []
    for entry in entries:
        table += [
            entry["ru_hash"],
            lambda at, labels, e=entry: TEXT_VA + labels[f"news_body_{e['number']}"],
            lambda at, labels, e=entry: TEXT_VA + labels[f"news_title_{e['number']}"],
            entry["ua_hash"],
        ]
    table.append(0)  # a zero hash ends the walk

    blocks: dict[str, list] = {
        # Entered in place of the dispatcher's own prologue, so its arguments are still in
        # r0/r1 and lr is still its caller. They are put back before the prologue runs.
        "news_hook": [
            0xE92D500F,                              # push  {r0, r1, r2, r3, ip, lr}
            bl("news_fix"),                          # bl    news_fix
            0xE8BD500F,                              # pop   {r0, r1, r2, r3, ip, lr}
            hook["original_word"],                   # the dispatcher's own prologue
            lambda at, labels: _b(at, hook["return_to"]),
        ],
        "news_fix": [
            0xE92D41F0,                              # push  {r4, r5, r6, r7, r8, lr}
            0xE24DD070,                              # sub   sp, sp, #0x70    the header buffer
            ldr_pc(0, "news_handle"),                # ldr   r0, [pc, #...]   &news:s handle
            0xE5900000,                              # ldr   r0, [r0]
            0xE3500000,                              # cmp   r0, #0
            lambda at, labels: _blc(COND_EQ, at, hook["open_news_off"]),  # bleq  open news:s
            ldr_pc(0, "news_handle"),                # ldr   r0, [pc, #...]
            0xE5900000,                              # ldr   r0, [r0]
            0xE3500000,                              # cmp   r0, #0
            bc(COND_EQ, "news_out"),                 # beq   out              no session
            0xE3A04000,                              # mov   r4, #0           slot index
            0xE3A08000,                              # mov   r8, #0           anything written
        ],
        "news_loop": [
            0xE1A00004,                              # mov   r0, r4
            0xE1A0100D,                              # mov   r1, sp
            call("get_header_off"),                   # bl    GetNotificationHeader(idx, buf)
            0xE3500000,                              # cmp   r0, #0
            bc(COND_MI, "news_next"),                # bmi   next             no such slot
            0xE5DD0000,                              # ldrb  r0, [sp]         valid flag
            0xE3500000,                              # cmp   r0, #0
            bc(COND_EQ, "news_next"),                # beq   next             free slot
            0xE28D0030,                              # add   r0, sp, #0x30    the stored title
            bl("news_hash"),                         # bl    hash
            ldr_pc(5, "news_table_ptr"),             # ldr   r5, [pc, #...]   the table
        ],
        "news_walk": [
            0xE5951000,                              # ldr   r1, [r5]         entry hash
            0xE3510000,                              # cmp   r1, #0
            bc(COND_EQ, "news_next"),                # beq   next             end of table
            0xE1510000,                              # cmp   r1, r0
            bc(COND_EQ, "news_match"),               # beq   match
            0xE2855010,                              # add   r5, r5, #16
            b("news_walk"),                          # b     walk
        ],
        # The title is fetched first and checked against the hash this build shipped: it is
        # the gate that keeps a console set to another language untouched.
        "news_match": [
            0xE5950008,                              # ldr   r0, [r5, #8]     title label
            0xE3A01000,                              # mov   r1, #0           menu_msbt
            call("get_message_off"),                  # bl    GetMessage -> const u16*
            0xE3500000,                              # cmp   r0, #0
            bc(COND_EQ, "news_next"),                # beq   next
            0xE1A07000,                              # mov   r7, r0           keep the title
            bl("news_hash"),                         # bl    hash
            0xE595100C,                              # ldr   r1, [r5, #0xc]   expected hash
            0xE1500001,                              # cmp   r0, r1
            bc(COND_NE, "news_next"),                # bne   next             not our text
            0xE5950004,                              # ldr   r0, [r5, #4]     body label
            0xE3A01000,                              # mov   r1, #0
            call("get_message_off"),                  # bl    GetMessage
            0xE3500000,                              # cmp   r0, #0
            bc(COND_EQ, "news_next"),                # beq   next
            0xE1A06000,                              # mov   r6, r0           keep the body
            bl("news_len"),                          # bl    len              -> bytes with NUL
            0xE1A02000,                              # mov   r2, r0
            0xE1A01006,                              # mov   r1, r6
            0xE1A00004,                              # mov   r0, r4
            bl("news_set_message"),                  # bl    SetNotificationMessage
            0xE3500000,                              # cmp   r0, #0
            bc(COND_MI, "news_next"),                # bmi   next             leave the title
            0xE28D1030,                              # add   r1, sp, #0x30    the header field
            0xE3A0201F,                              # mov   r2, #31          units it holds
            0xE1A00007,                              # mov   r0, r7
        ],
        "news_copy": [
            0xE0D030B2,                              # ldrh  r3, [r0], #2
            0xE3530000,                              # cmp   r3, #0
            bc(COND_EQ, "news_copied"),              # beq   copied
            0xE0C130B2,                              # strh  r3, [r1], #2
            0xE2522001,                              # subs  r2, r2, #1
            bc(COND_NE, "news_copy"),                # bne   copy
        ],
        "news_copied": [
            0xE3A03000,                              # mov   r3, #0
            0xE1C130B0,                              # strh  r3, [r1]         terminate
            0xE1A00004,                              # mov   r0, r4
            0xE1A0100D,                              # mov   r1, sp
            bl("news_set_header"),                   # bl    SetNotificationHeader
            0xE3A08001,                              # mov   r8, #1
        ],
        "news_next": [
            0xE2844001,                              # add   r4, r4, #1
            0xE3540000 | slots,                      # cmp   r4, #100
            bc(COND_NE, "news_loop"),                # bne   loop
            0xE3580000,                              # cmp   r8, #0
            lambda at, labels: _blc(COND_NE, at, hook["write_db_off"]),  # blne  flush the db
        ],
        "news_out": [
            0xE28DD070,                              # add   sp, sp, #0x70
            0xE8BD81F0,                              # pop   {r4, r5, r6, r7, r8, pc}
        ],
        # hash(r0 = UTF-16 string) -> r0. h = h * 31 + unit, the same two instructions
        # tools/news_tips.py hashes with.
        "news_hash": [
            0xE3A01000,                              # mov   r1, #0           the hash
            0xE1A02000,                              # mov   r2, r0
        ],
        "news_hash_loop": [
            0xE0D230B2,                              # ldrh  r3, [r2], #2
            0xE3530000,                              # cmp   r3, #0
            0x10611281,                              # rsbne r1, r1, r1, lsl #5   h * 31
            0x10811003,                              # addne r1, r1, r3
            bc(COND_NE, "news_hash_loop"),           # bne   hash_loop
            0xE1A00001,                              # mov   r0, r1
            0xE12FFF1E,                              # bx    lr
        ],
        # len(r0 = UTF-16 string) -> r0 = its size in bytes, terminator included.
        "news_len": [
            0xE1A01000,                              # mov   r1, r0
        ],
        "news_len_loop": [
            0xE0D120B2,                              # ldrh  r2, [r1], #2
            0xE3520000,                              # cmp   r2, #0
            bc(COND_NE, "news_len_loop"),            # bne   len_loop
            0xE0410000,                              # sub   r0, r1, r0
            0xE12FFF1E,                              # bx    lr
        ],
        "news_set_message": [
            ldr_pc(3, "news_message_cmd"),           # ldr   r3, [pc, #...]
            b("news_ipc"),                           # b     ipc              keeps lr
        ],
        "news_set_header": [
            0xE3A02070,                              # mov   r2, #0x70
            ldr_pc(3, "news_header_cmd"),            # ldr   r3, [pc, #...]
            b("news_ipc"),                           # b     ipc
        ],
        # ipc(r0 = slot, r1 = buffer, r2 = size, r3 = command header) -> r0 = result.
        # Written the way this title writes its own news:s calls, down to the descriptor:
        # 0xA is a read-only mapped buffer, which is what every setter here passes. The TLS
        # base goes in a callee-saved register because the kernel does not promise ip back.
        "news_ipc": [
            0xE92D4080,                              # push  {r7, lr}
            0xEE1D7F70,                              # mrc   p15, #0, r7, c13, c0, #3
            0xE5A73080,                              # str   r3, [r7, #0x80]! -> cmdbuf
            0xE2873004,                              # add   r3, r7, #4
            0xE8830005,                              # stm   r3, {r0, r2}     slot, size
            0xE3A0000A,                              # mov   r0, #0xa
            0xE1800202,                              # orr   r0, r0, r2, lsl #4
            0xE1C700FC,                              # strd  r0, r1, [r7, #0xc]
            ldr_pc(0, "news_handle"),                # ldr   r0, [pc, #...]
            0xE5900000,                              # ldr   r0, [r0]
            0xEF000032,                              # svc   #0x32            SendSyncRequest
            0xE5970004,                              # ldr   r0, [r7, #4]     the result
            0xE8BD8080,                              # pop   {r7, pc}
        ],
        "news_handle": [
            hook["handle_va"],                       # literal
        ],
        "news_table_ptr": [
            lambda at, labels: TEXT_VA + labels["news_table"],
        ],
        "news_message_cmd": [
            hook["set_message_cmd"],
        ],
        "news_header_cmd": [
            hook["set_header_cmd"],
        ],
        "news_table": table,
    }
    for entry in entries:
        blocks[f"news_body_{entry['number']}"] = _ascii_words(str(entry["body_label"]))
        blocks[f"news_title_{entry['number']}"] = _ascii_words(str(entry["title_label"]))
    return _assemble(blocks, base)


def _ascii_words(text: str) -> list[int]:
    """A NUL-terminated ASCII string as words, so it can share a blob with code."""
    raw = text.encode("ascii") + b"\0"
    raw += b"\0" * (-len(raw) % 4)
    return list(struct.unpack(f"<{len(raw) // 4}I", raw))


def _banner_hook(
    patch: dict, entries: list[dict], base: int, hook_key: str = "banner_hook"
) -> tuple[list[int], dict[str, int]]:
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
    hook = patch[hook_key]
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
    lang_index = variant.current().smdh_index
    short_at, long_at = smdh_names.slot_offsets(lang_index)
    page, short_low, long_low = short_at & ~0xFF, short_at & 0xFF, long_at & 0xFF
    if long_at & ~0xFF != page:
        raise RuntimeError(f"slot {lang_index} spans two immediate pages")

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
    } | _smdh_rewrite_blocks(lang_index, table_va)
    return _assemble(blocks, base)


def _smdh_rewrite_blocks(lang_index: int, table_va: int) -> dict[str, list]:
    """rewrite(r0 = SMDH buffer, r1 = title id low, r2 = title id high), plus its table.

    Replaces the short and long description of the one language slot the mod overwrites,
    for the title the buffer belongs to; a title the table does not list is left alone.

    Two hooks share it. HOME Menu reads every title's SMDH for the names it labels icons
    with, and the Instruction Manual reads the documented title's SMDH for the name it
    prints above the page - the same strings, out of the same structure, so the same
    routine serves both.
    """
    short_at, long_at = smdh_names.slot_offsets(lang_index)
    page, short_low, long_low = short_at & ~0xFF, short_at & 0xFF, long_at & 0xFF
    if long_at & ~0xFF != page:
        raise RuntimeError(f"slot {lang_index} spans two immediate pages")

    def b(target: str):
        return lambda at, labels: _b(at, labels[target])

    def bc(cond: int, target: str):
        return lambda at, labels: _bc(cond, at, labels[target])

    def ldr_pc(reg: int, target: str):
        return lambda at, labels: 0xE59F0000 | (reg << 12) | (labels[target] - at - 8)

    return {
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


def _smdh_hook(patch: dict, table_va: int, base: int) -> tuple[list[int], dict[str, int]]:
    """An SMDH reader wrapped around the same `rewrite`, for the titles that read one.

    ebird reads the documented title's `ExeFS:/icon` once per manual - the call at
    smdh_hook["site_off"] - and the buffer it fills is where both the wrench icon in the
    corner and the name across the top of the page come from. There is no icon cache here,
    so one hook is the whole job.

    The reader is entered with r0 = buffer, r1 = mediatype, r2/r3 = the title id and takes
    nothing off the stack, so unlike HOME Menu's thunk it can simply be called: the wrapper
    keeps the three registers it needs, makes the call the site used to make, and hands the
    buffer to `rewrite` when the read came back non-negative - the same test the caller
    itself applies to the result.

    System Settings takes the same shape with one wrinkle: its reader wants the mediatype in
    a *fifth* argument, on the stack, and its two thunks are what put it there. A wrapper
    that pushed anything would move the word out from under the reader's `ldr r4, [sp, #0x38]`,
    so with smdh_hook["stack_arg"] the wrapper carries the word across its own frame and
    hands it over the way the thunk did.
    """
    hook = patch["smdh_hook"]
    stack_arg = hook.get("stack_arg")

    def bl(target: str):
        return lambda at, labels: _bl(at, labels[target])

    def bc(cond: int, target: str):
        return lambda at, labels: _bc(cond, at, labels[target])

    blocks = {
        "icon_hook": [
            0xE92D400D,                          # push  {r0, r2, r3, lr}   buffer, title id
        ] + ([
            0xE59DC010,                          # ldr   ip, [sp, #0x10]    the thunk's arg
            0xE24DD008,                          # sub   sp, sp, #8         8-byte aligned
            0xE58DC000,                          # str   ip, [sp]           where the reader looks
        ] if stack_arg else []),
        "icon_call": [
            lambda at, labels: _bl(at, hook["reader_off"]),  # bl the reader the site called
        ] + ([
            0xE28DD008,                          # add   sp, sp, #8
        ] if stack_arg else []) + [
            0xE3500000,                          # cmp   r0, #0
            bc(COND_MI, "icon_out"),             # bmi   icon_out           the read failed
            # Two registers, not one: the result has to survive `rewrite` and the stack has
            # to stay 8-byte aligned across the call. ip is free at both ends.
            0xE92D1001,                          # push  {r0, ip}           keep the result
            0xE59D0008,                          # ldr   r0, [sp, #8]       buffer
            0xE59D100C,                          # ldr   r1, [sp, #0xc]     title id low
            0xE59D2010,                          # ldr   r2, [sp, #0x10]    title id high
            bl("rewrite"),                       # bl    rewrite
            0xE8BD1001,                          # pop   {r0, ip}
        ],
        "icon_out": [
            0xE28DD00C,                          # add   sp, sp, #12
            0xE8BD8000,                          # pop   {pc}
        ],
    } | _smdh_rewrite_blocks(variant.current().smdh_index, table_va)
    return _assemble(blocks, base)


def _smdh_hook_sites(hook: dict) -> list[int]:
    """The `bl` instructions the wrapper takes over - one in ebird, two in System Settings.

    ebird names its site outright. System Settings names the thunks instead, because that is
    what the shape check below is about, and the call is always the fourth instruction in.
    """
    if "thunks" in hook:
        return [thunk + THUNK_CALL_OFFSET for thunk in hook["thunks"]]
    return [hook["site_off"]]


def _verify_smdh_thunks(hook: dict, code: bytes) -> None:
    """Each thunk is push {r3, lr}; mov ip, #mediatype; str ip, [sp]; bl reader; pop {r3, pc}.

    The wrapper's whole stack-argument dance rests on that `str ip, [sp]`, so an offset that
    has drifted onto some other function has to fail the build rather than reach a console.
    """
    for thunk in hook.get("thunks", []):
        words = struct.unpack_from("<5I", code, thunk)
        shape = (
            words[0] == ORIGINAL_THUNK_WORD
            and words[1] & ~0xFF == THUNK_SET_MEDIATYPE
            and words[2] == THUNK_STORE_MEDIATYPE
            and words[4] == THUNK_RETURN_WORD
        )
        if not shape:
            raise RuntimeError(
                f"0x{thunk:X} is not one of the SMDH thunks the offsets were taken from: "
                + " ".join(f"0x{word:08X}" for word in words)
            )


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


def area_sd_paths(patch: dict) -> dict[str, str]:
    """The SD path behind each `area:` file, keyed by "<region>/<file>"."""
    paths = {}
    for _, filename in patch["path_tables"].values():
        for region in dict.fromkeys(patch["path_regions"]):
            paths[f"{region}/{filename}"] = f"area:{patch['sd_dir']}/{region}/{filename}"
    return paths


def _generate_area_from_sd(
    patch: dict, code: bytes, exheader: bytes, version: int, table: bytes | None = None
) -> tuple[dict[str, bytes], list[str]]:
    """Point the `area:` mount and its path tables at the SD card.

    Nothing is executed that was not already there: two `bl` instructions change target
    from MountByTitleId to the title's own MountSdmc, and fourteen pointers in .data change
    to strings written into the .rodata padding. Every one of those is checked against the
    dump first and re-read out of the patched image afterwards, because an IPS applied at
    the wrong offset would leave System Settings mounting garbage.

    The SMDH name hook rides along in the same two paddings when the title has one: its
    table goes past the `area:` strings in .rodata, its wrapper at the end of the .text
    padding, so Luma's payload keeps the front of both.
    """
    for site in patch["mount_sites"]:
        expected = _bl(site, patch["mount_by_title_id"])
        found = struct.unpack_from("<I", code, site)[0]
        if found != expected:
            raise RuntimeError(
                f"0x{site:X} holds 0x{found:08X}, not the bl 0x{patch['mount_by_title_id']:X} "
                f"(0x{expected:08X}) the patch replaces"
            )

    padding = patch["rodata_padding_off"]
    room = patch["rodata_padding_room"]
    if any(code[padding:padding + room]):
        raise RuntimeError(f"the .rodata padding at 0x{padding:X} is not free")

    # Luma writes its own "lf:/luma/titles/<TID>/romfs" at the front of this padding after
    # the IPS is applied, so start past it.
    at = padding + LUMA_PATH_SIZE
    blobs: list[tuple[int, bytes]] = []
    string_va: dict[str, int] = {}
    for key, path in area_sd_paths(patch).items():
        encoded = path.encode("ascii") + b"\0"
        string_va[key] = TEXT_VA + at
        blobs.append((at, encoded))
        at += len(encoded)
    if at > padding + room:
        raise RuntimeError(f"the paths need {at - padding} bytes, only {room} are free")

    records = list(blobs)
    for table_off, filename in patch["path_tables"].values():
        for index, region in enumerate(patch["path_regions"]):
            records.append((table_off + index * 4, struct.pack("<I", string_va[f"{region}/{filename}"])))
    for site in patch["mount_sites"]:
        records.append((site, struct.pack("<I", _bl(site, patch["mount_sdmc"]))))

    _verify_area(patch, code, records, string_va)

    log = [
        f"{patch['title']} title version {version}",
        f"code.ips: {len(patch['mount_sites'])} `area:` mounts retargeted to MountSdmc at "
        f"0x{patch['mount_sdmc']:X}, so the country and region lists come off the SD card",
        f"code.ips: {len(patch['path_regions']) * len(patch['path_tables'])} path pointers "
        f"repointed at {len(string_va)} strings in the .rodata padding "
        f"({at - padding - LUMA_PATH_SIZE} bytes of {room - LUMA_PATH_SIZE} free)",
    ]
    if patch.get("smdh_hook"):
        log += _place_smdh_hook(
            patch, code, exheader, table, at,
            patch["rodata_padding_off"] + patch["rodata_padding_room"], records,
        )
    return {"code.ips": make_ips(records)}, log


def _place_smdh_hook(
    patch: dict, code: bytes, exheader: bytes, table: bytes | None, rodata_at: int,
    padding_end: int, records: list
) -> list[str]:
    """Place the SMDH name hook in the paddings another patch of the same title has left over.

    Two titles come through here: System Settings, whose `area:` paths take the front of the
    .rodata padding, and New 3DS Health and Safety, whose romfs path takes one line of it.
    `rodata_at` is where that patch stopped writing and `padding_end` where the padding ends.

    Neither address is a constant, because both depend on what the build ships: the table
    grows with src/app_names.json and the wrapper is laid out twice, once to learn its own
    length. So the offsets are computed here and checked against the padding, rather than
    written down in the config where they would drift silently.
    """
    if not table:
        raise RuntimeError(f"{patch['title']} needs an SMDH name table and none was built")

    hook = patch["smdh_hook"] = dict(patch["smdh_hook"])  # a copy: HOOK_PATCHES is shared
    _verify_smdh_thunks(hook, code)

    rounded = lambda value: (value + 0xFFF) & ~0xFFF  # noqa: E731
    text_size = struct.unpack_from("<I", exheader, TEXT_SIZE_OFFSET)[0]

    # The wrapper goes at the end of the .text padding, leaving the front to Luma's payload.
    # Its length is known before its address is, so it is laid out twice - the same two-pass
    # shape _generate_smdh_names() uses.
    hook["rodata_off"] = rodata_at + -rodata_at % 4  # a word-aligned table, past the paths
    hook["rodata_room"] = padding_end - hook["rodata_off"]
    sizing, _ = _smdh_hook(patch, TEXT_VA + hook["rodata_off"], 0)
    hook["stub_off"] = rounded(text_size) - len(sizing) * 4
    hook["stub_room"] = len(sizing) * 4
    if hook["stub_off"] < text_size + LUMA_PAYLOAD_SIZE:
        raise RuntimeError(
            f"the wrapper needs {len(sizing) * 4} bytes and the .text padding has "
            f"{rounded(text_size) - text_size - LUMA_PAYLOAD_SIZE} past Luma's payload"
        )

    return _smdh_hook_records(patch, code, table, records)


def _verify_area(patch: dict, code: bytes, records: list[tuple[int, bytes]], string_va: dict[str, int]) -> None:
    """Apply the records and read the result back the way the console would."""
    patched = bytearray(code)
    for offset, data in records:
        patched[offset:offset + len(data)] = data
    word = lambda off: struct.unpack_from("<I", patched, off)[0]  # noqa: E731

    for site in patch["mount_sites"]:
        target = _bl_target(word(site), site)
        if target != patch["mount_sdmc"]:
            raise RuntimeError(f"site 0x{site:X} calls 0x{target:X}, expected MountSdmc")

    expected = area_sd_paths(patch)
    for table_off, filename in patch["path_tables"].values():
        for index, region in enumerate(patch["path_regions"]):
            key = f"{region}/{filename}"
            va = word(table_off + index * 4)
            if va != string_va[key]:
                raise RuntimeError(f"path table entry {index} does not point at {key}")
            off = va - TEXT_VA
            end = patched.index(b"\0", off)
            if patched[off:end].decode("ascii") != expected[key]:
                raise RuntimeError(f"the string behind {key} is not {expected[key]!r}")

    # MountSdmc takes the mount name in r0 and nothing else, so the sites must still be
    # loading "area:" into r0 - the whole patch rests on that argument being untouched.
    for site in patch["mount_sites"]:
        loads_r0 = any(
            word(at) & 0xFFFFF000 == 0xE59F0000
            for at in range(site - 0x20, site, 4)
        )
        if not loads_r0:
            raise RuntimeError(f"site 0x{site:X} does not load a mount name into r0")


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


def wants_news_tips(tid: str) -> bool:
    """Whether this title's patch rewrites the built-in notifications, and so needs the table."""
    return bool(HOOK_PATCHES.get(tid.upper(), {}).get("news_hook"))


def smdh_table_key(patch: dict) -> str:
    """Which of the two SMDH name tables a hook looks its title up in.

    The manual viewer needs one row per title it documents, so it reads the table built from
    the viewer's own list. A title that documents itself - New 3DS Health and Safety - needs
    only its own rows, and the shared table has no room to spare for them: the viewer's two
    tables sit in one 1064-byte window of padding. So `titles` in the hook config gets its
    own table, in padding of its own.
    """
    return "smdh_self" if patch["smdh_hook"].get("titles") else "smdh_manual"


def smdh_self_titles() -> list[str]:
    """Every title id the self-documenting hooks look up, for tools/build.py to tabulate."""
    return [
        tid
        for patch in HOOK_PATCHES.values()
        if patch.get("smdh_hook", {}).get("titles")
        for tid in patch["smdh_hook"]["titles"]
    ]


def wants_names(tid: str) -> str | None:
    """Which application-name table this title's patch needs, if any."""
    patch = HOOK_PATCHES.get(tid.upper())
    if patch is None:
        return None
    if patch.get("kind") == "smdh_names":
        return "smdh"
    if patch.get("smdh_hook"):
        return smdh_table_key(patch)
    return "pane" if patch.get("pane_hook") else None


def _thumb_redirect_records(
    patch: dict, path_va: int, path_off: int, sd_path: str
) -> list[tuple[int, bytes]]:
    """The same redirect for a Thumb title, entered with `bl` and left with `bx lr`.

    One stub serves every site: they all reach the same OpenFileDirectly wrapper, whose
    caller frame keeps the file path in the slots below, and they all displace the same
    `str r4, [sp, #0x1c]`. `bl` clobbers lr, which is free here - the call the sites are
    about to make would overwrite it anyway.
    """
    encoded = sd_path.encode("ascii") + b"\0"
    stub = patch["stub_off"]
    if stub % 4:
        raise RuntimeError(f"stub at 0x{stub:X} must be word-aligned for its literal")
    if len(encoded) > 0xFF:
        raise RuntimeError(f"path is {len(encoded)} bytes, `movs r3, #imm8` tops out at 255")

    halfwords = [
        0x2300 | PATH_ASCII,                        # +00  movs r3, #3
        0x9300 | (FILE_PATH_TYPE_SLOT >> 2),        # +02  str  r3, [sp, #0xc]
        0x4B03,                                     # +04  ldr  r3, [pc, #0xc]   the path
        0x9300 | (FILE_PATH_PTR_SLOT >> 2),         # +06  str  r3, [sp, #0x10]
        0x2300 | len(encoded),                      # +08  movs r3, #len (with the NUL)
        0x9300 | (FILE_PATH_SIZE_SLOT >> 2),        # +0A  str  r3, [sp, #0x14]
        THUMB_STORE_ATTRIBUTES,                     # +0C  str  r4, [sp, #0x1c]
        0x2300 | ARCHIVE_SDMC,                      # +0E  movs r3, #9
        0x4770,                                     # +10  bx   lr
        0x0000,                                     # +12  pad to the literal's word
    ]
    blob = b"".join(struct.pack("<H", h) for h in halfwords) + struct.pack("<I", path_va)
    if len(blob) > patch["stub_room"]:
        raise RuntimeError(f"stub needs {len(blob)} bytes, only {patch['stub_room']} are free")

    records = [(path_off, encoded), (stub, blob)]
    for site in patch["sites"]:
        records.append((site["patch_at"], _thumb_bl(site["patch_at"], stub)))
    return records


def _redirect_records(patch: dict, path_va: int, path_off: int, sd_path: str) -> list[tuple[int, bytes]]:
    """IPS records that make every ARCHIVE_ROMFS open read an image off the SD card.

    Each site is `mov r3, #3` immediately before the OpenFileDirectly call, with the file
    path already laid out on the stack. The site branches to a stub that swaps in
    ARCHIVE_SDMC and an ASCII path, then branches back to the next instruction.
    """
    if patch.get("encoding") == "thumb":
        return _thumb_redirect_records(patch, path_va, path_off, sd_path)

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


def _hooked_text_words(patch: dict) -> list[int]:
    """Offsets inside .text that a patch overwrites with a branch into a stub.

    Only their positions matter to a symbol search: each one is the `push` that
    findFunctionStart() walks back to, so a scan that still sees a `push` there can report
    a function start the loader will never see.
    """
    sites: list[int] = []
    if patch.get("kind") == "smdh_names":
        sites += [patch["thunk_off"], patch["cache_read_off"]]
        if patch.get("banner_hook"):
            sites.append(patch["banner_hook"]["site_off"])
        if patch.get("news_hook"):
            sites.append(patch["news_hook"]["site_off"])
    if patch.get("pane_hook"):
        sites.append(patch["pane_hook"]["set_text_off"])
    if patch.get("msg_hook"):
        sites.append(patch["msg_hook"]["site_off"])
    return sites


def patched_code(tid: str, code: bytes) -> bytes:
    """The title's .code as the loader sees it after applying our code.ips.

    Only a mount stub adds anything the symbol search can find. The other kinds keep their
    blobs in the .text padding past text.size, or replace plain stores and moves, or ship
    no code.ips at all - but any of them can take out a `push`, so those words are stood in
    for with a branch of no consequence. The real ones are not reproduced here: they would
    need the name tables the build assembles from src/strings.
    """
    patch = HOOK_PATCHES[tid.upper()]
    out = bytearray(code)
    for offset in _hooked_text_words(patch):
        struct.pack_into("<I", out, offset, PLACEHOLDER_BRANCH)

    if patch.get("kind") in ("romfs_from_sd", "area_from_sd", "exheader_only", "smdh_names"):
        return bytes(out)

    globals_value = struct.unpack_from("<I", code, patch["globals_off"])[0]
    stub = build_stub(patch, globals_value)
    out[patch["stub_off"]:patch["stub_off"] + len(stub)] = stub

    # The SMDH wrapper is the one blob that lands inside .text proper, over a function the
    # search would otherwise walk into, so it is reproduced for real - the table it points
    # at is data and its address is fixed, so no name table is needed to lay it out.
    if patch.get("smdh_hook"):
        hook = patch["smdh_hook"]
        words, labels = _smdh_hook(patch, TEXT_VA + hook["rodata_off"], hook["stub_off"])
        blob = b"".join(struct.pack("<I", word) for word in words)
        out[hook["stub_off"]:hook["stub_off"] + len(blob)] = blob
        struct.pack_into("<I", out, hook["site_off"], _bl(hook["site_off"], labels["icon_hook"]))
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


def _bl_target(word: int, at: int) -> int | None:
    """Where a `bl` at .text offset `at` lands, or None if the word is not one."""
    if word >> 24 != 0xEB:
        return None
    offset = word & 0xFFFFFF
    if offset & 0x800000:
        offset -= 0x1000000
    return at + 8 + offset * 4


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
    hook_key: str = "banner_hook",
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

    hook = patch[hook_key]
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


def _verify_news(
    patch: dict,
    code: bytes,
    records: list[tuple[int, bytes]],
    labels: dict[str, int],
    entries: list[dict],
) -> None:
    """Apply the records and walk the notification hook: in, prologue, out, and the table.

    What would be silent here and fatal on a console: a hook that swallows the dispatcher's
    own prologue, so its epilogue pops a return address nobody pushed; a call landing on a
    function other than the one the offsets name; or a table entry pointing at a label that
    is not the NUL-terminated ASCII the message lookup expects.
    """
    patched = bytearray(code)
    for offset, data in records:
        patched[offset:offset + len(data)] = data
    word = lambda off: struct.unpack_from("<I", patched, off)[0]  # noqa: E731

    hook = patch["news_hook"]
    entry = _branch_target(word(hook["site_off"]), hook["site_off"])
    if entry != labels["news_hook"]:
        raise RuntimeError(f"0x{hook['site_off']:X} does not branch into the notification hook")

    # The dispatcher's own prologue and the branch back, in the order they have to run.
    if word(labels["news_hook"] + 0x0C) != hook["original_word"]:
        raise RuntimeError("the notification hook does not reproduce the dispatcher's prologue")
    back = _branch_target(word(labels["news_hook"] + 0x10), labels["news_hook"] + 0x10)
    if back != hook["return_to"]:
        raise RuntimeError(
            f"the notification hook continues at "
            f"{'0x%X' % back if back is not None else 'nowhere'}, expected "
            f"0x{hook['return_to']:X}"
        )

    # Every call out of the blob has to land on the function the offsets name, and that
    # function has to still start with the word it started with when the offset was taken.
    # Two of the calls are conditional (`bleq` to open the session, `blne` to flush the
    # database), which is why the condition nibble is masked off rather than compared.
    def bl_target(at: int) -> int | None:
        value = word(at)
        if (value >> 24) & 0x0F != 0x0B:
            return None
        offset = value & 0xFFFFFF
        return at + 8 + (offset - (0x1000000 if offset & 0x800000 else 0)) * 4

    called = {bl_target(off) for off in range(labels["news_hook"], labels["news_table"], 4)}
    for key, expected in hook["expects"].items():
        target = hook[key]
        if target not in called:
            raise RuntimeError(f"the notification hook never calls {key} at 0x{target:X}")
        if word(target) != expected:
            raise RuntimeError(
                f"0x{target:X} holds 0x{word(target):08X}, expected 0x{expected:08X} - "
                f"{key} is not the function the offsets were taken from"
            )

    # The table: four words an entry, a zero hash to stop on, each label reachable and
    # spelled the way tools/news_tips.py says.
    table_at = word(labels["news_table_ptr"]) - TEXT_VA
    for index, expected in enumerate(entries):
        at = table_at + index * 16
        ru_hash, body_va, title_va, ua_hash = (word(at + step) for step in (0, 4, 8, 12))
        if ru_hash != expected["ru_hash"] or ua_hash != expected["ua_hash"]:
            raise RuntimeError(f"table entry {index} does not carry the hashes it was built with")
        for what, va in (("body_label", body_va), ("title_label", title_va)):
            off = va - TEXT_VA
            text = bytes(patched[off:patched.index(b"\0", off)]).decode("ascii", "replace")
            if text != expected[what]:
                raise RuntimeError(
                    f"table entry {index} points at {text!r}, expected {expected[what]!r}"
                )
    if word(table_at + len(entries) * 16) != 0:
        raise RuntimeError("the notification table has no terminator")


def _verify_redirect(
    patch: dict, code: bytes, records: list[tuple[int, bytes]], path_va: int, sd_path: str
) -> None:
    """Apply the records and walk the result: each site must reach a stub and come back."""
    patched = bytearray(code)
    for offset, data in records:
        patched[offset:offset + len(data)] = data

    word = lambda off: struct.unpack_from("<I", patched, off)[0]  # noqa: E731
    half = lambda off: struct.unpack_from("<H", patched, off)[0]  # noqa: E731

    if patch.get("encoding") == "thumb":
        stub = patch["stub_off"]
        for site in patch["sites"]:
            at = site["patch_at"]
            target = _thumb_bl_target(bytes(patched[at:at + 4]), at)
            if target != stub:
                raise RuntimeError(f"site 0x{at:X} calls 0x{target:X}, expected the stub at 0x{stub:X}")
        if half(stub) != (0x2300 | PATH_ASCII) or half(stub + 0x0E) != (0x2300 | ARCHIVE_SDMC):
            raise RuntimeError(f"stub at 0x{stub:X} does not set an ASCII path and ARCHIVE_SDMC")
        if half(stub + 0x0C) != THUMB_STORE_ATTRIBUTES:
            raise RuntimeError(f"stub at 0x{stub:X} drops the instruction the sites displaced")
        if half(stub + 0x10) != 0x4770:
            raise RuntimeError(f"stub at 0x{stub:X} does not return to its caller")
        if word(stub + 0x14) != path_va:
            raise RuntimeError(f"stub at 0x{stub:X} does not point at the path string")
        encoded = sd_path.encode("ascii") + b"\0"
        path_off = next(off for off, data in records if data == encoded)
        if bytes(patched[path_off:path_off + len(encoded)]) != encoded:
            raise RuntimeError("the path string did not land where the stub points")
        return

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
    tid: str, patch: dict, code: bytes, exheader: bytes, version: int,
    names: dict[str, object] | None = None,
) -> tuple[dict[str, bytes], list[str]]:
    thumb = patch.get("encoding") == "thumb"
    expected = ORIGINAL_THUMB_SITE_WORD if thumb else ORIGINAL_SITE_WORD
    shape = "str r5, [sp, #0x14] ; str r4, [sp, #0x1c]" if thumb else "mov r3, #3"
    for site in patch["sites"]:
        word = struct.unpack_from("<I", code, site["patch_at"])[0]
        if word != expected:
            raise RuntimeError(
                f"0x{site['patch_at']:X} holds 0x{word:08X}, expected 0x{expected:08X} "
                f"({shape}) - this is not the ARCHIVE_ROMFS open the offsets were taken from"
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
    edit_log = _code_edit_records(patch, code, records)
    msg_log: list[str] = []
    if patch.get("msg_hook"):
        hook = patch["msg_hook"]
        extra, msg_log = _msg_records(
            tid, patch, code, exheader, hook["stub_off"], hook["rodata_off"]
        )
        records += extra
    gate_log: list[str] = []
    if patch.get("lang_swap"):
        gate_log = _lang_swap_records(patch, code, exheader, records)
    smdh_log: list[str] = []
    if patch.get("smdh_hook"):
        key = smdh_table_key(patch)
        if not (names or {}).get(key):
            raise RuntimeError(f"{patch['title']} needs an SMDH name table and none was built")
        # The path string above took the front of the .rodata padding; the table goes behind
        # it, and the wrapper at the far end of the .text padding, past the redirect stubs.
        smdh_log = _place_smdh_hook(
            patch, code, exheader, names[key],
            rounded(text_size) + ro_size + len(sd_path) + 1,
            rounded(text_size) + rounded(ro_size), records,
        )
    files = {"code.ips": make_ips(records)}
    log = [
        f"{patch['title']} title version {version}",
        f"code.ips: {len(patch['sites'])} ARCHIVE_ROMFS opens redirected to ARCHIVE_SDMC, "
        f"stubs at 0x{patch['stub_off']:X} (va 0x{TEXT_VA + patch['stub_off']:X})",
        f"code.ips: path {sd_path!r} at va 0x{ro_address + ro_size:X} "
        f"({room} bytes of .rodata padding available)",
    ] + edit_log + msg_log + gate_log + smdh_log

    # A title that already carries DirectSdmc gets no exheader.bin: it would be byte-identical
    # to the one in NAND, and shipping a copy only adds a file that has to match the console's
    # build to be harmless.
    access = struct.unpack_from("<Q", exheader, ACCESS_INFO_OFFSET)[0]
    if access & (1 << DIRECT_SDMC_BIT):
        log.append(f"exheader.bin: not shipped, accessInfo 0x{access:016x} already has DirectSdmc")
    else:
        files["exheader.bin"] = patch_exheader(tid, exheader)
        log.append("exheader.bin: DirectSdmc granted")
    return files, log


def _lang_swap_records(
    patch: dict, code: bytes, exheader: bytes, records: list
) -> list[str]:
    """Swap the Russian language slot with the one this build takes, inside the applet.

    The keyboard's layouts do live in the MSBT - `qwerty_keytop_ru`, `cell_keytop_cyrillic*`,
    `euro_keytop_05*` - which is why the Ukrainian ЙЦУКЕН needs no code at all in the
    `from-ru` build. What is *not* in the MSBT is whether those labels are ever read. The
    applet keeps its own language index in a global (va 0x1B7744) and asks some twenty-five
    times over whether it equals 12, EU_Russian: for the input language, for the number of
    keytop pages, for `KeytopModeSelect_5p` over `KeytopModeSelect`, for the bound of the
    loop that *builds* those pages. Retargeting the tests one by one is a losing game - the
    page objects and the code that draws them are gated in different functions, and missing
    one leaves a null pointer for the other to dereference.

    So the language itself is swapped instead, at the single place it is set:

        0x107E78  mov r0, r4            the index the console's language maps to
        0x107E7C  pop {r4, r5, r6, lr}
        0x107E80  b   SetLanguage       -> b <stub>, which swaps 5 and 12 and falls through

    After that every one of those tests answers the way it does on a Russian console, which
    is the arrangement the `from-ru` build has already been proven on. The two entries of
    the .rodata table that names the MSBT folder per language are swapped to match, so the
    applet still reads the folder each language's text actually lives in:

        index 5  -> EU_Russian     a console left on Russian, whose text this build keeps
        index 12 -> EU_English     the slot this build translates

    The swap is a swap and not an overwrite so that both languages stay reachable: only the
    Cyrillic keyboard, which the applet grants to exactly one language, moves with it.
    """
    swap = patch["lang_swap"]
    slot = variant.current()
    russian = swap["russian"]
    wanted = swap["languages"][slot.key]
    if wanted == russian:
        return ["code.ips: language left alone, this build already takes the slot the "
                "Cyrillic keyboard is wired to"]

    setter = TEXT_VA + swap["set_language_off"]
    word = struct.unpack_from("<I", code, swap["tail_call_off"])[0]
    if word != _b(swap["tail_call_off"], swap["set_language_off"]):
        raise RuntimeError(
            f"0x{swap['tail_call_off']:X} holds 0x{word:08X}, not the `b 0x{setter:X}` that "
            f"ends the language mapper - the offsets are stale"
        )
    body = struct.unpack_from("<3I", code, swap["set_language_off"])
    if list(body) != swap["set_language"]:
        raise RuntimeError(
            f"0x{swap['set_language_off']:X} is not the language setter the offsets were "
            f"taken from: {[f'{w:08X}' for w in body]}"
        )

    stub = swap["stub_off"]
    words = [
        0xE3500000 | wanted,                    # +00  cmp   r0, #<this build's slot>
        0x03A00000 | russian,                   # +04  moveq r0, #12
        _bc(COND_EQ, stub + 0x08, stub + 0x14),  # +08  beq   done
        0xE3500000 | russian,                   # +0C  cmp   r0, #12
        0x03A00000 | wanted,                    # +10  moveq r0, #<this build's slot>
        _b(stub + 0x14, swap["set_language_off"]),  # +14  done: b SetLanguage
    ]
    blob = b"".join(struct.pack("<I", w) for w in words)
    if any(code[stub:stub + len(blob)]):
        raise RuntimeError(f"0x{stub:X} is not the .text padding the stub goes into")

    # The folder table is .rodata, whose file offset follows from the section sizes the way
    # the SD path's does.
    text_size = struct.unpack_from("<I", exheader, TEXT_SIZE_OFFSET)[0]
    ro_address = struct.unpack_from("<I", exheader, 0x20)[0]
    table = ((text_size + 0xFFF) & ~0xFFF) + swap["table_va"] - ro_address
    entries = {}
    for index, folder in swap["folders"].items():
        va = struct.unpack_from("<I", code, table + 4 * index)[0]
        name = _rodata_string(code, exheader, va)
        if name != folder:
            raise RuntimeError(
                f"entry {index} of the folder table at 0x{table:X} names {name!r}, not "
                f"{folder!r} - this is not the table the offsets were taken from"
            )
        entries[index] = va

    new = [
        (swap["tail_call_off"], struct.pack("<I", _b(swap["tail_call_off"], stub))),
        (stub, blob),
        (table + 4 * wanted, struct.pack("<I", entries[russian])),
        (table + 4 * russian, struct.pack("<I", entries[wanted])),
    ]
    for offset, data in new:
        for other, existing in records:
            if offset < other + len(existing) and other < offset + len(data):
                raise RuntimeError(
                    f"the language swap at 0x{offset:X} overlaps the record at 0x{other:X}"
                )
    records += new
    _verify_lang_swap(patch, code, exheader, records, table)

    return [
        f"code.ips: language {wanted} ({slot.lang}) and {russian} (EU_Russian) swapped by a "
        f"{len(blob)}-byte stub at va 0x{TEXT_VA + stub:X}, so the Cyrillic keyboard - and "
        f"everything else the applet grants only to Russian - follows this build's slot",
        f"code.ips: the MSBT folder table at va 0x{swap['table_va']:X} is swapped to match, "
        f"entry {wanted} -> {swap['folders'][russian]}, entry {russian} -> "
        f"{swap['folders'][wanted]}",
    ]


def _rodata_string(code: bytes, exheader: bytes, va: int) -> str:
    """The NUL-terminated string at a .rodata address, as the dumped .code holds it."""
    text_size = struct.unpack_from("<I", exheader, TEXT_SIZE_OFFSET)[0]
    ro_address = struct.unpack_from("<I", exheader, 0x20)[0]
    ro_size = struct.unpack_from("<I", exheader, 0x28)[0]
    if not ro_address <= va < ro_address + ro_size:
        raise RuntimeError(f"0x{va:X} is not a .rodata address")
    start = ((text_size + 0xFFF) & ~0xFFF) + va - ro_address
    return code[start:code.index(b"\0", start)].decode("ascii")


def _verify_lang_swap(
    patch: dict, code: bytes, exheader: bytes, records: list, table: int
) -> None:
    """Walk the patched image: the stub really swaps the two, and nothing else moved."""
    swap = patch["lang_swap"]
    russian = swap["russian"]
    wanted = swap["languages"][variant.current().key]
    patched = bytearray(code)
    for offset, data in records:
        patched[offset:offset + len(data)] = data

    def lands(at: int) -> int:
        word = struct.unpack_from("<I", patched, at)[0]
        if word >> 24 != 0xEA:
            raise RuntimeError(f"0x{at:X} holds 0x{word:08X}, which is not a `b`")
        offset = word & 0xFFFFFF
        return at + 8 + ((offset - 0x1000000 if offset & 0x800000 else offset) << 2)

    stub = swap["stub_off"]
    if lands(swap["tail_call_off"]) != stub:
        raise RuntimeError("the language mapper does not reach the swap stub")
    if lands(stub + 0x14) != swap["set_language_off"]:
        raise RuntimeError("the swap stub does not fall through to the language setter")

    # Both languages have to survive the swap, and land on the folder holding their text.
    for index, expected in ((wanted, swap["folders"][russian]),
                            (russian, swap["folders"][wanted])):
        va = struct.unpack_from("<I", patched, table + 4 * index)[0]
        if _rodata_string(bytes(patched), exheader, va) != expected:
            raise RuntimeError(f"entry {index} of the folder table does not name {expected}")

    # The setter it tail-calls is untouched: the swap is the only thing between the language
    # the console reports and the one the applet remembers.
    if list(struct.unpack_from("<3I", patched, swap["set_language_off"])) != \
            swap["set_language"]:
        raise RuntimeError("the language setter was rewritten")


def msg_sd_path(tid: str, image_name: str) -> str:
    """Where the error-message hook expects the translated archive. Written by tools/build.py."""
    return f"/luma/titles/{tid.upper()}/{image_name}"


def _msg_records(
    tid: str, patch: dict, code: bytes, exheader: bytes, stub_off: int, rodata_off: int
) -> tuple[list[tuple[int, bytes]], list[str]]:
    """Point the error-message archive read at an image on the SD card.

    The bodies of every error code the system shows - `009-1003`, `015-5004`, all 259 of
    them - live in the shared data archive 0004009B00012102, not in the title that draws
    them. Both readers (the error applet and Miiverse) mount it as `msg:` and then open its
    RomFS through FSUSER_OpenFileDirectly with ARCHIVE_SAVEDATA_AND_CONTENT and the archive's
    title id in the archive path. LayeredFS cannot follow that: the path is binary, so none
    of the mount-name prefixes Luma's payload looks for are in it.

    So the same hook the HOME Menu uses for banners is planted on the archive id load: it
    compares the title id the frame already carries and, only for the error-message archive,
    rewrites the frame into an SD open (empty archive path, ASCII file path, ARCHIVE_SDMC).
    Every other read through that call - the EULA archive shares it - falls through to the
    pass-through, which restores the archive id the replaced instruction loaded.
    """
    hook = patch["msg_hook"]
    site = hook["site_off"]
    word = struct.unpack_from("<I", code, site)[0]
    if word != hook["original_word"]:
        raise RuntimeError(
            f"0x{site:X} holds 0x{word:08X}, expected 0x{hook['original_word']:08X} - this is "
            f"not the archive id load the error-message offsets were taken from"
        )

    ro_address = struct.unpack_from("<I", exheader, 0x20)[0]
    ro_size = struct.unpack_from("<I", exheader, 0x28)[0]
    rounded = lambda v: (v + 0xFFF) & ~0xFFF  # noqa: E731
    text_size = struct.unpack_from("<I", exheader, TEXT_SIZE_OFFSET)[0]

    entries, paths = [], bytearray()
    for title in hook["titles"]:
        path = msg_sd_path(tid, title["image_name"])
        entries.append(
            {
                "title_id": title["title_id"],
                "path": path,
                "path_va": ro_address + rodata_off + len(paths),
                "path_len": len(path),
            }
        )
        paths += path.encode("ascii") + b"\0"

    room = rounded(ro_size) - rodata_off
    if len(paths) > room:
        raise RuntimeError(f"the paths need {len(paths)} bytes, .rodata padding has {room}")

    words, labels = _banner_hook(patch, entries, stub_off, hook_key="msg_hook")
    blob = b"".join(struct.pack("<I", w) for w in words)
    if len(blob) > hook["stub_room"]:
        raise RuntimeError(f"the hook is {len(blob)} bytes, only {hook['stub_room']} are free")
    if any(code[stub_off:stub_off + len(blob)]):
        raise RuntimeError(f"the hook would overwrite code at 0x{stub_off:X}, not padding")

    records = [
        (site, struct.pack("<I", _b(site, labels["banner_hook"]))),
        (stub_off, blob),
        (rounded(text_size) + rodata_off, bytes(paths)),
    ]
    _verify_banner(patch, code, records, labels, entries, hook_key="msg_hook")
    served = ", ".join(f"{e['title_id']:016X} -> {e['path']}" for e in entries)
    log = [
        f"code.ips: error-message archive read at 0x{site:X} -> {len(blob)}-byte hook at "
        f"0x{stub_off:X} (va 0x{TEXT_VA + stub_off:X}), serving {served}",
    ]
    return records, log


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
    patch: dict,
    code: bytes,
    exheader: bytes,
    version: int,
    table: bytes,
    news_entries: list[dict] | None = None,
) -> tuple[dict[str, bytes], list[str]]:
    """code.ips that routes both of HOME Menu's SMDH readers through the rewriting stub.

    Four records: one word over each reader's entry, the stub blob at the end of the .text
    padding, and the name table in the .rodata padding. No exheader - HOME Menu already has
    DirectSdmc, and nothing here needs Luma to find a symbol.

    Two more hooks share the same padding when the title has them: the banner open, and the
    tip dispatcher that `news_entries` feeds.
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

    # The notification hook goes below the banner hook. Its table and its labels ride inside
    # the blob rather than in .rodata: the name table has all but filled that padding, and
    # nothing here is a string the console reads - only labels our own code looks up with.
    news = news_off = None
    news_labels: dict[str, int] = {}
    if patch.get("news_hook") and news_entries:
        sizing, _ = _news_hook(patch, news_entries, 0)
        news_off = (banner_off if banner else patch["stub_off"]) - len(sizing) * 4
        news_words, news_labels = _news_hook(patch, news_entries, news_off)
        news = b"".join(struct.pack("<I", word) for word in news_words)

    used = len(stub) + (len(banner) if banner else 0) + (len(news) if news else 0)
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

    if news:
        site = patch["news_hook"]["site_off"]
        word = struct.unpack_from("<I", code, site)[0]
        if word != patch["news_hook"]["original_word"]:
            raise RuntimeError(
                f"0x{site:X} holds 0x{word:08X}, expected "
                f"0x{patch['news_hook']['original_word']:08X} - this is not the tip dispatcher "
                f"the notification offsets were taken from"
            )
        if any(code[news_off:news_off + len(news)]):
            raise RuntimeError(f"the notification hook would overwrite code at 0x{news_off:X}")
        records += [
            (site, struct.pack("<I", _b(site, news_labels["news_hook"]))),
            (news_off, news),
        ]
        _verify_news(patch, code, records, news_labels, news_entries)

    # Last, so Luma's symbol search runs over the image every record has been applied to:
    # each hook takes out a `push`, and a `push` is what findFunctionStart() walks back to.
    _verify_smdh_names(patch, code, records, text_size, labels)

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
    if news:
        tips = ", ".join(str(entry["body_label"]) for entry in news_entries)
        log.append(
            f"code.ips: tip dispatcher at 0x{patch['news_hook']['site_off']:X} -> "
            f"{len(news)}-byte notification hook at 0x{news_off:X}, rewriting {tips}"
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
    tid: str, code_path: Path, exheader_path: Path, names: dict[str, object] | None = None
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
        return _generate_romfs_from_sd(tid, patch, code, exheader, version, names)

    if patch.get("kind") == "area_from_sd":
        # No exheader: this title already has DirectSdmc, and the code the patch adds lands
        # inside pages the title already maps, so there is nothing to widen either.
        return _generate_area_from_sd(
            patch, code, exheader, version, (names or {}).get("smdh")
        )

    if patch.get("kind") == "smdh_names":
        if not (names or {}).get("smdh"):
            raise RuntimeError(f"{patch['title']} needs an SMDH name table and none was built")
        if patch.get("news_hook") and not (names or {}).get("news_tips"):
            raise RuntimeError(f"{patch['title']} needs a notification table and none was built")
        return _generate_smdh_names(
            patch, code, exheader, version, names["smdh"], names.get("news_tips")
        )

    if patch.get("kind") == "exheader_only":
        access = struct.unpack_from("<Q", exheader, ACCESS_INFO_OFFSET)[0]
        files = {"exheader.bin": patch_exheader(tid, exheader)}
        log = [
            f"{patch['title']} title version {version}",
            f"exheader.bin: DirectSdmc granted (accessInfo 0x{access:016x} -> "
            f"0x{access | (1 << DIRECT_SDMC_BIT):016x}); Luma finds every symbol it needs "
            f"in the title's own code",
        ]
        # ... but the error-message archive is not something LayeredFS can reach, so a title
        # that reads it still needs a code.ips of its own. See _msg_records().
        records: list[tuple[int, bytes]] = []
        if patch.get("msg_hook"):
            hook = patch["msg_hook"]
            records, msg_log = _msg_records(
                tid, patch, code, exheader, hook["stub_off"], hook["rodata_off"]
            )
            log += msg_log
        if patch.get("mount_rename"):
            log += _mount_rename_records(patch, code, records)
            # Luma looks for the new prefix inside .text; no stub widens it here, so the
            # exheader's own text.size is the range it will search.
            patch["text_size"] = struct.unpack_from("<I", exheader, TEXT_SIZE_OFFSET)[0]
            _verify_mount_search(patch, code, records)
        if patch.get("reader_policy"):
            log.append(_reader_policy_record(patch, code, records))
        if records:
            files["code.ips"] = make_ips(records)
        else:
            log[-1] += ", so no code.ips"
        return files, log

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
    rename_log = _mount_rename_records(patch, code, records)
    rename_log += _manual_path_records(patch, code, records)
    _verify_mount_search(patch, code, records)
    pane_log: list[str] = []
    if patch.get("pane_hook"):
        if not (names or {}).get("pane"):
            raise RuntimeError(f"{patch['title']} needs a pane name table and none was built")
        extra, pane_log = _pane_records(patch, code, exheader, names["pane"])
        records += extra
    if patch.get("smdh_hook"):
        key = smdh_table_key(patch)
        if not (names or {}).get(key):
            raise RuntimeError(f"{patch['title']} needs an SMDH name table and none was built")
        pane_log += _smdh_hook_records(patch, code, names[key], records)

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
    ] + rename_log + pane_log
    return files, log


"""The 28 words at manual_path["block_off"], as the dump has them. Seven are kept (they set
up the file object, not the path); the rest built the old constant path and are replaced."""
MANUAL_BLOCK = (
    0xE28F5E11,  # add  r5, pc, #272        -> "man:/Manual.bcma"
    0xE2817004,  # add  r7, r1, #4          keep
    0xE58D2000,  # str  r2, [sp]            keep
    0xE5122030,  # ldr  r2, [r2, #-0x30]    keep
    0xE590000C,  # ldr  r0, [r0, #0xc]      keep
    0xE3A08001,  # mov  r8, #1              keep
    0xE28D401C,  # add  r4, sp, #28         keep
    0xE7810002,  # str  r0, [r1, r2]        keep
    0xE28D0F8A,  # add  r0, sp, #552        the converter state, dead with the converter
    0xE58D9228,  # str  r9, [sp, #0x228]
    0xE58D922C,  # str  r9, [sp, #0x22c]
    0xEB007521,  # bl   0x165574            converter init
    0xE288AF41,  # add  r10, r8, #260
    0xE28D2F8A,  # add  r2, sp, #552        \
    0xE1A0100A,  # mov  r1, r10              |
    0xE1A00005,  # mov  r0, r5               |
    0xEB007522,  # bl   0x16558C             |
    0xE1B06000,  # movs r6, r0               |
    0x0A000008,  # beq  +0x20                |  the ASCII -> UTF-16 loop
    0xE1A02000,  # mov  r2, r0               |
    0xE28D3F8A,  # add  r3, sp, #552         |
    0xE1A01005,  # mov  r1, r5               |
    0xE1A00004,  # mov  r0, r4               |
    0xEB007528,  # bl   0x1655C0             |
    0xE3500000,  # cmp  r0, #0               |
    0x12844002,  # addne r4, r4, #2          |
    0x10855006,  # addne r5, r5, r6          |
    0x1AFFFFF0,  # bne  -0x40               /
)


def manual_file_name(tid: str) -> str:
    """The name the viewer asks for on the SD card - and what tools/manual.py must write.

    Four hex digits, not the whole low word. The string lives in a .rodata padding that is
    also the ceiling on how many manuals a release can carry, and `rex:/2000` costs 10 bytes
    where `rex:/00022000.bcma` cost 19 - nine bytes per title, in a budget measured in tens.
    The low 16 bits are unique across every Old 3DS system title the viewer documents, and
    _manual_path_records() refuses to build a table where they are not.

    New 3DS keeps the same low 16 bits for its own copy of a title and puts the `2` further
    up the low word (`0004003020009D02` against `0004003000009D02`), so those get an `n` in
    front - one byte, where the whole low word would cost four. Nothing on the console
    parses the name: the table the viewer walks holds the full low word and a pointer to
    this string, so it only has to be unique on the SD card.
    """
    low = int(tid, 16) & 0xFFFFFFFF
    return ("n" if low >> 28 == 2 else "") + f"{low & 0xFFFF:04x}"


def _manual_path_records(patch: dict, code: bytes, records: list) -> list[str]:
    """Give the viewer one manual file per documented title, with a fallback that works.

    The path `rex:/Manual.bcma` is built in 0x147F58 and used twice: once inside it, and once
    by its caller, which loads the document with the *same* string:

        148280  bl   0x147F58            mount, and open the file once to check it is there
        148290  beq  0x1482A4            gone -> give up
        148294  sub  r1, pc, #200        -> "rex:/Manual.bcma", the string in .text
        14829C  bl   0x14797C            load it

    An earlier version of this patch rewrote that string and only fixed up the first user,
    so the second one opened a path made of whatever was left - which is why every manual on
    the console, translated or not, showed the loading screen and then dropped back to the
    HOME Menu. Both sites now ask the same routine, and the string itself is left alone.

    The routine is fifteen words in the space the multibyte-to-UTF-16 loop used to occupy.
    It reads the documented title's id where the mount above reads it, walks a table of
    {title id, path} pairs in the .rodata padding, and returns either that title's own path
    or - for anything not in the table - the original constant. So a title this build ships
    no manual for asks for `Manual.bcma`, LayeredFS finds no such file on the SD card, and
    Luma's payload falls back to the console's own manual exactly as it always did.

    Nothing is written at runtime: the table and the paths are read-only data, which the
    country lists in System Settings already prove the console loads from that padding.
    """
    spec = patch.get("manual_path")
    if not spec or not spec.get("enabled", True) or manual_path_mode() == "off":
        return []

    if manual_path_mode() == "copy":
        return _manual_copy_only(spec, code, records)
    if manual_path_mode() == "rodata":
        return _manual_rodata_only(spec, code, records)

    block = spec["block_off"]
    if struct.unpack_from(f"<{len(MANUAL_BLOCK)}I", code, block) != MANUAL_BLOCK:
        raise RuntimeError("the path block is not the one this patch reads")
    if struct.unpack_from("<I", code, spec["second_site"])[0] != spec["second_site_word"]:
        raise RuntimeError(f"0x{spec['second_site']:X} is not the caller's `sub r1, pc, #200`")

    # .rodata padding: the table first, then one path string per title.
    entries = spec["titles"]
    table_va = TEXT_VA + spec["rodata_off"]
    strings_at = spec["rodata_off"] + 8 * (len(entries) + 1)
    blob, offset = b"", strings_at
    table = b""
    names = [manual_file_name(tid) for tid in entries]
    if len(set(names)) != len(names):
        raise RuntimeError(f"two manuals would share a file name on the SD card: {names}")
    for tid in entries:
        path = f"rex:/{manual_file_name(tid)}".encode() + b"\0"
        table += struct.pack("<II", int(tid, 16) & 0xFFFFFFFF, TEXT_VA + offset)
        blob += path
        offset += len(path)
    table += struct.pack("<II", 0, 0)
    blob = table + blob
    if len(blob) > spec["rodata_room"]:
        raise RuntimeError(f"{len(blob)} bytes of table, {spec['rodata_room']} are free")
    if set(code[spec["rodata_off"] : spec["rodata_off"] + len(blob)]) != {0}:
        raise RuntimeError("the .rodata padding this patch writes into is not padding")

    va = TEXT_VA + block
    BUILDER, LITERAL = 13, 27
    builder_va = va + BUILDER * 4
    words = [
        *MANUAL_BLOCK[1:8],                              # the seven kept words
        _bl(va + 7 * 4, builder_va),                     # bl builder -> r1 = the path
        0xE4D10001,                                      # ldrb r0, [r1], #1  \
        0xE3500000,                                      # cmp  r0, #0         |  widen it
        0x10C400B2,                                      # strhne r0, [r4], #2 |  into sp+28
        _bc(COND_NE, va + 11 * 4, va + 8 * 4),           # bne  -3            /
        _b(va + 12 * 4, TEXT_VA + block + 4 * len(MANUAL_BLOCK)),  # b past the builder
        # builder: leaf, clobbers r0-r3 only, returns the path in r1
        0xE59F3000 | (TEXT_VA + spec["globals_literal"] - (builder_va + 8)),  # ldr r3, =globals
        0xE5930000,                                      # ldr  r0, [r3]
        0xE5900004,                                      # ldr  r0, [r0, #4]
        0xE5900000,                                      # ldr  r0, [r0]      the title id, low
        0xE59F2000 | (va + LITERAL * 4 - (builder_va + 4 * 4 + 8)),  # ldr r2, =table
        0xE4921008,                                      # ldr  r1, [r2], #8  \
        0xE3510000,                                      # cmp  r1, #0         |  find the title
        _bc(COND_EQ, builder_va + 7 * 4, builder_va + 12 * 4),  # beq fallback |
        0xE1510000,                                      # cmp  r1, r0         |
        _bc(COND_NE, builder_va + 9 * 4, builder_va + 5 * 4),   # bne  -4     /
        0xE5121004,                                      # ldr  r1, [r2, #-4] its path
        0xE12FFF1E,                                      # bx   lr
        0xE28F1000 | (TEXT_VA + spec["pool_off"] - (builder_va + 12 * 4 + 8)),  # add r1, pc, #.
        0xE12FFF1E,                                      # bx   lr
        TEXT_VA + spec["rodata_off"],                    # the literal the builder reads
    ]
    if len(words) != len(MANUAL_BLOCK):
        raise RuntimeError(f"the block is {len(words)} words, {len(MANUAL_BLOCK)} are free")

    records.append((block, struct.pack(f"<{len(words)}I", *words)))
    records.append((spec["second_site"], struct.pack("<I", _bl(TEXT_VA + spec["second_site"], builder_va))))
    records.append((spec["rodata_off"], blob))
    return [
        f"code.ips: both users of the manual path routed through a {len(MANUAL_BLOCK) - BUILDER}"
        f"-word builder at va 0x{builder_va:X} (the caller's site at 0x{spec['second_site']:X} "
        f"too); {len(entries)} titles in the table at va 0x{table_va:X}, everything else keeps "
        f"{spec['fallback'][:-1].decode()!r} and its own manual"
    ]


def _align(value: int, to: int) -> int:
    return (value + to - 1) & ~(to - 1)


def _manual_rodata_only(spec: dict, code: bytes, records: list) -> list[str]:
    """The second bisect: the copy build, plus the path string moved out to .rodata.

    One word differs from the build that works: `add r5, pc, #272` (the string in .text)
    becomes `ldr r5, [pc, #..]` through a literal in the dead pool, pointing at a copy of the
    same string in the .rodata padding. If the manuals still open, then the pool, the literal
    and the .rodata read are all sound and only the title-id lookup can be at fault.
    """
    block = spec["block_off"]
    if struct.unpack_from(f"<{len(MANUAL_BLOCK)}I", code, block) != MANUAL_BLOCK:
        raise RuntimeError("the path block is not the one this patch reads")

    text = spec["fallback"]
    if set(code[spec["rodata_off"] : spec["rodata_off"] + len(text)]) != {0}:
        raise RuntimeError("the .rodata padding this patch writes into is not padding")

    va = TEXT_VA + block
    pool = spec["pool_off"]
    loop = 13
    words = [
        0xE59F5000 | (TEXT_VA + pool - (va + 8)),    # ldr r5, =the string, in the dead pool
        *MANUAL_BLOCK[1:loop],
        0xE4D50001,                                  # ldrb r0, [r5], #1
        0xE3500000,                                  # cmp  r0, #0
        0x10C400B2,                                  # strhne r0, [r4], #2
        _bc(COND_NE, va + (loop + 3) * 4, va + loop * 4),
    ]
    words += [NOP] * (len(MANUAL_BLOCK) - len(words))

    records.append((block, struct.pack(f"<{len(words)}I", *words)))
    # The literal, then `rex:` for Luma's mount search - the string itself now lives in .rodata.
    records.append((pool, struct.pack("<I", TEXT_VA + spec["rodata_off"]) + b"rex:\0"))
    records.append((spec["rodata_off"], text))
    return [
        f"code.ips: BISECT BUILD - the constant path moved to .rodata at "
        f"va 0x{TEXT_VA + spec['rodata_off']:X}, loaded through a literal at 0x{pool:X}"
    ]


def manual_path_mode() -> str:
    """"full" | "copy" | "rodata" | "off" - which build of the manual path patch this makes.

    Full is what ships. The other two are the bisect builds that found the second user of the
    path string, kept because the next change to this patch will want them again.
    """
    return {"copy": "copy", "rodata": "rodata", "off": "off"}.get(
        os.environ.get("MANUAL_PATCH", ""), "full"
    )


def _manual_copy_only(spec: dict, code: bytes, records: list) -> list[str]:
    """The bisect build: everything Nintendo's, except how the path is widened to UTF-16.

    The full patch replaces all 28 words and reads its strings out of .rodata; this one
    keeps the first thirteen exactly as they are - the string pointer, the converter state,
    the mbsinit call, the length in r10 - and only swaps the fifteen-word multibyte loop for
    the four-word byte-by-byte one. If the manuals still open with this, nothing is wrong
    with the loop and the fault is in the parts the full patch adds.
    """
    block = spec["block_off"]
    have = struct.unpack_from(f"<{len(MANUAL_BLOCK)}I", code, block)
    if have != MANUAL_BLOCK:
        raise RuntimeError("the path block is not the one this patch reads")

    va = TEXT_VA + block
    loop = 13  # the first word of the multibyte loop
    words = [
        *MANUAL_BLOCK[:loop],
        0xE4D50001,                                  # ldrb r0, [r5], #1
        0xE3500000,                                  # cmp  r0, #0
        0x10C400B2,                                  # strhne r0, [r4], #2
        _bc(COND_NE, va + (loop + 3) * 4, va + loop * 4),
    ]
    words += [NOP] * (len(MANUAL_BLOCK) - len(words))
    records.append((block, struct.pack(f"<{len(words)}I", *words)))
    return [
        f"code.ips: BISECT BUILD - only the UTF-16 widening loop replaced at 0x{block:X}, "
        f"the path is still the constant string in .text"
    ]


def _mount_rename_records(patch: dict, code: bytes, records: list) -> list[str]:
    """Rename an archive mount to one LayeredFS knows, so Luma will redirect reads from it.

    Two shapes. `{"old", "new", "offsets"}` renames one word at several offsets - the
    Instruction Manual's `man:` -> `rex:`. A list of `(offset, old, new)` renames several
    different strings, which is what a mount reached through URLs needs: the account pages
    in `act` are addressed as `file:///content:/…`, so the scheme table and the URL template
    have to move together with the mount name or the applet mounts one thing and asks for
    another.

    Either way the replacement is written over the original in place, so both must be the
    same length. A shorter name is padded with NULs by the caller's table: these are C
    strings, the first NUL ends them, and the bytes behind it were already zero.
    """
    rename = patch.get("mount_rename")
    if not rename:
        return []

    entries = (
        [(off, rename["old"], rename["new"]) for off in rename["offsets"]]
        if isinstance(rename, dict)
        else list(rename)
    )

    for offset, old, new in entries:
        if len(old) != len(new):
            raise RuntimeError(f"{old!r} and {new!r} are different lengths; the patch is in place")
        if code[offset:offset + len(old)] != old:
            raise RuntimeError(f"0x{offset:X} does not hold {old!r} - the offsets are stale")
        records.append((offset, new))

    renamed = ", ".join(f"0x{off:X}" for off, _, _ in entries)
    shown = entries[0][1].decode(), entries[-1][2].split(b"\0")[0].decode()
    return [
        f"code.ips: mount {shown[0]} -> {shown[1]} at {renamed}"
        + "; LayeredFS then redirects the reads to the title's romfs folder, and falls back "
        "to the original archive when the file is absent"
    ]


def _smdh_hook_records(patch: dict, code: bytes, table: bytes, records: list) -> list[str]:
    """Route a title's SMDH read through the rewriting wrapper.

    Three kinds of record: the `bl` at every call site, the wrapper blob, and the name table
    in the .rodata padding. Everything the patch assumes about the dump is checked here
    rather than trusted - each site really is the `bl` to the reader, the space the blob goes
    into is what the offsets claim (byte for byte the dead function ebird overwrites, or
    genuine padding elsewhere), the .rodata it writes into is padding, and nothing already in
    `records` shares any of it.
    """
    hook = patch["smdh_hook"]
    sites, stub_off = _smdh_hook_sites(hook), hook["stub_off"]

    for site in sites:
        word = struct.unpack_from("<I", code, site)[0]
        if word != _bl(site, hook["reader_off"]):
            raise RuntimeError(
                f"0x{site:X} holds 0x{word:08X}, not the bl 0x{hook['reader_off']:X} "
                f"(0x{_bl(site, hook['reader_off']):08X}) this hook wraps"
            )

    region = code[stub_off:stub_off + hook["stub_room"]]
    if "dead_sha256" in hook:
        digest = hashlib.sha256(region).hexdigest()
        if digest != hook["dead_sha256"]:
            raise RuntimeError(
                f"0x{stub_off:X} is not the dead function the blob goes over\n"
                f"  expected sha256 {hook['dead_sha256']}\n  got             {digest}"
            )
    elif set(region) != {0}:
        raise RuntimeError(f"0x{stub_off:X} is not the .text padding the blob goes into")

    table_off = hook["rodata_off"]
    if len(table) > hook["rodata_room"]:
        raise RuntimeError(
            f"the name table is {len(table)} bytes, {hook['rodata_room']} are free"
        )
    if set(code[table_off:table_off + len(table)]) != {0}:
        raise RuntimeError("the .rodata padding this hook writes into is not padding")

    words, labels = _smdh_hook(patch, TEXT_VA + table_off, stub_off)
    blob = b"".join(struct.pack("<I", word) for word in words)
    if len(blob) > hook["stub_room"]:
        raise RuntimeError(f"the hook is {len(blob)} bytes, {hook['stub_room']} are free")

    new = [(site, struct.pack("<I", _bl(site, labels["icon_hook"]))) for site in sites]
    new += [(stub_off, blob), (table_off, table)]
    for offset, data in new:
        for other, existing in records:
            if offset < other + len(existing) and other < offset + len(data):
                raise RuntimeError(
                    f"the SMDH hook record at 0x{offset:X} overlaps the one at 0x{other:X}"
                )
    records += new
    _verify_smdh_hook(patch, code, records, labels, len(table))

    where = ", ".join(f"0x{site:X}" for site in sites)
    return [
        f"code.ips: {hook['reads']} at {where} routed through a {len(blob)}-byte "
        f"wrapper at va 0x{TEXT_VA + stub_off:X}; language slot {variant.current().smdh_index} is "
        f"rewritten from a {len(table)}-byte table at va 0x{TEXT_VA + table_off:X}, so "
        f"{hook['effect']}"
    ]


def _verify_smdh_hook(
    patch: dict, code: bytes, records: list, labels: dict[str, int], table_size: int
) -> None:
    """Walk the patched image: site -> wrapper -> reader, and the table the loop reads."""
    from layeredfs_check import find_symbols  # imported late: layeredfs_check imports build

    hook = patch["smdh_hook"]
    patched = bytearray(code)
    for offset, data in records:
        patched[offset:offset + len(data)] = data

    for site in _smdh_hook_sites(hook):
        word = struct.unpack_from("<I", patched, site)[0]
        if _bl_target(word, site) != labels["icon_hook"]:
            raise RuntimeError(f"the call site at 0x{site:X} does not reach the wrapper")

    call = labels["icon_call"]
    word = struct.unpack_from("<I", patched, call)[0]
    if _bl_target(word, call) != hook["reader_off"]:
        raise RuntimeError("the wrapper does not call the reader it replaced")

    literal = struct.unpack_from("<I", patched, labels["table"])[0]
    if literal != TEXT_VA + hook["rodata_off"]:
        raise RuntimeError("the rewrite loop does not point at the table")
    if struct.unpack_from("<I", patched, hook["rodata_off"] + table_size - 4)[0] != 0:
        raise RuntimeError("the name table is not terminated")

    # The blob lands on a function start, which is what Luma's symbol search walks back to,
    # so the search has to be re-run: the mount stub must still be what it resolves. Only the
    # titles that ship one care - `variant` is what builds it. Titles Luma hooks unaided have
    # no symbol of ours to protect, and the ones that never reach patchLayeredFs at all
    # (`romfs_from_sd`, `area_from_sd`) are not searched in the first place; their `stub_off`
    # is a redirect stub, not an fsMountArchive.
    if not patch.get("variant"):
        return
    symbols = find_symbols(bytes(patched), patch["text_size_override"] or patch["text_size"])
    if symbols["fsMountArchive"] != patch["stub_off"]:
        raise RuntimeError(
            f"the wrapper changes Luma's symbol search: fsMountArchive -> "
            f"{symbols['fsMountArchive']}, expected 0x{patch['stub_off']:X}"
        )


def _code_edit_records(patch: dict, code: bytes, records: list) -> list[str]:
    """Single instructions the patch rewrites in place, each checked against the dump first.

    The redirect stubs move whole opens onto the SD card; this is for the decisions taken
    before them - which of two paths an open is given, in the one title that picks between
    its own romfs and a content it keeps the document in. An offset that has drifted would
    otherwise land on whatever moved there, so the expected bytes are part of the entry.
    """
    log = []
    for edit in patch.get("code_edits", []):
        found = code[edit["off"]:edit["off"] + len(edit["expect"])]
        if found != edit["expect"]:
            raise RuntimeError(
                f"{patch['title']}: 0x{edit['off']:X} holds {found.hex()}, not the "
                f"{edit['expect'].hex()} this edit was derived from"
            )
        if len(edit["write"]) != len(edit["expect"]):
            raise RuntimeError(f"0x{edit['off']:X}: the edit changes the instruction length")
        records.append((edit["off"], edit["write"]))
        log.append(f"code.ips: 0x{edit['off']:X} {found.hex()} -> {edit['write'].hex()} - {edit['why']}")
    return log


def _reader_policy_record(patch: dict, code: bytes, records: list) -> str:
    """Move one file open onto the reader whose archive LayeredFS can serve.

    A single `mov r2, #imm` picks the reader class an open goes through, so the redirection
    costs one instruction. The dump is checked first: an offset that no longer holds the
    expected instruction would otherwise corrupt whatever moved there.
    """
    offset, expected, replacement = patch["reader_policy"]
    found = code[offset:offset + len(expected)]
    if found != expected:
        raise RuntimeError(
            f"{patch['title']}: 0x{offset:X} holds {found.hex()}, not the "
            f"{expected.hex()} the reader-policy patch was derived from"
        )
    records.append((offset, replacement))
    return (
        f"code.ips: font reader at 0x{offset:X} moved off the `dll:` policy onto `rom:`, "
        f"so /font/Hud.bcfnt is served from the SD card"
    )


def _verify_mount_search(patch: dict, code: bytes, records: list) -> None:
    """Luma finds the update mount by searching .text for a NUL followed by its name.

    The rename alone does not guarantee that: the copy Luma used to find can be the one the
    manual_path pool overwrites. So the check runs on the patched image, not on the config.
    """
    rename = patch.get("mount_rename")
    if not rename:
        return

    patched = bytearray(code)
    for offset, data in records:
        patched[offset:offset + len(data)] = data

    # The list form pads its replacements with NULs; the mount name is the last entry, up to
    # its first NUL. Luma matches on the bare name, not on the padding behind it.
    name = rename["new"] if isinstance(rename, dict) else rename[-1][2].split(b"\0")[0]

    text_size = patch.get("text_size_override") or patch["text_size"]
    if patched.find(b"\0" + name, 0, text_size) < 0:
        raise RuntimeError(
            f"nothing for Luma to match: no NUL-prefixed {name!r} inside .text"
        )
