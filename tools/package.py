"""Pack the build into a release archive.

Usage:
    python3 tools/package.py 0.1.0
    python3 tools/package.py 0.1.0 --slot en

Output: 3ds-ua-from-<slot>-<version>.zip, laid out the way the user extracts it to the SD
card root:
    luma/titles/<TID>/romfs/...
    README.txt

One archive per language slot the mod can stand in - `from-ru` out of dist/, `from-en` out
of dist_en/, see tools/variant.py. The two hold the same translation and differ only in
which language of the console it replaces, so README.txt says which one this is.

README.txt inside the archive stays in Ukrainian: it is read by end users, not developers.
"""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import variant  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

# The one thing the two builds say differently: which language the mod stands in place of,
# and therefore which one the console keeps.
SLOT_WORDS = {
    "ru": {"replaced": "російський", "kept": "Англійська", "left_pl": "російськими", "left_ms": "російським"},
    "en": {"replaced": "англійський", "kept": "Російська", "left_pl": "англійськими", "left_ms": "англійським"},
}

README_TXT = """3DS UA — український інтерфейс для Nintendo 3DS (версія {version}, збірка from-{slot})

Мод підміняє {replaced} мовний слот українською. {kept} лишається недоторканою.
Потрібна EUR-консоль з Luma3DS.

ЩО ПЕРЕКЛАДЕНО (31 частина системи)
Меню HOME, Налаштування системи, Mii Maker, Журнал дій, Електронний посібник,
Гра по завантаженню, екранна клавіатура, Список друзів, Камера Nintendo 3DS,
швидка камера на L+R, Звук Nintendo 3DS, Здоров'я і безпека,
Площа StreetPass Mii, Вибір Mii, Сповіщення, Ігрові записи, екран помилки,
Інтернет-браузер, Nintendo eShop, Перенесення даних, Оглядач Nintendo Zone,
Face Raiders, AR Games, Налаштування amiibo, аплет покупок і оновлень eShop,
3DS Memo, аплет Circle Pad Pro, Miiverse, публікація в Miiverse,
Дані Nintendo Network ID, тексти помилок системи.
Плюс електронні довідники одинадцяти додатків — Інтернет-браузера, Налаштувань
системи, Журналу дій, Гри по завантаженню, Камери, Звуку, Mii Maker, Площі
StreetPass Mii, Nintendo eShop, Face Raiders і AR Games, — разом із назвою
додатка над сторінкою і пунктом "Українська" в перемикачі мови довідника.
Плюс список країн і регіонів у налаштуваннях профілю та на Карті StreetPass:
усі 67 країн і 83 області коду 100, і назва панелі в Обміні частинками.

УКРАЇНИ В СПИСКУ КРАЇН НЕМАЄ
У таблиці кодів країн Nintendo її немає взагалі: європейський блок суцільний,
...99 Румунія, 100 Росія, 101 Сербія... Нового рядка в таблицю не вставити —
код країни це системна величина, від якої залежать NNID, eShop і вікові
рейтинги. Перейменувати код 100 на "Україна" мод колись пробував, але назву
за цим кодом кожен читає своєю таблицею: в онлайні, NNID, eShop і StreetPass
однаково стояла "Росія", а українська область показувалася їм російською з тим
самим номером. Тепер список показує те, що консоль справді повідомляє: код 100
це "росія (болота)" з її ж 83 областями, усе з малої літери.
Мова й країна в 3DS ніяк не пов'язані: переклад стоїть на мовному слоті, тому
інтерфейс лишиться повністю українським з будь-якою країною в профілі.

НАЗВИ ДОДАТКІВ
Назви додатків (підпис під іконкою, "Призупинена програма", діалоги закриття
й видалення) лежать не в перекладних файлах, а в NAND. Тому в папці Меню HOME
є code.ips — він перекладає їх на льоту й зроблений під Меню HOME ВЕРСІЇ 29.
Якщо Меню HOME не запуститься, видаліть спершу ТІЛЬКИ цей файл:
  luma/titles/0004003000009802/code.ips
Решта перекладу Меню HOME працює й без нього.
Той самий code.ips підміняє картинки на верхньому екрані — Налаштувань системи
(banner_22000.bin), Гри по завантаженню (banner_22100.bin), Журналу дій
(banner_22200.bin), Здоров'я і безпеки (banner_22300.bin), Площі StreetPass Mii
(banner_22800.bin) і AR Games (banner_22E00.bin) у тій самій папці. Якщо котрийсь
із цих файлів видалити, Меню HOME не зможе прочитати той банер; на решті
перекладу це не позначиться.
Так само зроблено Керування даними: у папці Налаштувань системи є свій code.ips,
який перекладає назви програм у їхньому списку.
У eShop, Перенесенні даних та Ігрових записах назви поки лишаються {left_pl} —
кожен з них читає їх окремо.

ПРО ТИТУЛИ З ПРАВКОЮ КОДУ
Переклади Налаштувань системи, Журналу дій, Електронного посібника, Списку
друзів, Вибору Mii, Сповіщень, Гри по завантаженню, клавіатури, Здоров'я і
безпеки, швидкої камери, екрана помилки, аплета покупок eShop, 3DS Memo та
аплета Circle Pad Pro містять
правку коду титулу (файли code.ips та exheader.bin) і зроблені під Налаштування
системи ВЕРСІЇ 12, швидку камеру ВЕРСІЇ 2, Журнал дій
ВЕРСІЇ 2, Електронний посібник ВЕРСІЇ 5, Список друзів ВЕРСІЇ 6, Вибір Mii
ВЕРСІЇ 3, Сповіщення ВЕРСІЇ 4, налаштування amiibo ВЕРСІЇ 1, Гру по завантаженню
ВЕРСІЇ 3, клавіатуру ВЕРСІЇ 4, Здоров'я і безпеку ВЕРСІЇ 3, екран помилки
ВЕРСІЇ 7, аплет покупок eShop ВЕРСІЇ 22, 3DS Memo ВЕРСІЇ 3,
аплет Circle Pad Pro ВЕРСІЇ 4, Miiverse ВЕРСІЇ 4 і Дані Nintendo Network ID
ВЕРСІЇ 3 для EUR. Площа StreetPass Mii везе тільки exheader.bin
(без правки коду) і зроблена під ВЕРСІЮ 5. Так само тільки exheader.bin везуть
Nintendo eShop (ВЕРСІЯ 29) і аплет публікації в Miiverse (ВЕРСІЯ 0).
Це не версія системи: самі титули Nintendo оновлювала одиниці разів, тож ці білди
стоять на всіх сучасних прошивках, включно з останньою 11.17.0-50. Спеціально нічого
перевіряти не треба.
Якщо котрийсь із них крешить — у вас старіший білд титулу. Видаліть його папку:
  Налаштування системи  luma/titles/0004001000022000
  Журнал дій            luma/titles/0004001000022200
  Швидка камера (L+R)   luma/titles/0004003000009902
  Електронний посібник  luma/titles/0004003000009B02
  Список друзів         luma/titles/0004003000009F02
  Вибір Mii             luma/titles/000400300000D102
  Сповіщення            luma/titles/000400300000A002
  Налаштування amiibo   luma/titles/000400300000B902
  Екран помилки         luma/titles/000400300000C502
  Площа StreetPass Mii  luma/titles/0004001000022800
  Гра по завантаженню   luma/titles/0004001000022100
  Клавіатура            luma/titles/000400300000D002
  Здоров'я і безпека    luma/titles/0004001000022300
  Аплет покупок eShop   luma/titles/000400300000D602
  3DS Memo              luma/titles/000400300000F602
  Аплет Circle Pad Pro  luma/titles/000400300000CD02
  Nintendo eShop        luma/titles/0004001000022900
  Miiverse              luma/titles/000400300000BE02
  Публікація в Miiverse luma/titles/000400300000BA02
  Дані NNID             luma/titles/000400100002C100
Решта перекладу працюватиме як раніше.

ПРО ВБУДОВАНІ ПІДКАЗКИ У СПОВІЩЕННЯХ
Підказки, які лежать у Сповіщеннях з першого запуску консолі ("Про повідомлення",
"Крокомір", "Ігрові монетки" й інші), консоль не читає з перекладних файлів.
Меню HOME один раз СКОПІЮВАЛО їх текст у власну базу в NAND, і копія застигла
такою, якою прийшла. Тому їх перекладає той самий code.ips Меню HOME —
переписує листи в базі на місці, першого разу після встановлення мода.

УВАГА: це єдина зміна мода, яка лишається після його видалення. У базі лишиться
український текст підказок, а не сміття, і консоль з ним працює нормально —
але {left_ms} він уже не стане. Нові листи (SpotPass, повідомлення від
Nintendo) мод не чіпає взагалі. Якщо цього не хочеться, видаліть
luma/titles/0004003000009802/code.ips ДО першого запуску з модом; тоді підказки
лишаться {left_pl} (разом із назвами додатків і банерами, які той самий
файл перекладає).

ПРО ЕЛЕКТРОННІ ДОВІДНИКИ
Довідник (кнопка "Довідник" у меню HOME) кожен додаток має свій, і лежить він у
самій консолі, а не в перекладних файлах. Тому в папці Електронного посібника, крім тексту
самого переглядача, лежать перекладені довідники окремими файлами:
  luma/titles/0004003000009B02/romfs/00009d02.bcma   Інтернет-браузер
  luma/titles/0004003000009B02/romfs/00022000.bcma   Налаштування системи
  luma/titles/0004003000009B02/romfs/00022100.bcma   Гра по завантаженню
  luma/titles/0004003000009B02/romfs/00022200.bcma   Журнал дій
  luma/titles/0004003000009B02/romfs/00022400.bcma   Камера Nintendo 3DS
  luma/titles/0004003000009B02/romfs/00022500.bcma   Звук Nintendo 3DS
  luma/titles/0004003000009B02/romfs/00022700.bcma   Mii Maker
  luma/titles/0004003000009B02/romfs/00022800.bcma   Площа StreetPass Mii
  luma/titles/0004003000009B02/romfs/00022900.bcma   Nintendo eShop
  luma/titles/0004003000009B02/romfs/00022d00.bcma   Face Raiders
  luma/titles/0004003000009B02/romfs/00022e00.bcma   AR Games
Додатки, для яких файла немає, показують свій рідний довідник — як і до мода.
Назву додатка над сторінкою й пункт мови в перемикачі перекладає code.ips у тій
самій папці; без нього довідники лишаться українськими, а заголовок — {left_ms}.
Якщо котрийсь довідник відкривається неправильно, видаліть його файл; решта
перекладу від цього не залежить.

ТЕКСТИ ПОМИЛОК
Тіла повідомлень про помилки (те, що написано під "Код помилки: XXX-YYYY") лежать
не в титулах, а в окремому системному архіві. Тому перекладений архів
(msg_romfs.bin) везуть дві папки — екрана помилки й Miiverse, — а їхній code.ips
показує титулу, де його шукати. Якщо видалити msg_romfs.bin, а code.ips лишити,
тексти помилок зникнуть — видаляйте папку цілком.

ДАНІ NINTENDO NETWORK ID
Екрани цього розділу — не звичайні системні тексти, а невеликий HTML-застосунок,
який лежить у спільному архіві консолі, а не в самому титулі. Перекладені сторінки
возить папка luma/titles/000400100002C100, а її code.ips показує титулу, що читати
їх треба з SD-карти. Тому папку теж видаляйте тільки цілком.

ОКРЕМО ПРО ГРУ ПО ЗАВАНТАЖЕННЮ, КЛАВІАТУРУ, ЗДОРОВ'Я І БЕЗПЕКУ, ШВИДКУ КАМЕРУ,
ЕКРАН ПОМИЛКИ, 3DS MEMO, АПЛЕТ CIRCLE PAD PRO, MIIVERSE ТА ДАНІ NNID
Перші сім читають свій romfs просто з SD-карти (dlplay_romfs.bin, swkbd_romfs.bin,
safe_romfs.bin, camera_applet_romfs.bin, error_romfs.bin, memolib_romfs.bin,
extrapad_romfs.bin).
Miiverse і Дані Nintendo Network ID так само беруть із SD-карти шрифт рядка з датою
(romfs/font/Hud.bcfnt) — власного вони не мають, а їхній code.ips показує, де його
шукати. Дані NNID беруть звідти ще й сторінки самого розділу.
Тому папки всіх дев'яти можна видаляти ТІЛЬКИ ЦІЛКОМ: якщо прибрати сам файл,
а code.ips лишити, титул перестане завантажуватись або впаде. Решти титулів це
не стосується.

ВСТАНОВЛЕННЯ
1. Розпакуйте вміст цього архіву в корінь SD-карти (папка luma має злитися з наявною).
2. Вставте SD у консоль. Тримайте SELECT і увімкніть консоль.
3. Увімкніть "Enable game patching" (кнопка A), натисніть START — зберегти й перезавантажити.
4. System Settings -> Other Settings -> Language -> Українська (пункт, де було "{original}").
5. Перезавантажте консоль.

ВИДАЛЕННЯ
Видаліть папки мода з luma/titles/ на SD-карті,
або переключіть мову консолі на будь-яку іншу.

Повна інструкція: https://github.com/BolgarMaxym97/3ds-ua
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("version", nargs="?", default="dev")
    variant.add_argument(ap)
    args = ap.parse_args()

    slot = variant.select(args.slot)
    version = args.version
    dist = slot.dist
    if not dist.is_dir():
        raise SystemExit(f"no {dist.name}/ directory - run `make build` first")

    archive = ROOT / f"3ds-ua-from-{slot.key}-{version}.zip"
    # Finder litters the build with .DS_Store; those must not reach the SD card.
    files = sorted(
        p for p in dist.rglob("*") if p.is_file() and not any(part.startswith(".") for part in p.parts)
    )
    if not files:
        raise SystemExit(f"{dist.name}/ is empty")

    readme = README_TXT.format(version=version, slot=slot.key, original=slot.original, **SLOT_WORDS[slot.key])
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            zf.write(path, path.relative_to(dist))
        zf.writestr("README.txt", readme)

    total = sum(p.stat().st_size for p in files)
    print(f"{archive.name}: {len(files)} files, {total} bytes -> {archive.stat().st_size} bytes")
    for path in files:
        print(f"  {path.relative_to(dist)}")


if __name__ == "__main__":
    main()
