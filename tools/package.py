"""Pack the build into a release archive.

Usage:
    python3 tools/package.py 0.1.0
    python3 tools/package.py 0.1.0 --slot en

Output: 3ds-ua-from-<slot>-<version>-<model>.zip, laid out the way the user extracts it to
the SD card root:
    luma/titles/<TID>/romfs/...
    README.txt

One archive per language slot the mod can stand in - `from-ru` out of dist/, `from-en` out
of dist_en/, see tools/variant.py. The two hold the same translation and differ only in
which language of the console it replaces, so README.txt says which one this is.

And one archive per console model, because a New 3DS runs its own copies of the Internet
Browser and of Health and Safety while Luma keeps reading the *Old 3DS* title's folder for
them - so `/luma/titles/0004001000022300/code.ips` has to be one binary's patch on one
console and the other binary's on the other, and no single card can hold both. The New 3DS
archive is the shared tree with <dist>/new3ds/ laid over it; the Old 3DS one is the shared
tree alone. See write_loader_alias() in tools/build.py for how that folder is built and for
the evidence it rests on.

README.txt inside the archive stays in Ukrainian: it is read by end users, not developers.
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import luma_hook  # noqa: E402
import variant  # noqa: E402
from manual import MANUAL_APPLET_TID  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

# The one thing the two builds say differently: which language the mod stands in place of,
# and therefore which one the console keeps.
SLOT_WORDS = {
    "ru": {"replaced": "російський", "kept": "Англійська", "left_pl": "російськими", "left_ms": "російським"},
    "en": {"replaced": "англійський", "kept": "Російська", "left_pl": "англійськими", "left_ms": "англійським"},
}

# The second axis of the release: which console the archive is for. The text differs, and so
# do two folders - see the module docstring and write_loader_alias() in tools/build.py.
MODELS = {
    "old3ds": {
        "name": "Old 3DS",
        "note": """ЦЕЙ АРХІВ — ДЛЯ 3DS, 3DS XL І 2DS (БЕЗ "NEW")
Для New 3DS, New 3DS XL і New 2DS XL є окремий архів
  3ds-ua-from-{slot}-{version}-new3ds.zip
New 3DS має власні копії Інтернет-браузера і Здоров'я і безпеки, а Luma шукає файли
для них у папці Old3DS-івського титулу — тобто в тих самих luma/titles/0004003000009D02
і luma/titles/0004001000022300, що й на цій консолі. Той самий файл мусить бути різним
на різних консолях, тому архіви два. На New 3DS цей архів дасть креш Здоров'я і безпеки
("An exception occurred") і наполовину {left_ms} браузер.""",
    },
    "new3ds": {
        "name": "New 3DS",
        "note": """ЦЕЙ АРХІВ — ДЛЯ NEW 3DS, NEW 3DS XL І NEW 2DS XL
Для звичайних 3DS, 3DS XL і 2DS є окремий архів
  3ds-ua-from-{slot}-{version}-old3ds.zip
New 3DS має власні копії Інтернет-браузера і Здоров'я і безпеки, а Luma шукає файли для
них у папці Old3DS-івського титулу. Тому тут luma/titles/0004003000009D02 і
luma/titles/0004001000022300 везуть New3DS-івські файли, а не Old3DS-івські. На звичайній
3DS цей архів ставити не можна: Здоров'я і безпека там не запуститься.
Якщо Здоров'я і безпека не запускається і на New 3DS — у вас інша версія титулу.
Видаліть тоді ОБИДВІ папки цілком:
  luma/titles/0004001000022300
  luma/titles/0004001020022300""",
    },
}

README_TXT = """3DS UA — український інтерфейс для Nintendo 3DS (версія {version}, збірка from-{slot}, {model_name})

Мод підміняє {replaced} мовний слот українською. {kept} лишається недоторканою.
Потрібна EUR-консоль з Luma3DS.

{model_note}

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
усі 67 країн і всі 724 їхні області, і назва панелі в Обміні частинками.
На New 3DS перекладено її власні версії Інтернет-браузера і Здоров'я і безпеки:
інтерфейс браузера, його вбудовану клавіатуру, його окремий довідник і сам
документ Здоров'я і безпеки — той, який показує New 3DS, а не Old 3DS.

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
ВЕРСІЇ 7, Здоров'я і безпеку New 3DS ВЕРСІЇ 0, аплет покупок eShop ВЕРСІЇ 22, 3DS Memo ВЕРСІЇ 3,
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
  Здоров'я і безпека (New 3DS)  luma/titles/0004001020022300
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
{manual_files}
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
не стосується. Це стосується правки картки руками — скрипти Universal-Updater
видаляють папки цілком самі.

ВСТАНОВЛЕННЯ
Найпростіше — через Universal-Updater, просто на консолі й без виймання картки.
Додайте там магазин
  {store_url}
і виберіть "Українізатор 3DS/2DS". Нижче — те саме вручну.

1. Розпакуйте вміст цього архіву в корінь SD-карти (папка luma має злитися з наявною).
2. Вставте SD у консоль. Тримайте SELECT і увімкніть консоль.
3. Увімкніть "Enable game patching" (кнопка A), натисніть START — зберегти й перезавантажити.
4. System Settings -> Other Settings -> Language -> Українська (пункт, де було "{original}").
5. Перезавантажте консоль.

ВИДАЛЕННЯ
Видаліть папки мода з luma/titles/ на SD-карті,
або переключіть мову консолі на будь-яку іншу,
або в Universal-Updater: "Українізатор 3DS/2DS" -> "2. Видалити українізатор".

Повна інструкція: https://github.com/BolgarMaxym97/3ds-ua
"""


def manual_files() -> str:
    """The manual list for README.txt, straight out of the patch it describes.

    Names come from luma_hook.manual_file_name(), so a title added to the viewer's table - or
    renamed there, as the New 3DS copies are - cannot drift out of the text. Labels come from
    src/app_names.json where the title has one; the few manuals whose title name the mod does
    not patch are named here instead.
    """
    names = json.loads((ROOT / "src" / "app_names.json").read_text(encoding="utf-8"))
    extra = {
        "0004001000022900": "Nintendo eShop",
        "0004001000022D00": "Face Raiders",
    }
    lines = []
    for tid in luma_hook.HOOK_PATCHES[MANUAL_APPLET_TID]["manual_path"]["titles"]:
        label = names.get(tid.upper(), {}).get("ua") or extra.get(tid.upper(), tid)
        if int(tid, 16) >> 28 & 0xF == 2:   # a New 3DS copy of a title the Old 3DS has too
            label += " (New 3DS)"
        lines.append(f"  luma/titles/{MANUAL_APPLET_TID}/romfs/{luma_hook.manual_file_name(tid):<6}      {label}")
    return "\n".join(lines)


# Where the UniStore that installs all this from the console itself is served from. It lives
# here rather than in tools/unistore.py because that module imports this one for
# archive_name(), and importing back would be a cycle.
STORE_URL = "https://raw.githubusercontent.com/BolgarMaxym97/3ds-ua/main/unistore/3ds-ua.unistore"


def archive_name(slot_key: str, version: str, model: str) -> str:
    """The release asset name, in one place.

    tools/unistore.py builds the store's download patterns out of this, so the name the
    console asks GitHub for cannot drift from the name this script writes.
    """
    return f"3ds-ua-from-{slot_key}-{version}-{model}.zip"


def collect(root: Path) -> dict[str, Path]:
    """The files under `root`, keyed by where they land on the SD card.

    The New 3DS subtree is skipped: it is not part of the card layout, it is the overlay the
    New 3DS archive is built with. Finder litters the build with .DS_Store, and those must
    not reach the card either.
    """
    files = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or any(part.startswith(".") for part in path.parts):
            continue
        rel = path.relative_to(root)
        if rel.parts[0] == variant.NEW3DS_DIR:
            continue
        files[rel.as_posix()] = path
    return files


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

    shared = collect(dist)
    if not shared:
        raise SystemExit(f"{dist.name}/ is empty")
    overlay = collect(dist / variant.NEW3DS_DIR)
    if not overlay:
        raise SystemExit(
            f"no {dist.name}/{variant.NEW3DS_DIR}/ - that is where the New 3DS copies of the "
            f"browser and of Health and Safety are built, and without them the New 3DS "
            f"archive would be the Old 3DS one under another name"
        )

    for model, words in MODELS.items():
        # The overlay wins where the two disagree: those paths are exactly the ones that
        # have to hold a different file on a New 3DS.
        files = shared | overlay if model == "new3ds" else shared
        archive = ROOT / archive_name(slot.key, version, model)
        readme = README_TXT.format(
            store_url=STORE_URL,
            version=version,
            slot=slot.key,
            original=slot.original,
            manual_files=manual_files(),
            model_name=words["name"],
            model_note=words["note"].format(
                slot=slot.key, version=version, **SLOT_WORDS[slot.key]
            ),
            **SLOT_WORDS[slot.key],
        )
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
            for rel, path in files.items():
                zf.write(path, rel)
            zf.writestr("README.txt", readme)

        total = sum(path.stat().st_size for path in files.values())
        print(f"{archive.name}: {len(files)} files, {total} bytes -> {archive.stat().st_size} bytes")
        for rel, path in files.items():
            from_overlay = " <- new3ds/" if model == "new3ds" and rel in overlay else ""
            print(f"  {rel}{from_overlay}")


if __name__ == "__main__":
    main()
