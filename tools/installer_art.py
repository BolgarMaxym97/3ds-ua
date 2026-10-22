"""The installer app's HOME Menu art, in the style of its own screens (installer/source/ui.h).

    icon.png    48x48: an open 3DS in the flag's colours, UA on its top screen
    banner.png  256x128: the top screen while the app is selected on the HOME Menu
    banner.wav  the banner's sound: a short soft two-note chime

The HOME Menu draws icons without transparency, so the console sits on the app's light
ground. Text is Nunito 800, the app's own UI font (OFL, installer/assets/fonts), instanced
by `make installer-fonts`.

Usage (`make installer-art`):
    python3 tools/installer_art.py dist_installer/fonts/Nunito-800.ttf dist_installer/art
"""

from __future__ import annotations

import math
import struct
import sys
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BLUE = (0x14, 0x58, 0xC7)
YELLOW = (0xF5, 0xC4, 0x00)
INK = (0x1B, 0x24, 0x33)
BODY = (0x3A, 0x45, 0x56)
GROUND = (0xE4, 0xE8, 0xEF)
CONTROL = (0x5A, 0x66, 0x78)
SCALE = 8  # drawn large, scaled down: smooth edges at 48 px


def badge(size: int, font: Path) -> Image.Image:
    """An open 3DS in the app's palette, `size` px square: the top screen blue with a white
    UA, the touch screen yellow; Circle Pad and D-pad on the left, ABXY on the right."""
    s = size * SCALE
    u = s / 48
    im = Image.new("RGB", (s, s), GROUND)
    d = ImageDraw.Draw(im)

    def box(x0: float, y0: float, x1: float, y1: float) -> list[float]:
        return [x0 * u, y0 * u, x1 * u, y1 * u]

    def dot(cx: float, cy: float, r: float, fill: tuple[int, int, int]) -> None:
        d.ellipse(box(cx - r, cy - r, cx + r, cy + r), fill=fill)

    d.rounded_rectangle(box(6, 3, 42, 23), 4 * u, fill=INK)
    d.rounded_rectangle(box(9, 5.5, 39, 20.5), 2 * u, fill=BLUE)
    face = ImageFont.truetype(str(font), round(11 * u))
    left, top, right, bottom = d.textbbox((0, 0), "UA", font=face)
    d.text((24 * u - (right - left) / 2 - left, 13 * u - (bottom - top) / 2 - top), "UA", font=face, fill=(255, 255, 255))

    d.rounded_rectangle(box(6, 25, 42, 45), 4 * u, fill=INK)
    d.rounded_rectangle(box(14, 27.5, 34, 42.5), 1.5 * u, fill=YELLOW)
    dot(10, 30, 2.2, CONTROL)                                    # Circle Pad
    d.rectangle(box(9.2, 35, 10.8, 41), fill=CONTROL)            # D-pad
    d.rectangle(box(7, 37.2, 13, 38.8), fill=CONTROL)
    for dx, dy in ((0, -2.2), (0, 2.2), (-2.2, 0), (2.2, 0)):    # A B X Y
        dot(38 + dx, 33 + dy, 1.1, CONTROL)
    return im.resize((size, size), Image.LANCZOS)


def banner(font: Path) -> Image.Image:
    w, h = 256, 128
    im = Image.new("RGB", (w * SCALE, h * SCALE), GROUND)
    draw = ImageDraw.Draw(im)
    title = ImageFont.truetype(str(font), 22 * SCALE)
    sub = ImageFont.truetype(str(font), 12 * SCALE)
    draw.text((92 * SCALE, 38 * SCALE), "Українізатор", font=title, fill=INK)
    draw.text((92 * SCALE, 63 * SCALE), "3DS", font=title, fill=INK)
    draw.text((92 * SCALE, 92 * SCALE), "Українізація системи", font=sub, fill=BODY)
    im = im.resize((w, h), Image.LANCZOS)
    im.paste(badge(68, font), (16, 30))
    return im


def chime(path: Path) -> None:
    """Two soft notes (E5, A5) with a quick decay, 0.6 s, 16-bit mono."""
    rate, length = 32000, 0.6
    frames = bytearray()
    for i in range(int(rate * length)):
        t = i / rate
        v = 0.0
        for start, freq in ((0.0, 659.25), (0.12, 880.0)):
            if t >= start:
                v += math.sin(2 * math.pi * freq * (t - start)) * math.exp(-(t - start) * 7)
        frames += struct.pack("<h", int(v * 0.25 * 32767))
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(bytes(frames))


def main() -> None:
    font, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    badge(48, font).save(out / "icon.png")
    banner(font).save(out / "banner.png")
    chime(out / "banner.wav")
    print(f"{out}: icon.png, banner.png, banner.wav")


if __name__ == "__main__":
    main()
