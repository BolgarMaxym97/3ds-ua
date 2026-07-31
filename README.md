# 3DS UA

Український інтерфейс для Nintendo 3DS. Ставиться як мод на SD-карту через LayeredFS (Luma3DS) — **системні файли в NAND не змінюються**.

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
| Клавіатура з російськими літерами | Так і має бути: це кирилична розкладка для введення тексту. Українських `і ї є ґ` у системному шрифті немає, тож замінити їх на клавішах неможливо. |
| `An exception occurred`, `Current process: loader` | Luma не змогла застосувати LayeredFS до титулу, який ви запускали, і зупинила консоль. Перейменуйте `SD:/luma/titles/<TID>/romfs` цього титулу на `_romfs` і перезавантажте — титул запуститься без перекладу. Напишіть в Issues з фото екрана помилки. |
| HOME Menu не запускається | Видаліть `SD:/luma/titles/0004003000009802`. Напишіть в Issues, вказавши модель, регіон і версію системи. |
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

### Що входить у реліз

| Титул | Стан |
|---|---|
| Меню HOME | ✅ перекладено |
| Налаштування системи | ✅ перекладено |
| Mii Maker | ✅ перекладено |
| Екранна клавіатура | ⛔ не входить |
| Журнал дій | ⛔ не входить |
| Гра по завантаженню | ⛔ не входить |
| Посібник | ⛔ не входить |

Чотири останні титули перекладені, але **не потрапляють в архів**: Luma не вміє під'єднати до них LayeredFS. Її завантажувач закінчує патч так:

```c
if(isApp || isApplet) { ... if(!patchLayeredFs(...)) goto error; }
error:
    svcBreak(USERBREAK_ASSERT);
```

Перевірка запускається лише тоді, коли папка `luma/titles/<TID>/romfs` існує. Тобто сама **наявність папки** для титулу, у коді якого Luma не знаходить потрібних функцій FS або місця під redirect-payload, перетворює кожен його запуск на екран помилки — вміст файлів при цьому не читається взагалі.

Тому «перекласти частково, щоб не падало» неможливо: справа не в тексті, а в самому титулі.

Конкретна причина (перевірено `tools/layeredfs_check.py` на дампах їхнього коду): Luma не знаходить у них функцію **`fsMountArchive`** — жодна з двох її сигнатур не збігається з тим, як цю функцію скомпілювали. Решта чотирьох функцій і місце під payload у них є. Luma пробачає відсутність лише `fsUnmountArchive`, тож саме цієї бракує критично.

### Чого мод не перекладає

**Підписи іконок на головному екрані.** Назва під іконкою й текст на верхньому екрані при наведенні (`Настройки системы`, `Игровые заметки`) — це не картинка, а текст, але живе він у **SMDH** кожного титулу (`CXI ExeFS:/icon`, 16 мовних структур).

LayeredFS до ExeFS не дістає — Luma підміняє лише `romfs/`, `code.bin`, `code.ips`, `exheader.bin` і `locale.txt`. Щоб змінити SMDH, треба перезібрати й перевстановити сам титул, тобто **писати в NAND** — а весь сенс проєкту в тому, що мод ставиться й зноситься копіюванням папки. Тому підписи іконок залишаються мовою слота.

**Кирилична розкладка клавіатури.** Літери на клавішах — російський набір ЙЦУКЕН. Українських `і ї є ґ` у системному шрифті немає, тож на клавішах були б порожні квадрати, а введення вставляло б символи, які консоль не намалює.

**Системний шрифт.** Див. розділ вище — LayeredFS шрифт не підміняє.

Усі три обмеження впираються в одне й те саме: вони потребують правки NAND. Логічний «Tier 2» для тих, хто на це свідомо йде, — окремий реліз із бекапом NAND і попередженнями; у цьому релізі його немає.

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
| Keyboard shows Russian letters | By design: that is the Cyrillic typing layout. The system font has no `і ї є ґ`, so the keys cannot be changed. |
| `An exception occurred`, `Current process: loader` | Luma could not apply LayeredFS to the title you launched and halted the console. Rename that title's `SD:/luma/titles/<TID>/romfs` to `_romfs` and reboot — the title then starts untranslated. Please open an Issue with a photo of the error screen. |
| HOME Menu won't boot | Delete `SD:/luma/titles/0004003000009802` and open an Issue with your model, region and system version. |
| Empty boxes instead of letters | Please report with a photo — that's a bug. |

### Why `i` instead of `і`

The 3DS shared font contains only 66 Cyrillic glyphs (the Russian set). The Ukrainian-specific `і ї є ґ І Ї Є Ґ` are **missing**, and replacing the system font requires modifying NAND — which this project deliberately avoids.

So the build substitutes visually close glyphs that do exist: `і/І → i/I`, `ї/Ї → ï/Ï`, `є/Є → ε/Ε` (Greek), `ґ/Ґ → г/Г`. Translation files store proper Ukrainian; substitution happens at build time.

### What is in the release

| Title | State |
|---|---|
| HOME Menu | ✅ translated |
| System Settings | ✅ translated |
| Mii Maker | ✅ translated |
| Software Keyboard | ⛔ not shipped |
| Activity Log | ⛔ not shipped |
| Download Play | ⛔ not shipped |
| Instruction Manual | ⛔ not shipped |

The last four are translated but **kept out of the archive**: Luma cannot hook LayeredFS
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

The precise cause (verified with `tools/layeredfs_check.py` against dumps of
their code): Luma cannot find **`fsMountArchive`** in them — neither of its two signatures
matches how that function was compiled. The other four functions and the payload space are
present. Luma only tolerates a missing `fsUnmountArchive`, so this one is fatal.

### What the mod does not translate

**Icon labels on the HOME Menu.** The name under an icon and the text shown on the upper screen when you highlight it are text, not an image — but that text lives in each title's **SMDH** (`CXI ExeFS:/icon`, 16 language structs).

LayeredFS cannot reach ExeFS: Luma only redirects `romfs/`, `code.bin`, `code.ips`, `exheader.bin` and `locale.txt`. Changing an SMDH means rebuilding and reinstalling the title itself, i.e. **writing to NAND** — and the whole point of this project is a mod you install and remove by copying a folder. So icon labels stay in the slot's original language.

**Cyrillic keyboard layout.** The key caps are the Russian ЙЦУКЕН set. The system font has no `і ї є ґ`, so replacing them would show empty boxes on the keys and type characters the console cannot render.

**The system font.** See the section above — LayeredFS cannot replace it.

All three limits come down to the same thing: they require modifying NAND. A "Tier 2" release for people who accept that — with a NAND backup and the appropriate warnings — is a separate thing and is not part of this release.

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
