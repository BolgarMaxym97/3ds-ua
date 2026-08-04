"""Disassemble a VA range of a decrypted .code dump. Usage: dis.py <va> <count> [file]"""

import struct
import sys
from pathlib import Path

from capstone import CS_ARCH_ARM, CS_MODE_ARM, Cs

ROOT = Path("/Users/max/Work/Pet/3ds-ua")
DEFAULT = ROOT / "work/0004001000022000/0004001000022000.dec.code"

TEXT_VA = 0x100000


def load(path=DEFAULT):
    return path.read_bytes()


def dis(va, count, data=None):
    data = data if data is not None else load()
    off = va - TEXT_VA
    md = Cs(CS_ARCH_ARM, CS_MODE_ARM)
    md.detail = False
    out = []
    for ins in md.disasm(data[off:off + count * 4], va):
        out.append(f"{ins.address:08X}  {ins.mnemonic:<8} {ins.op_str}")
    return "\n".join(out)


def word(data, va):
    return struct.unpack_from("<I", data, va - TEXT_VA)[0]


if __name__ == "__main__":
    va = int(sys.argv[1], 16)
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 32
    path = Path(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT
    print(dis(va, count, load(path)))
