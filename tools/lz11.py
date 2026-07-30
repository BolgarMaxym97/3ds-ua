"""LZ11 (Nintendo LZ77 type 0x11) decompression and compression.

Format: [0x11][decompressed size u24] (if 0, a u32 size follows), then the stream:
one flag byte (8 bits, MSB first) where 0 = literal byte, 1 = back-reference.
"""

from __future__ import annotations

import struct


def decompress(data: bytes) -> bytes:
    if not data or data[0] != 0x11:
        raise ValueError(f"not LZ11: first byte {data[:1].hex()}")

    size = int.from_bytes(data[1:4], "little")
    pos = 4
    if size == 0:
        size = struct.unpack_from("<I", data, pos)[0]
        pos += 4

    out = bytearray()
    while len(out) < size:
        flags = data[pos]
        pos += 1
        for bit in range(7, -1, -1):
            if len(out) >= size:
                break
            if not (flags >> bit) & 1:
                out.append(data[pos])
                pos += 1
                continue

            b1 = data[pos]
            indicator = b1 >> 4
            if indicator == 0:
                b2, b3 = data[pos + 1], data[pos + 2]
                length = (((b1 & 0xF) << 4) | (b2 >> 4)) + 0x11
                disp = (((b2 & 0xF) << 8) | b3) + 1
                pos += 3
            elif indicator == 1:
                b2, b3, b4 = data[pos + 1], data[pos + 2], data[pos + 3]
                length = (((b1 & 0xF) << 12) | (b2 << 4) | (b3 >> 4)) + 0x111
                disp = (((b3 & 0xF) << 8) | b4) + 1
                pos += 4
            else:
                b2 = data[pos + 1]
                length = indicator + 1
                disp = (((b1 & 0xF) << 8) | b2) + 1
                pos += 2

            if disp > len(out):
                raise ValueError(f"displacement {disp} exceeds {len(out)} bytes of output")
            start = len(out) - disp
            for i in range(length):
                out.append(out[start + i])

    return bytes(out[:size])


def compress(data: bytes) -> bytes:
    """LZ11 compression: greedy longest-match search over a 4096-byte window."""
    size = len(data)
    header = b"\x11" + size.to_bytes(3, "little") if size <= 0xFFFFFF else b"\x11\x00\x00\x00" + struct.pack("<I", size)

    out = bytearray(header)
    pos = 0
    while pos < size:
        flag_index = len(out)
        out.append(0)
        flags = 0
        for bit in range(7, -1, -1):
            if pos >= size:
                break
            length, disp = _find_match(data, pos)
            if length >= 3:
                flags |= 1 << bit
                out += _encode_ref(length, disp)
                pos += length
            else:
                out.append(data[pos])
                pos += 1
        out[flag_index] = flags

    return bytes(out)


def _find_match(data: bytes, pos: int) -> tuple[int, int]:
    size = len(data)
    max_len = min(0x10110, size - pos)
    if max_len < 3:
        return 0, 0

    window_start = max(0, pos - 4096)
    best_len, best_disp = 0, 0
    chunk = data[pos : pos + 3]
    search = data.rfind(chunk, window_start, pos + 2)
    while search != -1:
        length = 3
        while length < max_len and data[search + length] == data[pos + length]:
            length += 1
        if length > best_len:
            best_len, best_disp = length, pos - search
            if length == max_len:
                break
        search = data.rfind(chunk, window_start, search + 2)

    return best_len, best_disp


def _encode_ref(length: int, disp: int) -> bytes:
    d = disp - 1
    if length <= 0x10:
        return bytes([((length - 1) << 4) | (d >> 8), d & 0xFF])
    if length <= 0x110:
        n = length - 0x11
        return bytes([n >> 4, ((n & 0xF) << 4) | (d >> 8), d & 0xFF])
    n = length - 0x111
    return bytes([0x10 | (n >> 12), (n >> 4) & 0xFF, ((n & 0xF) << 4) | (d >> 8), d & 0xFF])


if __name__ == "__main__":
    import sys

    path = sys.argv[1]
    with open(path, "rb") as f:
        raw = f.read()
    plain = decompress(raw)
    print(f"{path}: {len(raw)} -> {len(plain)} bytes, magic {plain[:4]!r}")
    repacked = compress(plain)
    assert decompress(repacked) == plain, "round-trip broken"
    print(f"round-trip ok, our packer: {len(repacked)} bytes ({len(repacked) / len(raw):.2f}x of the original)")
