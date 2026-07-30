"""MSBT (Nintendo Message Studio Binary Text, `MsgStdBn`) reader and writer.

Layout:
    header 0x20: magic[8] BOM u16 pad u16 encoding u8 version u8 numBlocks u16 pad u16 fileSize u32 reserved[10]
    blocks:      magic[4] size u32 pad[8], then data padded to 16 bytes with 0xAB
    LBL1: u32 numSlots, [u32 count, u32 offset]*, then entries: u8 len, name, u32 msgIndex
    ATR1: u32 numEntries, u32 entrySize, then the attribute blob
    TXT2: u32 numMessages, u32 offsets[], then null-terminated UTF-16LE strings
    TSY1: one u32 style index per message

Inline control codes: 0x000E opens a tag (group u16, type u16, argLen u16, args), 0x000F closes it.
Tags are serialised as {t:group.type:hexargs} / {/t} tokens so the text stays editable.
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field

PADDING = 0xAB
TAG_OPEN = 0x000E
TAG_CLOSE = 0x000F
TOKEN_RE = re.compile(r"\{(/?)t:(\d+)\.(\d+)(?::([0-9a-fA-F]*))?\}")


@dataclass
class Msbt:
    encoding: int
    version: int
    labels: dict[str, int] = field(default_factory=dict)
    texts: list[str] = field(default_factory=list)
    styles: list[int] = field(default_factory=list)
    attributes: bytes = b""
    attr_count: int = 0
    attr_entry_size: int = 0
    label_slots: int = 0
    block_order: list[str] = field(default_factory=list)

    def label_of(self, index: int) -> str | None:
        for name, i in self.labels.items():
            if i == index:
                return name
        return None


def parse(data: bytes) -> Msbt:
    if data[:8] != b"MsgStdBn":
        raise ValueError(f"not an MSBT file: {data[:8]!r}")

    encoding, version = data[0x0C], data[0x0D]
    num_blocks = struct.unpack_from("<H", data, 0x0E)[0]
    msbt = Msbt(encoding=encoding, version=version)

    off = 0x20
    for _ in range(num_blocks):
        magic = data[off : off + 4].decode("ascii")
        size = struct.unpack_from("<I", data, off + 4)[0]
        body = data[off + 16 : off + 16 + size]
        msbt.block_order.append(magic)

        if magic == "LBL1":
            msbt.label_slots, msbt.labels = _parse_lbl1(body)
        elif magic == "ATR1":
            msbt.attr_count, msbt.attr_entry_size = struct.unpack_from("<II", body, 0)
            msbt.attributes = body[8:]
        elif magic == "TXT2":
            msbt.texts = _parse_txt2(body)
        elif magic == "TSY1":
            msbt.styles = list(struct.unpack_from(f"<{len(body) // 4}I", body, 0))
        else:
            raise ValueError(f"unknown MSBT block: {magic}")

        off += 16 + size
        off = (off + 15) & ~15

    return msbt


def build(msbt: Msbt) -> bytes:
    blocks: list[tuple[str, bytes]] = []
    for magic in msbt.block_order:
        if magic == "LBL1":
            blocks.append((magic, _build_lbl1(msbt)))
        elif magic == "ATR1":
            blocks.append((magic, struct.pack("<II", msbt.attr_count, msbt.attr_entry_size) + msbt.attributes))
        elif magic == "TXT2":
            blocks.append((magic, _build_txt2(msbt.texts)))
        elif magic == "TSY1":
            blocks.append((magic, struct.pack(f"<{len(msbt.styles)}I", *msbt.styles)))
        else:
            raise ValueError(f"unknown MSBT block: {magic}")

    out = bytearray(b"MsgStdBn")
    out += struct.pack("<HH", 0xFEFF, 0)
    out += bytes([msbt.encoding, msbt.version])
    out += struct.pack("<HH", len(blocks), 0)
    out += struct.pack("<I", 0)  # file size, filled in below
    out += b"\x00" * 10

    for magic, body in blocks:
        out += magic.encode("ascii")
        out += struct.pack("<I", len(body))
        out += b"\x00" * 8
        out += body
        while len(out) % 16:
            out.append(PADDING)

    struct.pack_into("<I", out, 0x12, len(out))
    return bytes(out)


def _parse_lbl1(body: bytes) -> tuple[int, dict[str, int]]:
    num_slots = struct.unpack_from("<I", body, 0)[0]
    labels: dict[str, int] = {}
    for slot in range(num_slots):
        count, offset = struct.unpack_from("<II", body, 4 + slot * 8)
        pos = offset
        for _ in range(count):
            length = body[pos]
            name = body[pos + 1 : pos + 1 + length].decode("ascii")
            index = struct.unpack_from("<I", body, pos + 1 + length)[0]
            labels[name] = index
            pos += 1 + length + 4
    return num_slots, labels


def _build_lbl1(msbt: Msbt) -> bytes:
    slots: list[list[tuple[str, int]]] = [[] for _ in range(msbt.label_slots)]
    for name, index in msbt.labels.items():
        slots[_label_hash(name, msbt.label_slots)].append((name, index))

    table_size = 4 + msbt.label_slots * 8
    entries = bytearray()
    table = bytearray(struct.pack("<I", msbt.label_slots))
    for slot in slots:
        table += struct.pack("<II", len(slot), table_size + len(entries))
        for name, index in slot:
            entries += bytes([len(name)]) + name.encode("ascii") + struct.pack("<I", index)

    return bytes(table + entries)


def _label_hash(name: str, num_slots: int) -> int:
    h = 0
    for ch in name.encode("ascii"):
        h = (h * 0x492 + ch) & 0xFFFFFFFF
    return h % num_slots


def _parse_txt2(body: bytes) -> list[str]:
    count = struct.unpack_from("<I", body, 0)[0]
    offsets = list(struct.unpack_from(f"<{count}I", body, 4))
    offsets.append(len(body))
    return [_decode_text(body[offsets[i] : offsets[i + 1]]) for i in range(count)]


def _build_txt2(texts: list[str]) -> bytes:
    encoded = [_encode_text(t) for t in texts]
    header_size = 4 + len(texts) * 4
    out = bytearray(struct.pack("<I", len(texts)))
    pos = header_size
    for blob in encoded:
        out += struct.pack("<I", pos)
        pos += len(blob)
    for blob in encoded:
        out += blob
    return bytes(out)


def _decode_text(raw: bytes) -> str:
    out: list[str] = []
    i = 0
    while i < len(raw) - 1:
        code = struct.unpack_from("<H", raw, i)[0]
        if code == TAG_OPEN:
            group, ttype, arg_len = struct.unpack_from("<HHH", raw, i + 2)
            args = raw[i + 8 : i + 8 + arg_len]
            out.append(f"{{t:{group}.{ttype}:{args.hex()}}}")
            i += 8 + arg_len
        elif code == TAG_CLOSE:
            group, ttype = struct.unpack_from("<HH", raw, i + 2)
            out.append(f"{{/t:{group}.{ttype}}}")
            i += 6
        elif code == 0:
            i += 2
            break
        else:
            out.append(chr(code))
            i += 2
    return "".join(out)


def _encode_text(text: str) -> bytes:
    out = bytearray()
    pos = 0
    for m in TOKEN_RE.finditer(text):
        out += text[pos : m.start()].encode("utf-16-le")
        closing, group, ttype, args = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4) or ""
        if closing:
            out += struct.pack("<HHH", TAG_CLOSE, group, ttype)
        else:
            blob = bytes.fromhex(args)
            out += struct.pack("<HHHH", TAG_OPEN, group, ttype, len(blob)) + blob
        pos = m.end()
    out += text[pos:].encode("utf-16-le")
    out += b"\x00\x00"
    return bytes(out)


if __name__ == "__main__":
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent))
    from lz11 import decompress

    path = Path(sys.argv[1])
    raw = path.read_bytes()
    data = decompress(raw) if path.name.endswith("_LZ.bin") else raw

    msbt = parse(data)
    print(f"{path.name}: {len(msbt.texts)} messages, {len(msbt.labels)} labels, blocks {msbt.block_order}")

    rebuilt = build(msbt)
    if rebuilt == data:
        print("round-trip: byte-identical")
    else:
        diff = next((i for i in range(min(len(rebuilt), len(data))) if rebuilt[i] != data[i]), None)
        print(f"round-trip: MISMATCH (size {len(rebuilt)} vs {len(data)}, first byte @0x{diff:X})" if diff else
              f"round-trip: size {len(rebuilt)} vs {len(data)}")

    for name in list(msbt.labels)[:5]:
        print(f"  {name} → {msbt.texts[msbt.labels[name]]!r}")
