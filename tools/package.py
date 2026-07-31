"""Pack the build into a release archive.

Usage:
    python3 tools/package.py 0.1.0

Output: 3ds-ua-<version>.zip laid out the way the user extracts it to the SD card root:
    luma/titles/<TID>/romfs/...
    README.txt

README.txt inside the archive stays in Ukrainian: it is read by end users, not developers.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

README_TXT = """3DS UA — український інтерфейс для Nintendo 3DS (версія {version})

Мод підміняє російський мовний слот українською. Англійська лишається недоторканою.
Потрібна EUR-консоль з Luma3DS.

ПРО ЖУРНАЛ ДІЙ
Його переклад містить правку коду титулу (файли code.ips та exheader.bin) і зроблений
під Журнал дій ВЕРСІЇ 2 для EUR. Це не версія системи: сам титул Nintendo оновлювала
лише двічі, тож версія 2 стоїть на всіх сучасних прошивках, включно з останньою
11.17.0-50. Спеціально нічого перевіряти не треба.
Якщо Журнал дій усе ж крешить — у вас старіший білд титулу. Видаліть папку
luma/titles/0004001000022200, решта перекладу працюватиме як раніше.

ВСТАНОВЛЕННЯ
1. Розпакуйте вміст цього архіву в корінь SD-карти (папка luma має злитися з наявною).
2. Вставте SD у консоль. Тримайте SELECT і увімкніть консоль.
3. Увімкніть "Enable game patching" (кнопка A), натисніть START — зберегти й перезавантажити.
4. System Settings -> Other Settings -> Language -> Українська (пункт, де було "Русский").
5. Перезавантажте консоль.

ВИДАЛЕННЯ
Видаліть папки мода з luma/titles/ на SD-карті,
або переключіть мову консолі на будь-яку іншу.

Повна інструкція: https://github.com/BolgarMaxym97/3ds-ua
"""


def main() -> None:
    version = sys.argv[1] if len(sys.argv) > 1 else "dev"
    dist = ROOT / "dist"
    if not dist.is_dir():
        raise SystemExit("no dist/ directory - run `make build` first")

    archive = ROOT / f"3ds-ua-{version}.zip"
    # Finder litters dist/ with .DS_Store; those must not reach the SD card.
    files = sorted(
        p for p in dist.rglob("*") if p.is_file() and not any(part.startswith(".") for part in p.parts)
    )
    if not files:
        raise SystemExit("dist/ is empty")

    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            zf.write(path, path.relative_to(dist))
        zf.writestr("README.txt", README_TXT.format(version=version))

    total = sum(p.stat().st_size for p in files)
    print(f"{archive.name}: {len(files)} files, {total} bytes -> {archive.stat().st_size} bytes")
    for path in files:
        print(f"  {path.relative_to(dist)}")


if __name__ == "__main__":
    main()
