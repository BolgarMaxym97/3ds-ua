"""Read and replace 8-bit textures inside a CGFX (3DS graphics container).

Only what the banner needs: find the TXOB entries, and swap the pixels of an 8-bits-per-
pixel one. The language slots of a banner are exactly that - a CGFX holding nothing but the
localised title texture, which the banner model draws over its common geometry.

Eight bits per pixel here means LA4, luminance and alpha a nibble each, but nothing in this
module cares: a pixel is one byte going in and one byte coming out. tools/banner_text.py is
where the format is interpreted.

TXOB field offsets, measured on the banners in work/ and asserted on every read:

    +0x00  'TXOB'
    +0x08  name offset, relative to itself
    +0x14  height          +0x18  width
    +0x40  data length     +0x44  data offset, relative to itself
    +0x4C  bits per pixel

Pixels are stored in 8x8 tiles, tiles in raster order, and inside a tile in Morton
(Z) order. No axis is flipped: decode as written here and the text reads normally.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

MAGIC = b"TXOB"
TILE = 8


@dataclass(frozen=True)
class Texture:
    name: str
    width: int
    height: int
    bpp: int
    data_at: int
    data_len: int


def _morton(index: int) -> tuple[int, int]:
    x = (index & 1) | ((index >> 1) & 2) | ((index >> 2) & 4)
    y = ((index >> 1) & 1) | ((index >> 2) & 2) | ((index >> 3) & 4)
    return x, y


def textures(cgfx: bytes) -> list[Texture]:
    found = []
    at = cgfx.find(MAGIC)
    while at != -1:
        name_at = at + 8 + struct.unpack_from("<I", cgfx, at + 8)[0]
        end = cgfx.index(b"\0", name_at)
        height, width = struct.unpack_from("<II", cgfx, at + 0x14)
        data_len = struct.unpack_from("<I", cgfx, at + 0x40)[0]
        data_at = at + 0x44 + struct.unpack_from("<I", cgfx, at + 0x44)[0]
        bpp = struct.unpack_from("<I", cgfx, at + 0x4C)[0]
        found.append(
            Texture(cgfx[name_at:end].decode(), width, height, bpp, data_at, data_len)
        )
        at = cgfx.find(MAGIC, at + 4)
    return found


def find(cgfx: bytes, name: str) -> Texture:
    for texture in textures(cgfx):
        if texture.name == name:
            return texture
    raise KeyError(f"no texture named {name!r}")


def _check(texture: Texture) -> None:
    if texture.bpp != 8:
        raise ValueError(f"{texture.name}: {texture.bpp} bpp, only 8 is supported")
    if texture.data_len != texture.width * texture.height:
        raise ValueError(f"{texture.name}: data length {texture.data_len} is not w*h")
    if texture.width % TILE or texture.height % TILE:
        raise ValueError(f"{texture.name}: {texture.width}x{texture.height} is not tiled by 8")


def unswizzle(cgfx: bytes, texture: Texture) -> bytes:
    """The texture as w*h bytes in raster order, top-left first."""
    _check(texture)
    packed = cgfx[texture.data_at : texture.data_at + texture.data_len]
    out = bytearray(texture.data_len)
    pos = 0
    for tile_y in range(0, texture.height, TILE):
        for tile_x in range(0, texture.width, TILE):
            for index in range(TILE * TILE):
                x, y = _morton(index)
                out[(tile_y + y) * texture.width + tile_x + x] = packed[pos]
                pos += 1
    return bytes(out)


def swizzle(pixels: bytes, texture: Texture) -> bytes:
    """The inverse of unswizzle(): raster order back to 8x8 Morton tiles."""
    _check(texture)
    if len(pixels) != texture.data_len:
        raise ValueError(f"{texture.name}: got {len(pixels)} bytes, want {texture.data_len}")
    out = bytearray(texture.data_len)
    pos = 0
    for tile_y in range(0, texture.height, TILE):
        for tile_x in range(0, texture.width, TILE):
            for index in range(TILE * TILE):
                x, y = _morton(index)
                out[pos] = pixels[(tile_y + y) * texture.width + tile_x + x]
                pos += 1
    return bytes(out)


def replace(cgfx: bytes, name: str, pixels: bytes) -> bytes:
    """A copy of the CGFX with one texture's pixels replaced. Size and format are kept,
    so every offset in the container stays valid and nothing else has to be rewritten."""
    texture = find(cgfx, name)
    packed = swizzle(pixels, texture)
    return cgfx[: texture.data_at] + packed + cgfx[texture.data_at + texture.data_len :]
