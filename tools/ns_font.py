"""Opt-in: make NS read the shared system font from the SD card - no NAND write at all.

The shared font (`cbf_std.bcfnt.lz`, archive 0004009B00014002) is loaded at boot by NS
(0004013000008002), a system module - not by any title, so LayeredFS never sees it (see
"Real Ukrainian letters in the system font" in docs/internals.en.md). Reinstalling the font
title (tools/sysfont_cia.py) works but writes to NAND. This is the other way: patch NS so
that it reads the font off the SD card first and falls back to the stock title otherwise.
Luma3DS v13+ applies such patches from two places:

    luma/sysmodules/0004013000008002.ips      needs "Load external FIRMs and modules"
    luma/titles/0004013000008002/exheader.bin needs that *and* "Enable game patching"

What NS does at 0x1020A4 (v23): picks the font by region, mounts the font title as `font:`
(0x102178), opens `font:/cbf_std.bcfnt.lz`, reads it whole to the end of the 0x332000-byte
shared block (`r8 - align4(size) + 0x331F80`, r8 = block + 0x80), unmounts, and inflates it
in place to the start of the block. The hook replaces the `ldr r0, ="font:"` right before
the mount with a `bl` into a stub in the .text padding. The stub opens
`sdmc:/3ds/3ds-ua/font/cbf_std.bcfnt.lz` through NS's own FSUSER_OpenFileDirectly wrapper,
reads it to that same address and resumes at 0x102330 - the inflate - as if the stock read
had happened. Anything going wrong - no file, a size of 0 or over LIMIT, a short read, no
SD access - restores every register, executes the replaced instruction and returns to the
mount: the console boots with the stock font.

So the patch fails safe twice over. NS has no `DirectSdmc` right of its own, which is what
the exheader adds; without it (game patching off) the SD open is refused and the IPS alone
changes nothing. And a font that NS cannot use only ever costs the font, never the boot -
except for a font that does not fit, which check_font() refuses before anything is copied.

Offsets are specific to one build of NS, identified like the titles in luma_hook.py: the
exheader's remaster version plus the sha256 of the .code. The checks also cover what Luma
patches in NS on its own (patcher.c, region-free carts, the New 3DS clock, a .rodata wipe):
none of it may move, and none of its search patterns may appear in the stub.

Verified on an Old 3DS, 11.17.0-50E, Luma3DS v13.4, 2026-10-21: the patched font from SD
drew і ї є ґ ʼ in a GLYPHS=real build, and with the font file renamed the console booted on
the stock font.

Usage:
    python3 tools/ns_font.py            # -> dist_sysfont/sd/{luma/...,3ds/3ds-ua/font/...}
    python3 tools/ns_font.py --check    # also the in-place inflate margin of both fonts
"""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import luma_hook  # noqa: E402
from luma_hook import (  # noqa: E402
    ACCESS_INFO_OFFSET,
    DIRECT_SDMC_BIT,
    REMASTER_VERSION_OFFSET,
    TEXT_SIZE_OFFSET,
    TEXT_VA,
    _assemble,
    _bc,
    _bl,
    _imm12,
)

ROOT = Path(__file__).resolve().parent.parent
TID = "0004013000008002"
WORK = ROOT / "work" / TID
STOCK_FONT = ROOT / "work" / "0004009B00014002" / "cbf_std.bcfnt.lz"
PATCHED_FONT = ROOT / "dist_sysfont" / "cbf_std.bcfnt.lz"
OUT = ROOT / "dist_sysfont" / "sd"

# Where the font goes on the card. The installer app writes it here, so the two must agree.
FONT_SD_PATH = "/3ds/3ds-ua/font/cbf_std.bcfnt.lz"

# The 0x332000-byte shared block: 0x80 of header, then the inflated font. The compressed file
# is read to the end of it and inflated towards the start, so it has to fit twice over - see
# inplace_slack().
SHARED_BLOCK_DATA = 0x332000 - 0x80
LIMIT = 0x1C0000  # sanity bound the stub puts on the compressed size

COND_HI, COND_LT = 0x8, 0xB

# code sha256 -> everything the stub needs. One entry per NS build; New 3DS consoles run the
# same title, so its dump is expected to hash the same - checked before it ships there.
NS_BUILDS: dict[str, dict] = {
    "0e9c322edb02e4a7373282a7cd3e66d2e66d9e8832a0775f84fbbe34c81688a0": {
        "remaster": 23,          # TMD v23.0.1 (23553), the last NS there is
        "hook": 0x102170,        # ldr r0, [pc, #0x28c]  (="font:"), right before the mount
        "hook_word": 0xE59F028C,
        "resume": 0x102330,      # after the read, close and unmount: the inflate begins
        "font_str": 0x1201C0,    # "font:"
        "fs_session": 0x124250,  # fs:USER handle, stored at 0x101FB0
        "open_direct": 0x10A4E4, # FSUSER_OpenFileDirectly wrapper
        "file_getsize": 0x116774,
        "file_read": 0x116690,
        "file_close": 0x1166E8,
        "stub": 0x11FA40,        # .text ends at 0x11FA3C; its page runs to 0x120000
        "text_page_end": 0x120000,
    },
}

# What Luma's loader searches NS for (patcher.c). Each must be found as often after our IPS
# as before it, or Luma refuses to boot NS (`goto error`) - or patches the wrong place.
LUMA_NS_PATTERNS = (
    bytes((0x0C, 0x18, 0xE1, 0xD8)),  # region-free carts
    bytes((0x0C, 0x00, 0x94, 0x15)),  # New 3DS clock / L2
    bytes((0x00, 0xB1, 0x15, 0x00)),  # .rodata wipe, NS remaster > 0x12
)


def _ldr_literal(reg: int, literal: str):
    """`ldr <reg>, [pc, #off]` aimed at a labelled pool word."""
    return lambda address, labels: 0xE59F0000 | (reg << 12) | (labels[literal] - address - 8)


def _branch(cond: int, target: str):
    return lambda address, labels: _bc(cond, address, labels[target])


def _call(target: int):
    return lambda address, labels: _bl(address, target)


def stub(build: dict) -> bytes:
    """The SD reader, hand-assembled like the stubs in luma_hook.py.

    Entered by `bl` from the hook. State there: r4 = font index (0 = cbf_std, the only one
    redirected), r8 = shared block + 0x80, r5 = 0, the caller's [sp, #0x1c] - its file object
    slot - not yet written. The stub keeps its own 0x30 bytes below a full register save.
    """
    path = FONT_SD_PATH.encode("ascii") + b"\0"
    data = b"\0" + path                       # PATH_EMPTY's "" right before the path
    data += b"\0" * (-len(data) % 4)
    blocks: dict[str, list] = {
        "entry": [
            0xE92D5FFF,                       # push {r0-r12, lr}     caller sp = sp + 0x38
            0xE3540000,                       # cmp  r4, #0           only cbf_std
            _branch(luma_hook.COND_NE, "fallback"),
            0xE24DD030,                       # sub  sp, sp, #0x30    [0..1f] args, [20] handle,
                                              #                       [24] read, [28] u64 size
            0xE3A00001,                       # mov  r0, #1           archive path: PATH_EMPTY
            0xE58D0000,                       # str  r0, [sp]
            _ldr_literal(0, "lit_empty"),     # ldr  r0, =""
            0xE58D0004,                       # str  r0, [sp, #4]
            0xE3A00001,                       # mov  r0, #1           ... of size 1
            0xE58D0008,                       # str  r0, [sp, #8]
            0xE3A00003,                       # mov  r0, #3           file path: PATH_ASCII
            0xE58D000C,                       # str  r0, [sp, #0xc]
            _ldr_literal(0, "lit_path"),      # ldr  r0, =path
            0xE58D0010,                       # str  r0, [sp, #0x10]
            0xE3A00000 | _imm12(len(path)),   # mov  r0, #len(path)
            0xE58D0014,                       # str  r0, [sp, #0x14]
            0xE3A00001,                       # mov  r0, #1           FS_OPEN_READ
            0xE58D0018,                       # str  r0, [sp, #0x18]
            0xE3A00000,                       # mov  r0, #0           attributes
            0xE58D001C,                       # str  r0, [sp, #0x1c]
            0xE58D0020,                       # str  r0, [sp, #0x20]  handle = 0
            _ldr_literal(0, "lit_session"),   # ldr  r0, =&fs:USER handle
            0xE28D1020,                       # add  r1, sp, #0x20
            0xE3A02000,                       # mov  r2, #0           transaction
            0xE3A03009,                       # mov  r3, #9           ARCHIVE_SDMC
            _call(build["open_direct"]),
            0xE3500000,                       # cmp  r0, #0
            _branch(COND_LT, "fail_open"),    # no file, no card, no DirectSdmc: stock font
            0xE28D0020,                       # add  r0, sp, #0x20
            0xE28D1028,                       # add  r1, sp, #0x28
            _call(build["file_getsize"]),
            0xE3500000,                       # cmp  r0, #0
            _branch(COND_LT, "fail_close"),
            0xE59D102C,                       # ldr  r1, [sp, #0x2c]  size has to fit 32 bits
            0xE3510000,                       # cmp  r1, #0
            _branch(luma_hook.COND_NE, "fail_close"),
            0xE59D5028,                       # ldr  r5, [sp, #0x28]
            0xE3550000,                       # cmp  r5, #0
            _branch(luma_hook.COND_EQ, "fail_close"),
            0xE3A01000 | _imm12(LIMIT),       # mov  r1, #LIMIT
            0xE1550001,                       # cmp  r5, r1
            _branch(COND_HI, "fail_close"),
            0xE2856003,                       # add  r6, r5, #3       r6 = r8 - align4(size)
            0xE3C66003,                       # bic  r6, r6, #3            + 0x331F80,
            0xE0486006,                       # sub  r6, r8, r6            as NS at 0x1022A4
            0xE2866000 | _imm12(0x330000),    # add  r6, r6, #0x330000
            0xE2866000 | _imm12(0x1F80),      # add  r6, r6, #0x1f80
            0xE58D6000,                       # str  r6, [sp]         buffer
            0xE58D5004,                       # str  r5, [sp, #4]     size
            0xE28D0020,                       # add  r0, sp, #0x20
            0xE28D1024,                       # add  r1, sp, #0x24
            0xE3A02000,                       # mov  r2, #0           offset
            0xE3A03000,                       # mov  r3, #0
            _call(build["file_read"]),
            0xE3500000,                       # cmp  r0, #0
            _branch(COND_LT, "fail_close"),
            0xE59D1024,                       # ldr  r1, [sp, #0x24]
            0xE1510005,                       # cmp  r1, r5           a short read is a failure
            _branch(luma_hook.COND_NE, "fail_close"),
            0xE28D0020,                       # add  r0, sp, #0x20
            _call(build["file_close"]),
            0xE59D0020,                       # ldr  r0, [sp, #0x20]
            0xEF000023,                       # svc  0x23             CloseHandle
            0xE28DD030,                       # add  sp, sp, #0x30
            0xE58D5010,                       # str  r5, [sp, #0x10]  caller r4 = size
            0xE58D6024,                       # str  r6, [sp, #0x24]  caller sb = buffer
            0xE3A00000,                       # mov  r0, #0
            0xE58D0054,                       # str  r0, [sp, #0x54]  caller [sp,#0x1c]: no file
            _ldr_literal(0, "lit_resume"),    # ldr  r0, =resume
            0xE58D0034,                       # str  r0, [sp, #0x34]  return past the stock read
            0xE8BD9FFF,                       # pop  {r0-r12, pc}
        ],
        "fail_close": [
            0xE28D0020,                       # add  r0, sp, #0x20
            _call(build["file_close"]),
            0xE59D0020,                       # ldr  r0, [sp, #0x20]
            0xEF000023,                       # svc  0x23
        ],
        "fail_open": [
            0xE28DD030,                       # add  sp, sp, #0x30
        ],
        "fallback": [
            0xE8BD5FFF,                       # pop  {r0-r12, lr}
            _ldr_literal(0, "lit_font"),      # ldr  r0, ="font:"     the replaced instruction
            0xE12FFF1E,                       # bx   lr               on to the stock mount
        ],
        "lit_empty": [lambda a, labels: labels["data"]],
        "lit_path": [lambda a, labels: labels["data"] + 1],
        "lit_session": [build["fs_session"]],
        "lit_resume": [build["resume"]],
        "lit_font": [build["font_str"]],
        "data": list(struct.unpack(f"<{len(data) // 4}I", data)),
    }
    words, _ = _assemble(blocks, build["stub"])
    return struct.pack(f"<{len(words)}I", *words)


def identify(code: bytes, exheader: bytes) -> dict:
    digest = hashlib.sha256(code).hexdigest()
    build = NS_BUILDS.get(digest)
    if build is None:
        raise SystemExit(f"NS .code sha256 {digest} is not a build this patch knows")
    remaster = struct.unpack_from("<H", exheader, REMASTER_VERSION_OFFSET)[0]
    if remaster != build["remaster"]:
        raise SystemExit(f"NS exheader is remaster {remaster}, the code is {build['remaster']}")
    return build


def build_patch(code: bytes, exheader: bytes) -> tuple[bytes, bytes]:
    """Return (code.ips for luma/sysmodules, exheader.bin for luma/titles)."""
    build = identify(code, exheader)
    body = stub(build)
    hook = build["hook"] - TEXT_VA
    if struct.unpack_from("<I", code, hook)[0] != build["hook_word"]:
        raise SystemExit("the hook site does not hold the expected instruction")
    records = [
        (hook, struct.pack("<I", _bl(build["hook"], build["stub"]))),
        (build["stub"] - TEXT_VA, body),
    ]
    ips = luma_hook.make_ips(records)
    verify(code, exheader, build, records)

    out = bytearray(exheader)
    access = struct.unpack_from("<Q", out, ACCESS_INFO_OFFSET)[0]
    struct.pack_into("<Q", out, ACCESS_INFO_OFFSET, access | (1 << DIRECT_SDMC_BIT))
    return ips, bytes(out)


def verify(code: bytes, exheader: bytes, build: dict, records: list[tuple[int, bytes]]) -> None:
    text_size = struct.unpack_from("<I", exheader, TEXT_SIZE_OFFSET)[0]
    start, end = build["stub"] - TEXT_VA, build["text_page_end"] - TEXT_VA
    body = records[1][1]
    if not text_size <= start or start + len(body) > end:
        raise SystemExit(f"stub ({len(body)} bytes at 0x{build['stub']:X}) is not inside the .text padding")
    if any(code[text_size:end]):
        raise SystemExit("the .text padding is not empty")

    patched = bytearray(code)
    for offset, data in records:
        patched[offset:offset + len(data)] = data
    for pattern in LUMA_NS_PATTERNS:
        before = [m.start() for m in re.finditer(re.escape(pattern), code)]
        after = [m.start() for m in re.finditer(re.escape(pattern), bytes(patched))]
        if before != after:
            raise SystemExit(f"the patch changes where Luma finds {pattern.hex()} in NS")
        for offset in after:
            if any(o <= offset < o + len(d) + len(pattern) for o, d in records):
                raise SystemExit(f"Luma's {pattern.hex()} site overlaps the patch")
    if luma_hook._bl_target(struct.unpack_from("<I", patched, build["hook"] - TEXT_VA)[0], build["hook"]) != build["stub"]:
        raise SystemExit("the hook does not reach the stub")


def inplace_slack(lz: bytes) -> int:
    """Bytes to spare between NS's inflate output and the compressed input it reads.

    The file sits at the end of the block and inflates towards the start, so the write
    pointer must never pass the read pointer: max(out - in) over the stream has to stay
    below where the input starts. A negative result is a font that corrupts itself.
    """
    if lz[0] != 0x11:
        raise ValueError("not LZ11")
    size, p = int.from_bytes(lz[1:4], "little"), 4
    if size == 0:
        size, p = int.from_bytes(lz[4:8], "little"), 8
    out, worst = 0, 0
    while out < size:
        flags = lz[p]
        p += 1
        for bit in range(8):
            if out >= size:
                break
            if flags & (0x80 >> bit):
                kind = lz[p] >> 4
                if kind == 0:
                    out += (((lz[p] & 0xF) << 4) | (lz[p + 1] >> 4)) + 0x11
                    p += 3
                elif kind == 1:
                    out += (((lz[p] & 0xF) << 12) | (lz[p + 1] << 4) | (lz[p + 2] >> 4)) + 0x111
                    p += 4
                else:
                    out += kind + 1
                    p += 2
            else:
                out += 1
                p += 1
            worst = max(worst, out - p)
    start = SHARED_BLOCK_DATA - ((len(lz) + 3) & ~3)  # where NS reads the file to
    return start - worst


def check_font(lz: bytes) -> int:
    """Refuse a font NS could not load; return its in-place slack."""
    if not 0 < len(lz) <= LIMIT:
        raise SystemExit(f"compressed font is {len(lz)} bytes, the stub takes 1..{LIMIT}")
    size = int.from_bytes(lz[1:4], "little")
    if size > SHARED_BLOCK_DATA:
        raise SystemExit(f"inflated font is {size} bytes, the block holds {SHARED_BLOCK_DATA}")
    slack = inplace_slack(lz)
    if slack <= 0:
        raise SystemExit(f"the font would overwrite itself while inflating (slack {slack})")
    return slack


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="also report the fonts' inflate margin")
    args = parser.parse_args()

    code_path, exheader_path = WORK / "code.bin", WORK / "exheader.bin"
    if not code_path.exists():
        raise SystemExit(f"{code_path.relative_to(ROOT)} is missing - unpack the NS CIA with tools/cia.py")
    code, exheader = code_path.read_bytes(), exheader_path.read_bytes()
    ips, patched_exheader = build_patch(code, exheader)

    sysmodules = OUT / "luma" / "sysmodules"
    titles = OUT / "luma" / "titles" / TID
    sysmodules.mkdir(parents=True, exist_ok=True)
    titles.mkdir(parents=True, exist_ok=True)
    (sysmodules / f"{TID}.ips").write_bytes(ips)
    (titles / "exheader.bin").write_bytes(patched_exheader)
    build = identify(code, exheader)
    print(f"NS remaster {build['remaster']}: stub {len(stub(build))} bytes at 0x{build['stub']:X}, "
          f"hook at 0x{build['hook']:X}")
    print(f"{(sysmodules / f'{TID}.ips').relative_to(ROOT)} ({len(ips)} bytes)")
    print(f"{(titles / 'exheader.bin').relative_to(ROOT)} (DirectSdmc granted)")

    if PATCHED_FONT.exists():
        slack = check_font(PATCHED_FONT.read_bytes())
        target = OUT / FONT_SD_PATH.lstrip("/")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PATCHED_FONT, target)
        print(f"{target.relative_to(ROOT)} (inflate slack {slack} bytes)")
    else:
        print(f"{PATCHED_FONT.relative_to(ROOT)} is missing - run `make sysfont` first")

    if args.check:
        for path in (STOCK_FONT, PATCHED_FONT):
            if path.exists():
                print(f"  {path.relative_to(ROOT)}: inflate slack {inplace_slack(path.read_bytes())} bytes")


if __name__ == "__main__":
    main()
