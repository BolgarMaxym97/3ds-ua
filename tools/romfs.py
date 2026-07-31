"""Build and read a 3DS RomFS level 3 image.

This is the plain RomFS the FS module hands over when a title opens ARCHIVE_ROMFS - no
IVFC wrapper and no hash tree, just the directory/file tables and the data. Titles that
parse it themselves never see the IVFC layers, which is why an image built here can stand
in for the real one.

Layout, all offsets counted from the start of the image:

    0x00  header, 0x28 bytes
          directory hash table   u32 per bucket, 0xFFFFFFFF when empty
          directory metadata     linked entries, offsets are into this table
          file hash table
          file metadata
          file data              each file aligned to 0x10

A lookup walks the path from the root, hashing (parent entry offset, name) into the bucket
table and following `next_hash` until the name matches - so the order entries are written
in carries no meaning, only the links do.

Usage:
    python3 tools/romfs.py build <directory> <image>
    python3 tools/romfs.py list <image>
    python3 tools/romfs.py selftest <directory>   # build, read back, compare with the tree
"""

from __future__ import annotations

import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

HEADER_SIZE = 0x28
NONE = 0xFFFFFFFF
DATA_ALIGN = 0x10
DIR_ENTRY_FIXED = 0x18
FILE_ENTRY_FIXED = 0x20


def hash_table_length(entry_count: int) -> int:
    """Bucket count Nintendo's tooling picks: small counts are odd, larger ones coprime."""
    count = entry_count
    if entry_count < 3:
        count = 3
    elif entry_count < 19:
        count |= 1
    else:
        while any(count % p == 0 for p in (2, 3, 5, 7, 11, 13, 17)):
            count += 1
    return count


def path_hash(parent_offset: int, name: str) -> int:
    """Hash of (parent entry offset, UTF-16 name), as the on-console reader computes it."""
    value = (parent_offset ^ 123456789) & 0xFFFFFFFF
    raw = name.encode("utf-16-le")
    for unit in struct.unpack(f"<{len(raw) // 2}H", raw):
        value = ((value >> 5) | (value << 27)) & 0xFFFFFFFF
        value ^= unit
    return value


def _aligned_name(name: str) -> bytes:
    raw = name.encode("utf-16-le")
    return raw + b"\0" * (-len(raw) % 4)


@dataclass
class _Dir:
    name: str
    parent: "_Dir | None"
    dirs: list["_Dir"] = field(default_factory=list)
    files: list["_File"] = field(default_factory=list)
    offset: int = 0


@dataclass
class _File:
    name: str
    parent: _Dir
    data: bytes
    offset: int = 0
    data_offset: int = 0


def _scan(root: Path, overrides: dict[str, bytes]) -> _Dir:
    unused = set(overrides)

    def walk(path: Path, name: str, parent: _Dir | None, prefix: str) -> _Dir:
        node = _Dir(name, parent)
        for child in sorted(path.iterdir(), key=lambda p: p.name):
            if child.name.startswith("."):
                continue  # Finder litter never belongs in an image
            if child.is_dir():
                node.dirs.append(walk(child, child.name, node, f"{prefix}{child.name}/"))
            elif child.is_file():
                key = f"{prefix}{child.name}"
                unused.discard(key)
                node.files.append(_File(child.name, node, overrides.get(key, child.read_bytes())))
        return node

    tree = walk(root, "", None, "")
    if unused:
        # A typo in an override would silently ship the original file instead.
        raise KeyError(f"overrides not present in {root}: {', '.join(sorted(unused))}")
    return tree


def _flatten(root: _Dir) -> tuple[list[_Dir], list[_File]]:
    dirs: list[_Dir] = []
    files: list[_File] = []

    def visit(node: _Dir) -> None:
        dirs.append(node)
        files.extend(node.files)
        for child in node.dirs:
            visit(child)

    visit(root)
    return dirs, files


def build(root_path: Path, overrides: dict[str, bytes] | None = None) -> bytes:
    """Image of the tree at `root_path`, with `overrides` (paths relative to it) swapped in."""
    root = _scan(root_path, overrides or {})
    dirs, files = _flatten(root)

    offset = 0
    for node in dirs:
        node.offset = offset
        offset += DIR_ENTRY_FIXED + len(_aligned_name(node.name))
    dir_meta_size = offset

    offset = 0
    for item in files:
        item.offset = offset
        offset += FILE_ENTRY_FIXED + len(_aligned_name(item.name))
    file_meta_size = offset

    offset = 0
    for item in files:
        item.data_offset = offset
        offset += len(item.data) + (-len(item.data) % DATA_ALIGN)
    file_data_size = offset

    dir_buckets = [NONE] * hash_table_length(len(dirs))
    file_buckets = [NONE] * hash_table_length(len(files))
    dir_next = {node.offset: NONE for node in dirs}
    file_next = {item.offset: NONE for item in files}

    # Chain newest-first into its bucket; the reader walks the chain until the name matches.
    for node in dirs:
        index = path_hash(node.parent.offset if node.parent else 0, node.name) % len(dir_buckets)
        dir_next[node.offset] = dir_buckets[index]
        dir_buckets[index] = node.offset
    for item in files:
        index = path_hash(item.parent.offset, item.name) % len(file_buckets)
        file_next[item.offset] = file_buckets[index]
        file_buckets[index] = item.offset

    dir_hash_off = HEADER_SIZE
    dir_meta_off = dir_hash_off + len(dir_buckets) * 4
    file_hash_off = dir_meta_off + dir_meta_size
    file_meta_off = file_hash_off + len(file_buckets) * 4
    file_data_off = file_meta_off + file_meta_size
    file_data_off += -file_data_off % DATA_ALIGN

    out = bytearray()
    out += struct.pack(
        "<10I", HEADER_SIZE,
        dir_hash_off, len(dir_buckets) * 4,
        dir_meta_off, dir_meta_size,
        file_hash_off, len(file_buckets) * 4,
        file_meta_off, file_meta_size,
        file_data_off,
    )
    out += struct.pack(f"<{len(dir_buckets)}I", *dir_buckets)

    for node in dirs:
        name = _aligned_name(node.name)
        out += struct.pack(
            "<6I",
            node.parent.offset if node.parent else 0,
            _sibling(node.parent.dirs, node) if node.parent else NONE,
            node.dirs[0].offset if node.dirs else NONE,
            node.files[0].offset if node.files else NONE,
            dir_next[node.offset],
            len(node.name.encode("utf-16-le")),
        )
        out += name

    out += struct.pack(f"<{len(file_buckets)}I", *file_buckets)

    for item in files:
        name = _aligned_name(item.name)
        out += struct.pack(
            "<2I", item.parent.offset, _sibling(item.parent.files, item)
        )
        out += struct.pack("<2Q", item.data_offset, len(item.data))
        out += struct.pack("<2I", file_next[item.offset], len(item.name.encode("utf-16-le")))
        out += name

    out += b"\0" * (file_data_off - len(out))
    for item in files:
        out += item.data
        out += b"\0" * (-len(item.data) % DATA_ALIGN)

    assert len(out) == file_data_off + file_data_size, "image length does not match the header"
    return bytes(out)


def _sibling(siblings: list, node) -> int:
    index = siblings.index(node)
    return siblings[index + 1].offset if index + 1 < len(siblings) else NONE


def read(image: bytes) -> dict[str, bytes]:
    """Read an image back into {posix path: contents}, following the links the way FS does."""
    (header_size, _dir_hash_off, _dir_hash_len, dir_meta_off, _dir_meta_len,
     _file_hash_off, _file_hash_len, file_meta_off, _file_meta_len,
     file_data_off) = struct.unpack_from("<10I", image, 0)
    if header_size != HEADER_SIZE:
        raise ValueError(f"header says 0x{header_size:X} bytes, expected 0x{HEADER_SIZE:X}")

    out: dict[str, bytes] = {}

    def read_file(offset: int, prefix: str) -> None:
        while offset != NONE:
            base = file_meta_off + offset
            _parent, sibling = struct.unpack_from("<2I", image, base)
            data_offset, data_length = struct.unpack_from("<2Q", image, base + 8)
            name_length = struct.unpack_from("<I", image, base + 0x1C)[0]
            name = image[base + 0x20:base + 0x20 + name_length].decode("utf-16-le")
            start = file_data_off + data_offset
            out[f"{prefix}/{name}"] = image[start:start + data_length]
            offset = sibling

    def read_dir(offset: int, prefix: str) -> None:
        while offset != NONE:
            base = dir_meta_off + offset
            _parent, sibling, first_child, first_file, _next, name_length = struct.unpack_from(
                "<6I", image, base
            )
            name = image[base + 0x18:base + 0x18 + name_length].decode("utf-16-le")
            here = f"{prefix}/{name}" if name else prefix
            read_file(first_file, here)
            read_dir(first_child, here)
            offset = sibling if prefix or name else NONE  # the root has no siblings

    read_dir(0, "")
    return out


def lookup(image: bytes, path: str) -> bytes:
    """Resolve a path the way the console does: hash into a bucket, walk the chain.

    Deliberately not sharing code with read(): read() follows the sibling links, this
    follows the hash tables, and only doing both proves the two agree.
    """
    (_h, dir_hash_off, dir_hash_len, dir_meta_off, _dml,
     file_hash_off, file_hash_len, file_meta_off, _fml, file_data_off) = struct.unpack_from(
        "<10I", image, 0
    )

    def bucket(table_off: int, table_len: int, parent: int, name: str) -> int:
        index = path_hash(parent, name) % (table_len // 4)
        return struct.unpack_from("<I", image, table_off + index * 4)[0]

    parent = 0
    parts = [p for p in path.split("/") if p]
    for part in parts[:-1]:
        entry = bucket(dir_hash_off, dir_hash_len, parent, part)
        while entry != NONE:
            base = dir_meta_off + entry
            entry_parent, nxt = struct.unpack_from("<I", image, base)[0], struct.unpack_from(
                "<I", image, base + 0x10
            )[0]
            name_length = struct.unpack_from("<I", image, base + 0x14)[0]
            # A chain mixes entries from every parent that hashed here, so the parent has
            # to match as well - names repeat across the language directories.
            if (entry_parent == parent
                    and image[base + 0x18:base + 0x18 + name_length].decode("utf-16-le") == part):
                break
            entry = nxt
        if entry == NONE:
            raise KeyError(f"directory {part!r} not found under offset {parent}")
        parent = entry

    entry = bucket(file_hash_off, file_hash_len, parent, parts[-1])
    while entry != NONE:
        base = file_meta_off + entry
        entry_parent = struct.unpack_from("<I", image, base)[0]
        nxt = struct.unpack_from("<I", image, base + 0x18)[0]
        name_length = struct.unpack_from("<I", image, base + 0x1C)[0]
        if (entry_parent == parent
                and image[base + 0x20:base + 0x20 + name_length].decode("utf-16-le") == parts[-1]):
            data_offset, data_length = struct.unpack_from("<2Q", image, base + 8)
            start = file_data_off + data_offset
            return image[start:start + data_length]
        entry = nxt
    raise KeyError(f"file {parts[-1]!r} not found under offset {parent}")


def _selftest(root_path: Path) -> int:
    image = build(root_path)
    got = read(image)
    want = {
        "/" + str(p.relative_to(root_path)): p.read_bytes()
        for p in sorted(root_path.rglob("*"))
        if p.is_file() and not any(part.startswith(".") for part in p.relative_to(root_path).parts)
    }
    print(f"{root_path}: {len(image)} bytes, {len(want)} files")
    missing = sorted(set(want) - set(got))
    extra = sorted(set(got) - set(want))
    differing = sorted(k for k in set(want) & set(got) if want[k] != got[k])
    for label, items in (("missing", missing), ("unexpected", extra), ("corrupted", differing)):
        for name in items:
            print(f"  !! {label}: {name}")
    if missing or extra or differing:
        return 1
    print(f"  sibling walk ok: {len(want)} files came back byte-for-byte")

    unreachable = []
    for name, data in want.items():
        try:
            if lookup(image, name) != data:
                unreachable.append(f"{name} (hash lookup returned different bytes)")
        except KeyError as exc:
            unreachable.append(f"{name} ({exc})")
    for line in unreachable:
        print(f"  !! {line}")
    if unreachable:
        return 1
    print(f"  hash lookup ok: every file resolves through the hash tables too")
    return 0


def main() -> None:
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    command = sys.argv[1]
    if command == "build":
        Path(sys.argv[3]).write_bytes(build(Path(sys.argv[2])))
    elif command == "list":
        for name, data in sorted(read(Path(sys.argv[2]).read_bytes()).items()):
            print(f"{len(data):>10}  {name}")
    elif command == "selftest":
        sys.exit(_selftest(Path(sys.argv[2])))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
