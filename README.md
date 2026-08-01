# 3DS UA 🇺🇦

Український інтерфейс для Nintendo 3DS (work in progress). Ставиться як мод на SD-карту через LayeredFS (Luma3DS) — **системні файли в NAND не змінюються**.

Ukrainian system UI for Nintendo 3DS. Installs as an SD-card mod via Luma3DS LayeredFS — **nothing in NAND is modified**.

[Українською](#українською) · [In English](#in-english)

---

## Українською

Мод підміняє **російський** мовний слот українською: російська зникає з консолі, на її місці стає українська. **Англійська лишається недоторканою.**

### Що потрібно

- Nintendo 3DS / 2DS / New 3DS з **Luma3DS** (CFW) і boot9strap
- SD-карта
- регіон консолі: EUR (для USA/JPN дивись [Інші регіони](#інші-регіони))

Немає Luma3DS? Спершу пройди [3ds.hacks.guide](https://3ds.hacks.guide/) — цей мод без CFW не працює.

### Встановлення

**1. Завантажити архів**

Візьми `3ds-ua-<версія>.zip` з [Releases](../../releases).

**2. Розпакувати в корінь SD-карти**

Вставте SD-карту в комп'ютер і розпакуйте архів так, щоб папка `luma` **злилася** з наявною (не заміняйте її!). Має вийти:

```
SD:/luma/titles/0004003000009802/romfs/message/EU_Russian/menu_msbt_LZ.bin
SD:/luma/titles/0004001000022000/romfs/message_EU_LZ.bin
…і ще кілька титулів
```

**3. Увімкнути LayeredFS у Luma3DS**

- вставте SD у консоль, консоль **вимкнена**;
- натисніть і **тримайте SELECT**, потім увімкніть консоль;
- у синьому меню знайдіть `Enable game patching` (7-й пункт), натисніть **A** — має стати `(x)`;
- натисніть **START** — зберегти й перезавантажити.

**4. Вибрати українську мову**

`System Settings` → `Other Settings` → `Language` → **Українська** → `OK`.

Це той пункт, де раніше було `Русский`. Він підписаний як `Українська` в списку незалежно від поточної мови консолі, тож його видно й тоді, коли інтерфейс поки що англійський чи німецький.

**5. Перезавантажити консоль**

Готово.

### Що за папки в `luma/titles/`

Ім'я папки — це Title ID (TID) системного титулу, який вона підміняє. Luma читає її лише тоді, коли запускається саме цей титул, тож зайвих папок у моді немає.

| Папка (TID) | Титул | Що всередині |
|---|---|---|
| `0004003000009802` | Меню HOME | `romfs/` — LayeredFS |
| `0004001000022000` | Налаштування системи | `romfs/` — LayeredFS |
| `0004001000022700` | Mii Maker | `romfs/` — LayeredFS |
| `0004001000022400` | Nintendo 3DS Камера | `romfs/` — LayeredFS |
| `0004001000022500` | Nintendo 3DS Звук | `romfs/` — LayeredFS |
| `0004001000022200` | Журнал дій | `romfs/` + `code.ips` + `exheader.bin` — LayeredFS з правкою коду |
| `0004003000009B02` | Посібник | `romfs/` + `code.ips` + `exheader.bin` — LayeredFS з правкою коду |
| `0004003000009F02` | Список друзів | `romfs/` + `code.ips` + `exheader.bin` — LayeredFS з правкою коду |
| `0004001000022800` | Площа StreetPass Mii | `romfs/` + `exheader.bin` — LayeredFS з правкою прав |
| `000400300000D102` | Вибір Mii | `romfs/` + `code.ips` + `exheader.bin` — LayeredFS з правкою коду |
| `000400300000A002` | Повідомлення | `romfs/` + `code.ips` + `exheader.bin` — LayeredFS з правкою коду |
| `000400300000B902` | Налаштування amiibo | `romfs/` + `code.ips` + `exheader.bin` — LayeredFS з правкою коду |
| `0004003000009C02` | Ігрові записи | `romfs/` — LayeredFS |
| `0004003000009D02` | Інтернет-браузер | `romfs/` — LayeredFS |
| `0004001000022900` | Nintendo eShop | `romfs/` — LayeredFS |
| `0004001000022A00` | Перенесення даних | `romfs/` — LayeredFS |
| `0004001000022B00` | Nintendo Zone | `romfs/` — LayeredFS |
| `0004001000022D00` | Face Raiders | `romfs/` — LayeredFS |
| `0004001000022E00` | AR Games | `romfs/` — LayeredFS |
| `0004001000022100` | Гра по завантаженню | `code.ips` + `exheader.bin` + `dlplay_romfs.bin` — без LayeredFS, повний образ romfs з SD |
| `0004001000022300` | Здоров'я і безпека | `code.ips` + `exheader.bin` + `safe_romfs.bin` — без LayeredFS, повний образ romfs з SD |
| `000400300000D002` | Екранна клавіатура | `code.ips` + `exheader.bin` + `swkbd_romfs.bin` — без LayeredFS, повний образ romfs з SD |
| `000400300000C502` | Екран помилки | `code.ips` + `exheader.bin` + `error_romfs.bin` — без LayeredFS, повний образ romfs з SD |

Чому в останніх десяти є `exheader.bin`, а в більшості з них ще й `code.ips`, — див. [Що входить у реліз](#що-входить-у-реліз). Коротко: перші тринадцять титулів Luma хукає сама, решті бракує прав або коду, які додає збірка.

Папки `romfs` немає навмисно у Гри по завантаженню, клавіатури, Здоров'я і безпеки й екрана помилки: сама її наявність зупиняє ці титули на екрані помилки.

TID регіонозалежні. У релізі — **EUR**; для інших регіонів у тих самих папок інші імена:

| Титул | EUR | USA | JPN |
|---|---|---|---|
| Меню HOME | `0004003000009802` | `0004003000008F02` | `0004003000008202` |
| Список друзів | `0004003000009F02` | `0004003000009602` | `0004003000008D02` |

### Видалення

Будь-який зі способів:

1. **Видалити папки мода.** SD-карту в комп'ютер, видалити відповідні папки з `SD:/luma/titles/`.
2. **Змінити мову консолі** на будь-яку іншу — переклад просто не застосується, повернеться штатна мова.
3. **Вимкнути LayeredFS.** SELECT при вмиканні → зняти `Enable game patching` → START. Але це також вимкне всі інші моди.

NAND не змінювався, тому видалення нічого не ламає.

### Якщо не працює

| Симптом | Причина й що робити |
|---|---|
| Інтерфейс російською | Не увімкнено `Enable game patching`. Конфіг Luma **скидається після оновлення Luma** — поставте галочку знову. |
| Російською, галочка стоїть | Перевірте шлях: має бути `luma/titles/...`, а не `luma/luma/titles/...`. Регістр TID не важливий. |
| У списку мов немає `Українська` | Не скопійовано файл Налаштувань системи (`0004001000022000`) або мод стоїть не на EUR-консоль. |
| Частина тексту не українською | Це нормально: технічні рядки (`OK`, `Miiverse`, формати дат) залишені як є. |
| На клавіатурі `i` замість `і`, `ε` замість `є` | Так і має бути — та сама заміна, що й у решті інтерфейсу: цих літер у системному шрифті немає. Клавіші стоять на українських позиціях (`ы`→`і`, `ъ`→`ї`, `э`→`є`), а на місці `ё` тепер апостроф. |
| `An exception occurred`, `Current process: loader` | Luma не змогла застосувати LayeredFS до титулу, який ви запускали, і зупинила консоль. Перейменуйте `SD:/luma/titles/<TID>/romfs` цього титулу на `_romfs` і перезавантажте — титул запуститься без перекладу. Напишіть в Issues з фото екрана помилки. |
| HOME Menu не запускається | Видаліть `SD:/luma/titles/0004003000009802`. Напишіть в Issues, вказавши модель, регіон і версію системи. |
| Титул крешить після встановлення | Переклади Журналу дій, Посібника, Списку друзів, Вибору Mii, Повідомлень, налаштувань amiibo, Гри по завантаженню, клавіатури, Здоров'я і безпеки й екрана помилки містять правку коду титулу — під версії **2**, **5**, **6**, **3**, **4**, **1**, **3**, **4**, **3** і **7** відповідно (EUR). Ці білди стоять на всіх сучасних прошивках. Якщо у вас старіший, видаліть папку того титулу: `0004001000022200`, `0004003000009B02`, `0004003000009F02`, `000400300000D102`, `000400300000A002`, `000400300000B902`, `0004001000022100`, `000400300000D002`, `0004001000022300`, `000400300000C502`. Решта перекладу працюватиме як була. |
| Гра по завантаженню, клавіатура, Здоров'я і безпека або екран помилки не завантажується | Видаліть `SD:/luma/titles/0004001000022100`, `SD:/luma/titles/000400300000D002`, `SD:/luma/titles/0004001000022300` чи `SD:/luma/titles/000400300000C502` **цілком**. Вони читають свій romfs з SD-карти, тому `code.ips` без відповідного `*_romfs.bin` їх ламає — видаляти частинами не можна. |
| Порожні квадрати замість літер | Повідомте в Issues із фото — це баг, такого бути не повинно. |

### Чому `i` замість `і`

Системний шрифт 3DS має лише 66 кириличних символів (російський набір). Українських `і ї є ґ І Ї Є Ґ` у ньому **немає** — замінити шрифт можна тільки правкою NAND, а це суперечить ідеї «мод без змін системи».

Тому мод підставляє візуально близькі символи, які у шрифті є:

| Треба | Показується |
|---|---|
| `і` `І` | `i` `I` (латиниця) |
| `ї` `Ї` | `ï` `Ï` |
| `є` `Є` | `ε` `Ε` (грецька) |
| `ґ` `Ґ` | `г` `Г` |

Заміну робить збірка автоматично — у файлах перекладу текст записаний нормальною українською.

### Українська розкладка клавіатури

Системна клавіатура тепер українська, а не російська. Це вийшло зробити тому, що розкладка лежить не в коді й не в текстурах, а в тому самому MSBT, який мод і так підміняє (`qwerty_keytop_ru`, `euro_keytop_05`, `cell_*_cyrillic`).

Російський набір має рівно чотири літери, яких немає в українській — `ё ъ ы э`. У справжній українській розкладці ЙЦУКЕН на цих самих клавішах стоять `ґ ї і є`, тож заміна не довільна: кожна літера там, де її очікує той, хто друкує українською.

| Було | Стало | Показується |
|---|---|---|
| `ы` | `і` | `i` |
| `ъ` | `ї` | `ï` |
| `э` | `є` | `ε` |
| `ё` | `'` | `'` |

Окремої клавіші `ґ` немає навмисно: у моді вона й так показується як `г`, тож така клавіша видавала б символ, невідрізнимий від `г`. Апостроф корисніший — в українській він потрібен постійно (`об'єкт`, `п'ять`), а на цій розкладці його не було зовсім.

У списку мов словника пункт `Русский` підписаний як `українс.` — це той самий пункт, що вмикає кириличну клавіатуру.

### Що входить у реліз

| Титул | Стан |
|---|---|
| Меню HOME | ✅ перекладено |
| Налаштування системи | ✅ перекладено |
| Mii Maker | ✅ перекладено |
| Nintendo 3DS Камера | ✅ перекладено |
| Nintendo 3DS Звук | ✅ перекладено |
| Площа StreetPass Mii | ✅ перекладено, з правкою прав титулу |
| Ігрові записи | ✅ перекладено |
| Інтернет-браузер | ✅ перекладено |
| Nintendo eShop | ✅ перекладено |
| Перенесення даних | ✅ перекладено |
| Nintendo Zone | ✅ перекладено |
| Face Raiders | ✅ перекладено |
| AR Games | ✅ перекладено |
| Здоров'я і безпека | ✅ перекладено, повною підміною romfs — потрібна версія титулу 3 (див. нижче) |
| Журнал дій | ✅ перекладено, з правкою коду титулу — потрібна версія титулу 2 (див. нижче) |
| Посібник | ✅ перекладено, з правкою коду титулу — потрібна версія титулу 5 (див. нижче) |
| Список друзів | ✅ перекладено, з правкою коду титулу — потрібна версія титулу 6 (див. нижче) |
| Вибір Mii | ✅ перекладено, з правкою коду титулу — потрібна версія титулу 3 (див. нижче) |
| Повідомлення | ✅ перекладено, з правкою коду титулу — потрібна версія титулу 4 (див. нижче) |
| Налаштування amiibo | ✅ перекладено, з правкою коду титулу — потрібна версія титулу 1 (див. нижче) |
| Екран помилки | ✅ перекладено, повною підміною romfs — потрібна версія титулу 7 (див. нижче) |
| Гра по завантаженню | ✅ перекладено, повною підміною romfs — потрібна версія титулу 3 (див. нижче) |
| Екранна клавіатура | ✅ перекладено, повною підміною romfs — потрібна версія титулу 4 (див. нижче) |

Два останні титули потрапили в реліз не через LayeredFS — Luma не вміє під'єднати його до них. Її завантажувач закінчує патч так:

```c
if(isApp || isApplet) { ... if(!patchLayeredFs(...)) goto error; }
error:
    svcBreak(USERBREAK_ASSERT);
```

Перевірка запускається лише тоді, коли папка `luma/titles/<TID>/romfs` існує. Тобто сама **наявність папки** для титулу, у коді якого Luma не знаходить потрібних функцій FS або місця під redirect-payload, перетворює кожен його запуск на екран помилки — вміст файлів при цьому не читається взагалі.

Тому «перекласти частково, щоб не падало» неможливо: справа не в тексті, а в самому титулі.

#### Чому саме ці титули

Luma шукає в коді титулу п'ять функцій FS. Чотири з них є всюди; бракує щоразу однієї — **`fsMountArchive`**, тієї, що монтує архів за його ID. Без неї Luma не має чим підключити папку на SD як архів `lf:`.

Річ не в тому, що функція скомпільована незвично і сигнатура не збіглася. Її **немає взагалі**: в екранній клавіатурі і в грі по завантаженню в усьому коді нема жодного IPC-виклику `FSUSER_OpenArchive`, а в Журналі дій, Посібнику, Списку друзів і Виборі Mii єдиний такий виклик захований усередині монтування extdata чи системного сейву з бінарним шляхом.

Корінь — в `exheader`, поле `accessInfo` (зсув 0x248):

| Титул | `accessInfo` | `DirectSdmc` |
|---|---|---|
| Меню HOME | `0x0200000000310080` | є |
| Mii Maker | `0x0000000000000081` | є |
| Ігрові записи | `0x0000000000000081` | є |
| Інтернет-браузер | `0x0000000000000081` | є |
| Nintendo Zone | `0x0000000000000081` | є |
| Face Raiders | `0x0000000000000081` | є |
| AR Games | `0x0000000000000081` | є |
| Перенесення даних | `0x00000000000020a1` | є |
| Nintendo eShop | `0x0000000000240001` | **нема**, але `fsMountArchive` є |
| Nintendo 3DS Камера | `0x00000000000000a1` | є |
| Nintendo 3DS Звук | `0x00000000000000a1` | є |
| Площа StreetPass Mii | `0x0000000000000000` | **нема** |
| Екранна клавіатура | `0x0000000000000001` | **нема** |
| Журнал дій | `0x0000000000000001` | **нема** |
| Гра по завантаженню | `0x0000000000000001` | **нема** |
| Посібник | `0x0000000000000001` | **нема** |
| Список друзів | `0x0000000000000001` | **нема** |
| Вибір Mii | `0x0000000000000001` | **нема** |
| Повідомлення | `0x0000000000000001` | **нема** |
| Налаштування amiibo | `0x0000000000000001` | **нема** |
| Екран помилки | `0x0000000000000001` | **нема** |
| Здоров'я і безпека | `0x0000000000000001` | **нема** |

Титули без права `DirectSdmc` не мають доступу до SD-карти, тому Nintendo просто не залінкувала в них код монтування SD. Працюють ті титули, у яких це право є.

Площа StreetPass Mii — виняток з обох боків: права `DirectSdmc` в неї немає, але `fsMountArchive` є, бо вона монтує власні extdata. Luma знаходить усі п'ять функцій і патчить титул сама, тож `code.ips` не потрібен — але payload, який вона вписує, все одно читає файли з SD. Тому в цієї папки є `exheader.bin` з піднятим бітом `DirectSdmc` і більше нічого: жодних зсувів, отже нічого, що прив'язане до конкретного білда, крім звірки версії титулу.

Наскільки глибоко зайшла та економія, видно з набору IPC-команд, які титул узагалі вміє видавати:

| Титул | `OpenArchive` | `OpenFile` | `CloseArchive` | `OpenFileDirectly` |
|---|---|---|---|---|
| Журнал дій, Посібник, Список друзів, Вибір Mii, Повідомлення, Налаштування amiibo | ✅ | ✅ | ✅ | ✅ |
| Гра по завантаженню, клавіатура, Здоров'я і безпека | ❌ | ❌ | ❌ | ✅ |
| Екран помилки | ✅ | ❌ | ❌ | ✅ |

Двом останнім доступне рівно одне: відкрити файл напряму і читати його. Тому для них потрібен інший підхід.

#### Як полагоджено Журнал дій, Посібник, Список друзів, Вибір Mii, Повідомлення й налаштування amiibo

Обидві частини можна дати з SD-карти, бо завантажувач Luma виконує їх у такому порядку:

```c
applyCodeIpsPatch(progId, code, size);   // /luma/titles/<TID>/code.ips
...
patchLayeredFs(...);                     // тут шукаються ті п'ять функцій
```

а `exheader` підміняється ще раніше, до створення процесу. Тому в архіві поряд з `romfs` для Журналу лежать ще два файли:

| Файл | Що робить |
|---|---|
| `exheader.bin` | оригінальний exheader з піднятим бітом `DirectSdmc` |
| `code.ips` | 84–96 байт: дописує `fsMountArchive`, якої в титулі не було |

Сигнатурні слова, за якими Luma знаходить стаб, лежать за безумовним переходом і ніколи не виконуються; робоча частина складає виклик `FSUSER_OpenArchive` і стрибає в хвіст рідного монтування титулу, який виділяє об'єкт архіву з правильним vtable.

Місце під стаб у кожного титулу своє:

| Титул | Куди лягає стаб |
|---|---|
| Журнал дій | поверх `throwFatalError()` — тієї функції, яку Luma сама затирає, коли їй бракує місця під власний payload. Тут місця вистачає, тож Luma її не чіпає. |
| Посібник | у 88 байт padding'а в кінці `.text`. Тут `throwFatalError()` зайнята: padding менший за payload Luma (0x114), тож Luma забирає її собі. |
| Список друзів | поверх `throwFatalError()`, як у Журналу: padding `.text` тут 2724 байти, Luma кладе payload туди й `throwFatalError()` не чіпає. |
| Вибір Mii | поверх `throwFatalError()`: padding `.text` тут 3048 байт, Luma знову бере padding. |
| Повідомлення | поверх `throwFatalError()`: padding `.text` 2300 байт, Luma знову бере padding. |
| Налаштування amiibo | поверх `throwFatalError()`: padding `.text` 968 байт, Luma знову бере padding. |

Стаб буває у трьох варіантах — за тим, який регістр і який кадр стека чекає хвіст монтування, у який він стрибає: `r4`/кадр `0x28` (Журнал дій), `sl`/кадр `0x14` з результатом у `r8` (Посібник, Список друзів) або `r4`/кадр `0x18` (Вибір Mii, Повідомлення, налаштування amiibo). У цих трьох функція монтування одна-єдина, і стаб стрибає не в неї саму, а на перевірку результату за `0xD36C` — тому невдалий `OpenArchive` повертає помилку, а не об'єкт архіву з мотлохом замість handle. У Списку друзів усі три його функції монтування будують той самий об'єкт архіву (vtable `0x201E4C`), тож хвіст будь-якої з них підійшов би — узято `MountSystemSaveData()`.

У Посібника є додаткова тонкість. `findLayeredFsSymbols()` сканує лише до `text.size`, а це 0xADFA8 — padding лишається за межею. Тому в його `exheader.bin` `text.size` округлено до 0xAE000. Це безкоштовно: завантажувач усюди рахує сторінки як `(size + 4095) >> 12`, і 0xADFA8, і 0xAE000 дають ті самі 174 сторінки — адреси секцій, розкладка `.code` і мапінг лишаються байт-у-байт тими самими.

⚠️ **Зсуви прив'язані до білда титулу, не до версії системи.** Ідентифікує білд поле `remaster_version` в exheader — скільки разів Nintendo взагалі оновлювала цей титул:

| Титул | `remaster_version` |
|---|---|
| Меню HOME (`menu`) | 29 |
| **Список друзів (`friend`)** | **6** |
| **Посібник (`ebird`)** | **5** |
| **Клавіатура (`swkbd`)** | **4** |
| **Гра по завантаженню (`dlplay`)** | **3** |
| **Вибір Mii (`appletEd`)** | **3** |
| **Екран помилки (`error`)** | **7** |
| **Повідомлення (`newslist`)** | **4** |
| **Налаштування amiibo (`Cabinet`)** | **1** |
| **Площа StreetPass Mii (`MEET`)** | **5** |
| **Здоров'я і безпека (`safe`)** | **3** |
| Mii Maker (`EDIT`) | 2 |
| **Журнал дій (`PLOG`)** | **2** |

Ці титули оновлювали одиниці разів за весь час життя консолі, тож їхні білди стоять на всіх сучасних прошивках, включно з останньою `11.17.0-50` (травень 2023, останнє оновлення 3DS взагалі — жодного з них у ньому не чіпали). Практично це означає, що патч підходить майже всім.

Збірка звіряє `remaster_version` і sha256 дампа й падає, якщо білд інший. Кінцевого користувача це не захищає, тому в архіві є попередження: якщо титул крешить — білд старіший, треба видалити його папку з `luma/titles/`.

#### Як полагоджено Гру по завантаженню

Тут стаб нема чому передавати аргументи: обгортки `FSUSER_OpenArchive` в титулі не існує, і класу архіву на handle теж — єдиний його клас архіву це romfs поверх файлу. Тож замість того щоб додавати монтування, підмінюється те, що титул відкриває.

Гра по завантаженню читає власний romfs через `OpenFileDirectly` з `archiveId = 3` (`ARCHIVE_ROMFS`). `code.ips` міняє це на `archiveId = 9` (SDMC) з ASCII-шляхом до образу на SD:

| Файл | Що робить |
|---|---|
| `exheader.bin` | `DirectSdmc` |
| `code.ips` | 160 байт: два стаби в padding'у `.text` і рядок шляху в padding'у `.rodata` |
| `dlplay_romfs.bin` | увесь romfs титулу, зібраний наново з підміненими файлами перекладу |

Таких місць у титулі два: `0x14D3C` (з нього будується зареєстрований архів `rom:`) і `0xDD24` (окремий читач тих самих даних). Перенаправлені обидва — якби лишити одне, два читачі працювали б з двома різними образами одного romfs, у яких внутрішні зсуви не збігаються.

LayeredFS тут не задіяний узагалі: теки `romfs` для цього титулу немає, тому `checkLumaDir` нічого не знаходить, `patchLayeredFs` виходить одразу і той `svcBreak` недосяжний.

⚠️ **У цього титулу немає м'якої деградації.** У решти будь-яка проблема з файлами означає лише «працює без перекладу», бо оригінал лишається в NAND. Тут `code.ips` назавжди відправляє титул на SD: якщо видалити `dlplay_romfs.bin`, а `code.ips` лишити, Гра по завантаженню не прочитає свої ресурси. Видаляти треба папку цілком.

Образ збирається з повного оригінального дерева — підмінюються тільки файли російського слота, решта мов лишається на місці. Тому спосіб видалення «переключити мову консолі» працює і для нього.

Здоров'я і безпека — той самий випадок: у всьому її коді єдиний виклик fs:USER це `OpenFileDirectly` (обгортка за `0x21A18`), а обидва її romfs-сайти (`0xA800` — з нього будується `rom:`, і `0x11234`) перенаправлені на `safe_romfs.bin`. Стаби лягають у 1388 байт padding'а `.text` за `0x63A94`.

Екран помилки — інший випадок: `FSUSER_OpenArchive` у нього є, але об'єкта архіву немає ніде. Його монтування — це цикл повторів, який віддає сирий handle у `fsRegisterArchive`, тож стабу нема в чий хвіст стрибати. Тому він теж іде повним образом romfs: обидва його romfs-сайти (`0xBEA8` — з нього будується `rom:`, і `0x11298`) перенаправлені на `error_romfs.bin`, стаби лягають у 1140 байт padding'а `.text` за `0x55B8C`.

Екранна клавіатура влаштована так само й полагоджена тим самим способом: два її romfs-сайти (`0x14944` — з нього будується `rom:`, і `0xE958`) перенаправлені на `swkbd_romfs.bin`. Третій виклик `OpenFileDirectly` за адресою `0x6F7C0` не чіпається — він відкриває `ARCHIVE_SAVEDATA_AND_CONTENT`, а не romfs.

### Чого мод не перекладає

**Підписи іконок на головному екрані.** Назва під іконкою й текст на верхньому екрані при наведенні (`Настройки системы`, `Игровые заметки`) — це не картинка, а текст, але живе він у **SMDH** кожного титулу (`CXI ExeFS:/icon`, 16 мовних структур).

LayeredFS до ExeFS не дістає — Luma підміняє лише `romfs/`, `code.bin`, `code.ips`, `exheader.bin` і `locale.txt`. Щоб змінити SMDH, треба перезібрати й перевстановити сам титул, тобто **писати в NAND** — а весь сенс проєкту в тому, що мод ставиться й зноситься копіюванням папки. Тому підписи іконок залишаються мовою слота.

**Системний шрифт.** Див. розділ вище — LayeredFS шрифт не підміняє.

**Справжні українські літери з клавіатури.** Розкладка українська (див. нижче), але клавіші `і ї є` вводять `i ï ε` — ті самі гліфи-замінники, що й у решті мода. На консолі це виглядає правильно й узгоджено, проте назовні — в імені Mii, назві папки, дописі — це латиниця й грецька, а не український текст. Інакше ніяк: справжні літери потребують іншого шрифту, тобто правки NAND.

**Текст усередині електронних посібників.** Перекладено сам застосунок Посібника — `Назад`, `Збільшити`, `Мова`, `Стор.`, `Зміст`, діалог вибору мови. А от документ, який він показує, лишається мовою слота.

Причина в тому, що документ не належить Посібнику. Кожен титул везе власний електронний посібник окремим NCCH — контентом з індексом 1 у складі того ж титулу. Посібник дістає його через `ARCHIVE_SAVEDATA_AND_CONTENT`, тобто читає контент документованого титулу напряму.

LayeredFS туди не веде. Payload Luma перехоплює монтування лише для `ARCHIVE_ROMFS` і переписує лише шляхи від `rom:` або від «оновлювальної» точки монтування — а в коді Посібника з усіх, які Luma знає (`ro2:`, `rom2:`, `rex:`, `patch:`, `ext:`), немає жодної, тільки власний `rom:`. Механізму «підмінити контент 1 титулу» в Luma не існує.

Це ще й не один документ, а по одному на кожен титул: свій у Журналу дій, свій у Налаштувань системи, свій у кожної гри. Щоб їх перекласти, треба перезібрати й перевстановити контент кожного титулу.

Усі чотири обмеження впираються в одне й те саме: вони потребують правки NAND. Логічний «Tier 2» для тих, хто на це свідомо йде, — окремий реліз із бекапом NAND і попередженнями; у цьому релізі його немає.

### Інші регіони

Реліз зібраний під **EUR**-консолі. Російський мовний слот існує **лише в EUR-збірках** системного ПЗ, тож USA/JPN-консолі цим релізом не покриваються — для них потрібна окрема збірка, яка підміняє англійський слот:

| Регіон | HOME Menu Title ID |
|---|---|
| EUR | `0004003000009802` |
| USA | `0004003000008F02` |
| JPN | `0004003000008202` |

Див. [Збірка з джерел](#збірка-з-джерел) або створіть Issue — додамо в реліз.

### Збірка з джерел

У репозиторії немає файлів Nintendo. Щоб зібрати мод, потрібен дамп romfs **своєї** консолі.

```bash
# 1. Дамп HOME Menu через GodMode9:
#    [1:] SYSNAND CTRNAND → title → 00040030 → 00009802 → content
#    → найбільший .app → A → NCCH image options → Mount image to drive
#    → курсор на romfs → Y (копіювати) → [0:] SDCARD/gm9/out → Y (вставити)
#    Скопіювати на комп'ютер у work/0004003000009802/romfs/

# 2. Дамп системного шрифту (потрібен для перевірки символів):
#    title → 0004009b → 00014002 → content → найбільший .app → romfs
#    → work/0004009B00014002/cbf_std.bcfnt.lz

make font       # шрифт → assets/font_charset.txt + font_widths.json
make extract    # romfs → src/strings/*.json (наявні переклади зберігаються)
make validate   # перевірка: символи, ширина, рядки, теги
make build      # → dist/luma/titles/...
make package    # → 3ds-ua-<версія>.zip
make sd SD=/Volumes/<назва_SD>   # скопіювати прямо на SD
```

Інструменти (Python 3.11+, без залежностей):

| Файл | Що робить |
|---|---|
| `tools/lz11.py` | LZ11 розпак/пак |
| `tools/msbt.py` | MSBT (`MsgStdBn`) читання/зборка, round-trip байт-у-байт |
| `tools/font_cmap.py` | BCFNT → перелік символів і ширин гліфів |
| `tools/extract.py` | romfs → JSON для перекладу |
| `tools/validate.py` | перевірка перекладів проти межі UI |
| `tools/build.py` | JSON → MSBT → LZ11 → `dist/` |
| `tools/fit.py` | чи влазить формулювання в бюджет ширини |
| `tools/package.py` | ZIP для релізу |
| `tools/layeredfs_check.py` | чи зможе Luma під'єднати LayeredFS до титулу |
| `tools/luma_hook.py` | `code.ips` + `exheader.bin` для титулів, яких Luma не хукає сама |

### Як допомогти з перекладом

Правте `ua` у `src/strings/home_menu/*.json` (у полі `en` — оригінал).

Перед PR: `make validate`. Валідатор ловить символи поза шрифтом, завеликі рядки, вигадані керуючі теги. Межі ширини й висоти беруться з **усіх 8 офіційних локалізацій** титулу — якщо влазить німецька, влізе й українська.

Підібрати коротший варіант:

```bash
python3 tools/fit.py home_menu lau_dlg_2b_delete "Видалити" "Стерти"
# lau_dlg_2b_delete: budget 104px wide (limit 113px), 1 lines
#   FAIL   118px  'Видалити'  <- too wide
#   OK      86px  'Стерти'
```

### Ліцензія

Код інструментів і текст перекладу — MIT (див. `LICENSE`). Файли Nintendo в репозиторії відсутні; збірка потребує дампу з власної консолі. Проєкт неофіційний, з Nintendo не пов'язаний.

---

## In English

The mod replaces the **Russian** language slot with Ukrainian: Russian disappears from the console and Ukrainian takes its place. **English is left untouched.**

### Requirements

- Nintendo 3DS / 2DS / New 3DS with **Luma3DS** CFW and boot9strap
- an SD card
- EUR console region (see [Other regions](#other-regions) for USA/JPN)

No CFW yet? Follow [3ds.hacks.guide](https://3ds.hacks.guide/) first — this mod does nothing without Luma3DS.

### Installation

**1. Download**

Grab `3ds-ua-<version>.zip` from [Releases](../../releases).

**2. Extract to the SD card root**

Put the SD card in your computer and extract so that the `luma` folder **merges** with the existing one (do not replace it). You should end up with:

```
SD:/luma/titles/0004003000009802/romfs/message/EU_Russian/menu_msbt_LZ.bin
SD:/luma/titles/0004001000022000/romfs/message_EU_LZ.bin
…plus a few more titles
```

**3. Enable LayeredFS in Luma3DS**

- put the SD card back, console **powered off**;
- hold **SELECT** and power the console on;
- in the blue config menu select `Enable game patching` (7th item), press **A** so it shows `(x)`;
- press **START** to save and reboot.

**4. Pick Ukrainian**

`System Settings` → `Other Settings` → `Language` → **Українська** → `OK`.

That is the entry that used to read `Русский`. It is labelled `Українська` in every language, so you can find it while the console still runs in English or German.

**5. Reboot**

Done.

### What each folder under `luma/titles/` is

A folder name is the Title ID (TID) of the system title it overrides. Luma reads it only when that exact title launches, so nothing in the mod is spare.

| Folder (TID) | Title | Contents |
|---|---|---|
| `0004003000009802` | HOME Menu | `romfs/` — LayeredFS |
| `0004001000022000` | System Settings | `romfs/` — LayeredFS |
| `0004001000022700` | Mii Maker | `romfs/` — LayeredFS |
| `0004001000022400` | Nintendo 3DS Camera | `romfs/` — LayeredFS |
| `0004001000022500` | Nintendo 3DS Sound | `romfs/` — LayeredFS |
| `0004001000022200` | Activity Log | `romfs/` + `code.ips` + `exheader.bin` — LayeredFS plus a code patch |
| `0004003000009B02` | Instruction Manual | `romfs/` + `code.ips` + `exheader.bin` — LayeredFS plus a code patch |
| `0004003000009F02` | Friend List | `romfs/` + `code.ips` + `exheader.bin` — LayeredFS plus a code patch |
| `0004001000022800` | StreetPass Mii Plaza | `romfs/` + `exheader.bin` — LayeredFS plus a rights patch |
| `000400300000D102` | Mii Selector | `romfs/` + `code.ips` + `exheader.bin` — LayeredFS plus a code patch |
| `000400300000A002` | Notifications | `romfs/` + `code.ips` + `exheader.bin` — LayeredFS plus a code patch |
| `000400300000B902` | amiibo Settings | `romfs/` + `code.ips` + `exheader.bin` — LayeredFS plus a code patch |
| `0004003000009C02` | Game Notes | `romfs/` — LayeredFS |
| `0004003000009D02` | Internet Browser | `romfs/` — LayeredFS |
| `0004001000022900` | Nintendo eShop | `romfs/` — LayeredFS |
| `0004001000022A00` | System Transfer | `romfs/` — LayeredFS |
| `0004001000022B00` | Nintendo Zone | `romfs/` — LayeredFS |
| `0004001000022D00` | Face Raiders | `romfs/` — LayeredFS |
| `0004001000022E00` | AR Games | `romfs/` — LayeredFS |
| `0004001000022100` | Download Play | `code.ips` + `exheader.bin` + `dlplay_romfs.bin` — no LayeredFS, whole RomFS image off the SD card |
| `0004001000022300` | Health & Safety Information | `code.ips` + `exheader.bin` + `safe_romfs.bin` — no LayeredFS, whole RomFS image off the SD card |
| `000400300000D002` | Software Keyboard | `code.ips` + `exheader.bin` + `swkbd_romfs.bin` — no LayeredFS, whole RomFS image off the SD card |
| `000400300000C502` | Error applet | `code.ips` + `exheader.bin` + `error_romfs.bin` — no LayeredFS, whole RomFS image off the SD card |

Why the last ten carry `exheader.bin`, and most of them `code.ips` too: see [What is in the release](#what-is-in-the-release). In short, Luma hooks the first thirteen by itself; the rest lack the rights or the code the build supplies.

Download Play, the Software Keyboard and Health & Safety Information ship no `romfs` folder on purpose — its mere presence halts those titles on an exception screen.

TIDs are region-specific. The release targets **EUR**; on other regions the same folders have different names:

| Title | EUR | USA | JPN |
|---|---|---|---|
| HOME Menu | `0004003000009802` | `0004003000008F02` | `0004003000008202` |
| Friend List | `0004003000009F02` | `0004003000009602` | `0004003000008D02` |

### Uninstalling

Any of these:

1. **Delete the mod folders** under `SD:/luma/titles/` on the SD card.
2. **Change the console language** to anything else — the mod simply won't apply and the stock language returns.
3. **Turn LayeredFS off:** hold SELECT on boot → uncheck `Enable game patching` → START. Note this disables all other mods too.

NAND was never touched, so removal cannot break anything.

### Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Interface is still Russian | `Enable game patching` is off. Luma's config **resets when you update Luma** — re-enable it. |
| Still Russian, option is on | Check the path: it must be `luma/titles/...`, not `luma/luma/titles/...`. |
| No `Українська` in the language list | The System Settings file (`0004001000022000`) was not copied, or the console is not an EUR one. |
| Some text is not Ukrainian | Expected: technical strings (`OK`, `Miiverse`, date formats) are intentionally left as-is. |
| The keyboard shows `i` for `і`, `ε` for `є` | By design — the same substitution as everywhere else in the mod: those letters are not in the system font. The keys sit in their Ukrainian positions (`ы`→`і`, `ъ`→`ї`, `э`→`є`), and `ё` now carries the apostrophe. |
| `An exception occurred`, `Current process: loader` | Luma could not apply LayeredFS to the title you launched and halted the console. Rename that title's `SD:/luma/titles/<TID>/romfs` to `_romfs` and reboot — the title then starts untranslated. Please open an Issue with a photo of the error screen. |
| HOME Menu won't boot | Delete `SD:/luma/titles/0004003000009802` and open an Issue with your model, region and system version. |
| A title crashes after installing | The Activity Log, Instruction Manual, Friend List, Mii Selector, Notifications, amiibo Settings, Download Play, Software Keyboard, Health & Safety and error applet translations carry a code patch — for versions **2**, **5**, **6**, **3**, **4**, **1**, **3**, **4**, **3** and **7** respectively (EUR). Those builds are on every modern firmware. If yours is older, delete that title's folder: `0004001000022200`, `0004003000009B02`, `0004003000009F02`, `000400300000D102`, `000400300000A002`, `000400300000B902`, `0004001000022100`, `000400300000D002`, `0004001000022300`, `000400300000C502`. The rest of the mod keeps working. |
| Download Play, the Software Keyboard, Health & Safety or the error applet will not load | Delete `SD:/luma/titles/0004001000022100`, `SD:/luma/titles/000400300000D002`, `SD:/luma/titles/0004001000022300` or `SD:/luma/titles/000400300000C502` **as a whole**. They read their RomFS off the SD card, so `code.ips` without the matching `*_romfs.bin` breaks them — they cannot be removed piecemeal. |
| Empty boxes instead of letters | Please report with a photo — that's a bug. |

### Why `i` instead of `і`

The 3DS shared font contains only 66 Cyrillic glyphs (the Russian set). The Ukrainian-specific `і ї є ґ І Ї Є Ґ` are **missing**, and replacing the system font requires modifying NAND — which this project deliberately avoids.

So the build substitutes visually close glyphs that do exist: `і/І → i/I`, `ї/Ї → ï/Ï`, `є/Є → ε/Ε` (Greek), `ґ/Ґ → г/Г`. Translation files store proper Ukrainian; substitution happens at build time.

### The Ukrainian keyboard layout

The system keyboard is now Ukrainian rather than Russian. That turned out to be possible
because the layout lives neither in code nor in textures, but in the very MSBT the mod
already replaces (`qwerty_keytop_ru`, `euro_keytop_05`, `cell_*_cyrillic`).

The Russian set has exactly four letters Ukrainian does not use — `ё ъ ы э`. On a real
Ukrainian ЙЦУКЕН layout those same keys carry `ґ ї і є`, so the swap is not arbitrary:
every letter sits where a Ukrainian typist expects it.

| Was | Now | Shown as |
|---|---|---|
| `ы` | `і` | `i` |
| `ъ` | `ї` | `ï` |
| `э` | `є` | `ε` |
| `ё` | `'` | `'` |

There is deliberately no `ґ` key: in this mod `ґ` renders as `г` anyway, so such a key
would produce something indistinguishable from `г`. The apostrophe is more useful —
Ukrainian needs it constantly (`об'єкт`, `п'ять`) and this layout had none at all.

In the dictionary language list, the `Русский` entry is labelled `українс.` — it is the
same entry that switches the keyboard to Cyrillic.

### What is in the release

| Title | State |
|---|---|
| HOME Menu | ✅ translated |
| System Settings | ✅ translated |
| Mii Maker | ✅ translated |
| Nintendo 3DS Camera | ✅ translated |
| Nintendo 3DS Sound | ✅ translated |
| StreetPass Mii Plaza | ✅ translated, with a rights patch |
| Game Notes | ✅ translated |
| Internet Browser | ✅ translated |
| Nintendo eShop | ✅ translated |
| System Transfer | ✅ translated |
| Nintendo Zone | ✅ translated |
| Face Raiders | ✅ translated |
| AR Games | ✅ translated |
| Health & Safety Information | ✅ translated, by replacing the whole RomFS — needs title version 3 (see below) |
| Activity Log | ✅ translated, with a code patch — needs title version 2 (see below) |
| Instruction Manual | ✅ translated, with a code patch — needs title version 5 (see below) |
| Friend List | ✅ translated, with a code patch — needs title version 6 (see below) |
| Mii Selector | ✅ translated, with a code patch — needs title version 3 (see below) |
| Notifications | ✅ translated, with a code patch — needs title version 4 (see below) |
| amiibo Settings | ✅ translated, with a code patch — needs title version 1 (see below) |
| Error applet | ✅ translated, by replacing its whole RomFS — needs title version 7 (see below) |
| Download Play | ✅ translated, by replacing its whole RomFS — needs title version 3 (see below) |
| Software Keyboard | ✅ translated, by replacing its whole RomFS — needs title version 4 (see below) |

The last two are in the release by a different route than LayeredFS — Luma cannot hook it
into them. Its loader ends the patch with

```c
if(isApp || isApplet) { ... if(!patchLayeredFs(...)) goto error; }
error:
    svcBreak(USERBREAK_ASSERT);
```

and that check only runs when `luma/titles/<TID>/romfs` exists. So the mere presence of the
folder for a title whose code has no hookable FS symbols (or no room for the redirect
payload) turns every launch of that title into an exception screen — the file contents are
never even read.

Shipping "just a few strings" for those titles is therefore not an option: the problem is
the title, not the text.

#### Why these titles

Luma looks for five FS functions. Four are always there; the one that is missing is always
**`fsMountArchive`**, the one that mounts an archive by ID. Without it Luma has no way to
attach the SD folder as the `lf:` archive.

It is not that the function was compiled in an unusual way and the signature missed it. The
function is **not there at all**: the Software Keyboard and Download Play contain no
`FSUSER_OpenArchive` IPC call anywhere in their code, and in the Activity Log, the
Instruction Manual, the Friend List and the Mii Selector the only one is buried inside an
extdata, system-savedata or RomFS mount that takes a binary path.

The root cause is in the exheader, `accessInfo` at offset 0x248:

| Title | `accessInfo` | `DirectSdmc` |
|---|---|---|
| HOME Menu | `0x0200000000310080` | yes |
| Mii Maker | `0x0000000000000081` | yes |
| Game Notes | `0x0000000000000081` | yes |
| Internet Browser | `0x0000000000000081` | yes |
| Nintendo Zone | `0x0000000000000081` | yes |
| Face Raiders | `0x0000000000000081` | yes |
| AR Games | `0x0000000000000081` | yes |
| System Transfer | `0x00000000000020a1` | yes |
| Nintendo eShop | `0x0000000000240001` | **no**, but it has `fsMountArchive` |
| Nintendo 3DS Camera | `0x00000000000000a1` | yes |
| Nintendo 3DS Sound | `0x00000000000000a1` | yes |
| StreetPass Mii Plaza | `0x0000000000000000` | **no** |
| Software Keyboard | `0x0000000000000001` | **no** |
| Activity Log | `0x0000000000000001` | **no** |
| Download Play | `0x0000000000000001` | **no** |
| Instruction Manual | `0x0000000000000001` | **no** |
| Friend List | `0x0000000000000001` | **no** |
| Mii Selector | `0x0000000000000001` | **no** |
| Notifications | `0x0000000000000001` | **no** |
| amiibo Settings | `0x0000000000000001` | **no** |
| Error applet | `0x0000000000000001` | **no** |
| Health & Safety Information | `0x0000000000000001` | **no** |

Titles without `DirectSdmc` have no access to the SD card, so Nintendo never linked any
SD-mounting code into them. The titles that work are the ones that hold that right.

StreetPass Mii Plaza is the exception on both counts: it has no `DirectSdmc` right, yet it
does have `fsMountArchive`, because it mounts its own extdata. Luma finds all five symbols
and patches the title unaided, so no `code.ips` is needed — but the payload it writes still
reads its files off the SD card. So that folder carries an `exheader.bin` with the
`DirectSdmc` bit set and nothing else: no offsets, and therefore nothing tied to a
particular build beyond the title-version check.

How far that pruning went shows in the set of IPC commands each title can even issue:

| Title | `OpenArchive` | `OpenFile` | `CloseArchive` | `OpenFileDirectly` |
|---|---|---|---|---|
| Activity Log, Instruction Manual, Friend List, Mii Selector, Notifications, amiibo Settings | ✅ | ✅ | ✅ | ✅ |
| Download Play, Software Keyboard, Health & Safety | ❌ | ❌ | ❌ | ✅ |
| Error applet | ✅ | ❌ | ❌ | ✅ |

The last two can do exactly one thing: open a file directly and read it. They need a
different approach.

#### How the Activity Log, the Instruction Manual, the Friend List, the Mii Selector, Notifications and amiibo Settings were fixed

Both halves can be supplied from the SD card, because Luma's loader runs them in this order:

```c
applyCodeIpsPatch(progId, code, size);   // /luma/titles/<TID>/code.ips
...
patchLayeredFs(...);                     // where those five functions are searched for
```

and the exheader is replaced even earlier, before the process is created. So the archive
carries two extra files next to those titles' `romfs`:

| File | What it does |
|---|---|
| `exheader.bin` | the original exheader with the `DirectSdmc` bit set |
| `code.ips` | 84–96 bytes: adds the `fsMountArchive` the title never had |

The signature words Luma finds the stub by sit behind an unconditional branch and never
execute; the working part assembles the `FSUSER_OpenArchive` call and jumps into the tail of
the title's own mount routine, which allocates the archive object with the right vtable.

Where the stub goes differs per title:

| Title | Where the stub lands |
|---|---|
| Activity Log | over `throwFatalError()` — the function Luma itself overwrites when it is short of room for its own payload. Here there is room, so Luma leaves it alone. |
| Instruction Manual | in the 88 bytes of padding at the end of `.text`. Here `throwFatalError()` is taken: the padding is smaller than Luma's payload (0x114), so Luma claims the function for itself. |
| Friend List | over `throwFatalError()`, as in the Activity Log: the `.text` padding is 2724 bytes, so Luma puts its payload there and leaves the function alone. |
| Mii Selector | over `throwFatalError()`: the `.text` padding is 3048 bytes, so Luma takes the padding again. |
| Notifications | over `throwFatalError()`: the `.text` padding is 2300 bytes, so Luma takes the padding again. |
| amiibo Settings | over `throwFatalError()`: the `.text` padding is 968 bytes, so Luma takes the padding again. |

The stub comes in three variants, chosen by the register and stack frame the mount tail it
jumps into expects: `r4` on a 0x28 frame (Activity Log), `sl` on a 0x14 frame with the
result in `r8` (Instruction Manual, Friend List), or `r4` on a 0x18 frame (Mii Selector, Notifications, amiibo Settings).
All three of the Friend List's mount functions build the same archive object (vtable
`0x201E4C`), so any of their tails would have done — `MountSystemSaveData()` is the one
used. The Mii Selector, Notifications and amiibo Settings have exactly one mount function each, and the stub
branches not into it but to its result check (`0xD36C`, `0x5A500` and `0x3D344`), so a failed
`OpenArchive` returns an error instead of an archive object wrapped around a garbage handle.

The Instruction Manual needs one more thing. `findLayeredFsSymbols()` only scans up to
`text.size`, which is 0xADFA8 and stops short of the padding, so its shipped `exheader.bin`
rounds `text.size` up to 0xAE000. That is free: the loader derives page counts everywhere as
`(size + 4095) >> 12`, and 0xADFA8 and 0xAE000 both come to 174 pages — section addresses,
the `.code` layout and the mapping stay byte-for-byte what they were.

⚠️ **The offsets are tied to a build of the title, not to a system version.** What
identifies that build is `remaster_version` in the exheader — how many times Nintendo ever
updated the title:

| Title | `remaster_version` |
|---|---|
| HOME Menu (`menu`) | 29 |
| **Friend List (`friend`)** | **6** |
| **Instruction Manual (`ebird`)** | **5** |
| **Software Keyboard (`swkbd`)** | **4** |
| **Download Play (`dlplay`)** | **3** |
| **Health & Safety (`safe`)** | **3** |
| **Mii Selector (`appletEd`)** | **3** |
| **Error applet (`error`)** | **7** |
| **Notifications (`newslist`)** | **4** |
| **amiibo Settings (`Cabinet`)** | **1** |
| **StreetPass Mii Plaza (`MEET`)** | **5** |
| Mii Maker (`EDIT`) | 2 |
| **Activity Log (`PLOG`)** | **2** |

These titles were updated a handful of times in the console's lifetime, so their builds are
what sits on every modern firmware, including the final `11.17.0-50` (May 2023, the last 3DS
update ever — and it touched none of them). In practice the patch fits almost everyone.

The build checks both `remaster_version` and the dump's sha256 and refuses to run on a
mismatch. That does not protect an end user, so the archive carries a note: if one of those
titles crashes, its build is older and its folder under `luma/titles/` should be deleted.

#### How Download Play was fixed

Here a stub would have nothing to hand its arguments to: the title has no
`FSUSER_OpenArchive` wrapper and no handle-backed archive class — its only archive class is
romfs over a file. So instead of adding a mount, what the title opens is swapped out.

Download Play reads its own RomFS through `OpenFileDirectly` with `archiveId = 3`
(`ARCHIVE_ROMFS`). The `code.ips` turns that into `archiveId = 9` (SDMC) with an ASCII path
to an image on the card:

| File | What it does |
|---|---|
| `exheader.bin` | `DirectSdmc` |
| `code.ips` | 160 bytes: two stubs in the `.text` padding and the path string in the `.rodata` padding |
| `dlplay_romfs.bin` | the title's entire RomFS, rebuilt with the translated files swapped in |

There are two such places: `0x14D3C`, which feeds the archive registered as `rom:`, and
`0xDD24`, an independent reader of the same data. Both are redirected — leaving one behind
would put two readers on two different images of the same RomFS, whose internal offsets do
not agree.

LayeredFS is not involved at all: no `romfs` folder ships for this title, so `checkLumaDir`
finds nothing, `patchLayeredFs` returns early and that `svcBreak` is unreachable.

⚠️ **This title has no graceful degradation.** For every other title a file problem just
means "runs untranslated", because the original still sits in NAND. Here the `code.ips`
sends the title to the SD card permanently: delete `dlplay_romfs.bin` but keep `code.ips`
and Download Play cannot read its resources. Remove the folder as a whole.

The image is rebuilt from the complete original tree — only the replaced slot's files
differ, every other language stays in it. That keeps "switch the console language back"
working as a way to undo the mod here too.

The Software Keyboard is built the same way and is fixed the same way: its two RomFS sites
(`0x14944`, which feeds `rom:`, and `0xE958`) are pointed at `swkbd_romfs.bin`. Its third
`OpenFileDirectly` call at `0x6F7C0` is left alone — that one opens
`ARCHIVE_SAVEDATA_AND_CONTENT`, not the RomFS.

### What the mod does not translate

**Icon labels on the HOME Menu.** The name under an icon and the text shown on the upper screen when you highlight it are text, not an image — but that text lives in each title's **SMDH** (`CXI ExeFS:/icon`, 16 language structs).

LayeredFS cannot reach ExeFS: Luma only redirects `romfs/`, `code.bin`, `code.ips`, `exheader.bin` and `locale.txt`. Changing an SMDH means rebuilding and reinstalling the title itself, i.e. **writing to NAND** — and the whole point of this project is a mod you install and remove by copying a folder. So icon labels stay in the slot's original language.

**The system font.** See the section above — LayeredFS cannot replace it.

**Real Ukrainian letters from the keyboard.** The layout is Ukrainian (see below), but the `і ї є` keys type `i ï ε` — the same substitute glyphs the rest of the mod uses. On the console that reads correctly and consistently; outside it — in a Mii name, a folder name, a post — it is Latin and Greek, not Ukrainian text. There is no way around it: real letters need a different font, which means modifying NAND.

**The text inside electronic manuals.** The Instruction Manual application itself is translated — `Back`, `Enlarge`, `Language`, `Page`, `Contents`, the language dialog. The document it displays is not.

That document does not belong to the Instruction Manual. Every title ships its own electronic manual as a separate NCCH — content index 1 within that same title. The Instruction Manual reaches it through `ARCHIVE_SAVEDATA_AND_CONTENT`, reading the documented title's content directly.

LayeredFS does not lead there. Luma's payload only intercepts mounts for `ARCHIVE_ROMFS` and only rewrites paths starting with `rom:` or the detected update mount — and of the ones Luma knows (`ro2:`, `rom2:`, `rex:`, `patch:`, `ext:`) the Instruction Manual's code contains none, only its own `rom:`. Luma has no mechanism for replacing content index 1 of a title.

It is also not one document but one per title: the Activity Log has its own, System Settings has its own, every game has its own. Translating them means rebuilding and reinstalling each title's content.

All four limits come down to the same thing: they require modifying NAND. A "Tier 2" release for people who accept that — with a NAND backup and the appropriate warnings — is a separate thing and is not part of this release.

### Other regions

Releases target **EUR** consoles. The Russian language slot only exists in EUR builds of the system software, so USA and JPN consoles are not covered by this release — they need a separate build that replaces the English slot instead. See [Building from source](#building-from-source) or open an Issue.

### Building from source

No Nintendo files are included in this repository. You need a romfs dump from **your own** console (GodMode9), placed in `work/0004003000009802/romfs/`, plus the shared font at `work/0004009B00014002/cbf_std.bcfnt.lz`. Then:

```bash
make font extract validate build package
```

Python 3.11+, no dependencies. Tools: LZ11 (de)compressor, MSBT parser/builder with byte-exact round-trip, BCFNT glyph/width reader, extractor, validator, builder, width fitter, packager.

### Contributing translations

Edit the `ua` fields in `src/strings/home_menu/*.json` (`en` holds the original). Run `make validate` before opening a PR — it rejects glyphs missing from the font, strings wider or taller than the UI can fit, and invented control tags. Width/height budgets are derived from all 8 official localisations of the title.

### Licence

Tooling and translation text: MIT (see `LICENSE`). No Nintendo assets are distributed here. Unofficial project, not affiliated with Nintendo.
