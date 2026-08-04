"""Emulate System Settings' SMDH name hook over the patched image.

The harness reproduces what Luma does at boot, in Luma's order: apply code.ips, then write
the 0x114-byte LayeredFS payload at the front of the .text padding and the 48-byte
"lf:/luma/titles/<TID>/romfs" path at the front of the .rodata padding. A harness that
skips those two writes is green on a patch that the console would have overwritten.

Then, for every title in the table (and one that is not in it), it enters each thunk the
way Data Management does - r0 = a fresh 0x36C0 buffer, r1 = 1, r2/r3 = the title id - with
the reader itself intercepted: the interception checks the mediatype word the wrapper had to
carry across its own frame, fills the buffer with a Russian name, and returns 0.
"""

from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

from unicorn import UC_ARCH_ARM, UC_HOOK_CODE, UC_MODE_ARM, Uc
from unicorn.arm_const import (
    UC_ARM_REG_LR,
    UC_ARM_REG_PC,
    UC_ARM_REG_R0,
    UC_ARM_REG_R1,
    UC_ARM_REG_R2,
    UC_ARM_REG_R3,
    UC_ARM_REG_SP,
)

ROOT = Path("/Users/max/Work/Pet/3ds-ua")
sys.path.insert(0, str(ROOT / "tools"))

import smdh_names  # noqa: E402
from build import apply_homoglyphs, load_homoglyphs  # noqa: E402
from luma_hook import (  # noqa: E402
    HOOK_PATCHES,
    LUMA_PATH_SIZE,
    LUMA_PAYLOAD_SIZE,
    TEXT_VA,
    THUNK_CALL_OFFSET,
)

TID = "0004001000022000"
CODE = ROOT / "work" / TID / f"{TID}.dec.code"
IPS = ROOT / "dist" / "luma" / "titles" / TID / "code.ips"

SMDH_SIZE = 0x36C0
LANG_INDEX = HOOK_PATCHES[TID]["smdh_hook"]["lang_index"]
READER = TEXT_VA + HOOK_PATCHES[TID]["smdh_hook"]["reader_off"]
THUNKS = [TEXT_VA + off for off in HOOK_PATCHES[TID]["smdh_hook"]["thunks"]]

BASE = 0x100000
IMAGE_ROOM = 0x200000
STACK = 0x8000000
STACK_SIZE = 0x10000
HEAP = 0x9000000
HEAP_SIZE = 0x10000
DONE = 0xF0000000

RUSSIAN_SHORT = "Площадь StreetPass Mii"
RUSSIAN_LONG = "Площадь\nStreetPass Mii"


def apply_ips(code: bytearray, ips: bytes) -> list[tuple[int, int]]:
    assert ips[:5] == b"PATCH" and ips[-3:] == b"EOF"
    written = []
    at = 5
    while at < len(ips) - 3:
        offset = int.from_bytes(ips[at:at + 3], "big")
        size = int.from_bytes(ips[at + 3:at + 5], "big")
        code[offset:offset + size] = ips[at + 5:at + 5 + size]
        written.append((offset, size))
        at += 5 + size
    return written


def luma_writes(code: bytearray, text_size: int, ro_off: int, ro_size: int) -> None:
    """The two blobs Luma lays down after the IPS, at the front of each padding."""
    rounded = lambda value: (value + 0xFFF) & ~0xFFF  # noqa: E731
    code[text_size:text_size + LUMA_PAYLOAD_SIZE] = b"\xA5" * LUMA_PAYLOAD_SIZE
    path = f"lf:/luma/titles/{TID}/romfs".encode()
    front = ro_off + ro_size
    code[front:front + LUMA_PATH_SIZE] = path.ljust(LUMA_PATH_SIZE, b"\0")
    assert rounded(text_size) >= text_size + LUMA_PAYLOAD_SIZE


def fake_smdh() -> bytes:
    """A buffer the way the reader leaves it: Russian in the slot the mod rewrites."""
    buffer = bytearray(SMDH_SIZE)
    buffer[0:4] = b"SMDH"
    short_at, long_at = smdh_names.slot_offsets(LANG_INDEX)
    buffer[short_at:short_at + len(RUSSIAN_SHORT) * 2] = RUSSIAN_SHORT.encode("utf-16-le")
    buffer[long_at:long_at + len(RUSSIAN_LONG) * 2] = RUSSIAN_LONG.encode("utf-16-le")
    return bytes(buffer)


def read_slot(uc: Uc, buffer_va: int) -> tuple[str, str]:
    short_at, long_at = smdh_names.slot_offsets(LANG_INDEX)

    def utf16(at: int, limit: int) -> str:
        raw = uc.mem_read(buffer_va + at, limit * 2)
        text = raw.decode("utf-16-le")
        return text.split("\0")[0]

    return utf16(short_at, 0x40), utf16(long_at, 0x80)


def run(image: bytes, thunk: int, tid: int, mediatype: int, fail: bool) -> dict:
    uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    uc.mem_map(BASE, IMAGE_ROOM)
    uc.mem_write(BASE, image)
    uc.mem_map(STACK, STACK_SIZE)
    uc.mem_map(HEAP, HEAP_SIZE)
    uc.mem_write(HEAP, fake_smdh())

    seen: dict = {"reader_calls": 0, "mediatype": None}

    def on_code(uc: Uc, address: int, size: int, _user) -> None:
        if address != READER:
            return
        seen["reader_calls"] += 1
        # The reader takes its mediatype as a fifth argument, off the caller's stack. This is
        # the invariant the wrapper's sub/str dance exists for.
        seen["mediatype"] = struct.unpack("<I", uc.mem_read(uc.reg_read(UC_ARM_REG_SP), 4))[0]
        seen["buffer"] = uc.reg_read(UC_ARM_REG_R0)
        seen["tid"] = (
            uc.reg_read(UC_ARM_REG_R2) | uc.reg_read(UC_ARM_REG_R3) << 32
        )
        if not fail:
            uc.mem_write(seen["buffer"], fake_smdh())
        uc.reg_write(UC_ARM_REG_R0, 0xC8804632 - (1 << 32) if fail else 0)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    uc.hook_add(UC_HOOK_CODE, on_code, begin=BASE, end=BASE + IMAGE_ROOM)

    uc.reg_write(UC_ARM_REG_SP, STACK + STACK_SIZE - 0x100)
    uc.reg_write(UC_ARM_REG_R0, HEAP)
    uc.reg_write(UC_ARM_REG_R1, 1)
    uc.reg_write(UC_ARM_REG_R2, tid & 0xFFFFFFFF)
    uc.reg_write(UC_ARM_REG_R3, tid >> 32)
    uc.reg_write(UC_ARM_REG_LR, DONE)
    uc.emu_start(thunk, DONE, count=200000)

    short, long = read_slot(uc, HEAP)
    return {
        "result": uc.reg_read(UC_ARM_REG_R0),
        "sp": uc.reg_read(UC_ARM_REG_SP),
        "short": short,
        "long": long,
        **seen,
    }


def main() -> int:
    exheader = (ROOT / "work" / TID / "extheader.bin").read_bytes()
    text_size = struct.unpack_from("<I", exheader, 0x18)[0]
    ro_size = struct.unpack_from("<I", exheader, 0x28)[0]
    rounded = lambda value: (value + 0xFFF) & ~0xFFF  # noqa: E731

    image = bytearray(CODE.read_bytes())
    written = apply_ips(image, IPS.read_bytes())
    luma_writes(image, text_size, rounded(text_size), ro_size)
    for offset, size in written:
        if offset < text_size + LUMA_PAYLOAD_SIZE and offset + size > text_size:
            raise SystemExit(f"record at 0x{offset:X} shares Luma's payload space")

    names = {
        tid: entry
        for tid, entry in json.loads(
            (ROOT / "src" / "app_names.json").read_text(encoding="utf-8")
        ).items()
        if not tid.startswith("_")
    }

    # The table ships with homoglyphs applied, the way romfs strings do.
    homoglyphs = load_homoglyphs()
    expected_sp = STACK + STACK_SIZE - 0x100
    failures = []
    for thunk in THUNKS:
        mediatype = struct.unpack_from(
            "<I", bytes(image), thunk - TEXT_VA + 4
        )[0] & 0xFF
        for tid, entry in names.items():
            got = run(bytes(image), thunk, int(tid, 16), mediatype, fail=False)
            want_short = apply_homoglyphs(entry["ua"], homoglyphs)
            want_long = apply_homoglyphs(entry.get("ua_long") or entry["ua"], homoglyphs)
            ok = (
                got["short"] == want_short
                and got["long"] == want_long
                and got["result"] == 0
                and got["mediatype"] == mediatype
                and got["sp"] == expected_sp
            )
            print(
                f"{'ok ' if ok else 'FAIL'} thunk 0x{thunk:X} mediatype {mediatype} {tid} "
                f"-> {got['short']!r} / {got['long']!r} result 0x{got['result']:X} "
                f"mediatype seen {got['mediatype']} sp {'kept' if got['sp'] == expected_sp else 'LOST'}"
            )
            if not ok:
                failures.append((tid, thunk, got))

    # A title the table does not list keeps whatever the reader wrote.
    stranger = run(bytes(image), THUNKS[0], 0x0004001000099900, 1, fail=False)
    print(
        f"{'ok ' if stranger['short'] == RUSSIAN_SHORT else 'FAIL'} unlisted title left alone "
        f"-> {stranger['short']!r}"
    )
    if stranger["short"] != RUSSIAN_SHORT:
        failures.append(("unlisted", THUNKS[0], stranger))

    # A failed read must reach the caller as the negative result it was, untouched.
    failed = run(bytes(image), THUNKS[0], 0x0004001000022800, 1, fail=True)
    negative = failed["result"] & 0x80000000
    print(
        f"{'ok ' if negative else 'FAIL'} failed read passed through -> "
        f"0x{failed['result']:X}, buffer {failed['short']!r}"
    )
    if not negative:
        failures.append(("failed read", THUNKS[0], failed))

    print(f"\n{len(failures)} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
