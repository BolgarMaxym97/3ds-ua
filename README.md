# 3DS UA

Український інтерфейс для Nintendo 3DS. Ставиться як мод на SD-карту через LayeredFS (Luma3DS) — **системні файли в NAND не змінюються**.

Ukrainian system UI for Nintendo 3DS. Installs as an SD-card mod via Luma3DS LayeredFS — **nothing in NAND is modified**.

[Українською](#українською) · [In English](#in-english)

---

## Українською

Мод підміняє **англійський** мовний слот на українську мову. Рядки без перекладу залишаються англійськими.

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
SD:/luma/titles/0004003000009802/romfs/message/EU_English/menu_msbt_LZ.bin
SD:/luma/titles/0004003000009802/romfs/message_hud/EU_English/hud_msbt_LZ.bin
```

**3. Увімкнути LayeredFS у Luma3DS**

- вставте SD у консоль, консоль **вимкнена**;
- натисніть і **тримайте SELECT**, потім увімкніть консоль;
- у синьому меню знайдіть `Enable game patching` (7-й пункт), натисніть **A** — має стати `(x)`;
- натисніть **START** — зберегти й перезавантажити.

**4. Перевести консоль на англійську**

`System Settings` → `Other Settings` → `Language` → **English** → `OK`.

**5. Перезавантажити консоль**

Готово.

### Видалення

Будь-який зі способів:

1. **Видалити папку мода.** SD-карту в комп'ютер, видалити `SD:/luma/titles/0004003000009802`.
2. **Змінити мову консолі** на будь-яку, крім English — переклад просто не застосується.
3. **Вимкнути LayeredFS.** SELECT при вмиканні → зняти `Enable game patching` → START. Але це також вимкне всі інші моди.

NAND не змінювався, тому видалення нічого не ламає.

### Якщо не працює

| Симптом | Причина й що робити |
|---|---|
| Усе англійською | Не увімкнено `Enable game patching`. Конфіг Luma **скидається після оновлення Luma** — поставте галочку знову. |
| Усе англійською, галочка стоїть | Перевірте шлях: має бути `luma/titles/...`, а не `luma/luma/titles/...`. Регістр TID не важливий. |
| Частина тексту англійською | Це нормально: неперекладені рядки (`OK`, `Miiverse`, `Nintendo eShop`) залишені як є. |
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

### Інші регіони

Реліз зібраний під **EUR** HOME Menu (`0004003000009802`). Англійський слот є в титулах усіх регіонів, тож для USA/JPN достатньо перезібрати мод під інший Title ID:

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

The mod replaces the **English** language slot with Ukrainian. Strings without a translation stay in English.

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
SD:/luma/titles/0004003000009802/romfs/message/EU_English/menu_msbt_LZ.bin
SD:/luma/titles/0004003000009802/romfs/message_hud/EU_English/hud_msbt_LZ.bin
```

**3. Enable LayeredFS in Luma3DS**

- put the SD card back, console **powered off**;
- hold **SELECT** and power the console on;
- in the blue config menu select `Enable game patching` (7th item), press **A** so it shows `(x)`;
- press **START** to save and reboot.

**4. Set the console language to English**

`System Settings` → `Other Settings` → `Language` → **English** → `OK`.

**5. Reboot**

Done.

### Uninstalling

Any of these:

1. **Delete the mod folder:** remove `SD:/luma/titles/0004003000009802` from the SD card.
2. **Change the console language** to anything other than English — the mod simply won't apply.
3. **Turn LayeredFS off:** hold SELECT on boot → uncheck `Enable game patching` → START. Note this disables all other mods too.

NAND was never touched, so removal cannot break anything.

### Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Everything still in English | `Enable game patching` is off. Luma's config **resets when you update Luma** — re-enable it. |
| Still English, option is on | Check the path: it must be `luma/titles/...`, not `luma/luma/titles/...`. |
| Some text is English | Expected: a few strings (`OK`, `Miiverse`, `Nintendo eShop`) are intentionally left as-is. |
| HOME Menu won't boot | Delete `SD:/luma/titles/0004003000009802` and open an Issue with your model, region and system version. |
| Empty boxes instead of letters | Please report with a photo — that's a bug. |

### Why `i` instead of `і`

The 3DS shared font contains only 66 Cyrillic glyphs (the Russian set). The Ukrainian-specific `і ї є ґ І Ї Є Ґ` are **missing**, and replacing the system font requires modifying NAND — which this project deliberately avoids.

So the build substitutes visually close glyphs that do exist: `і/І → i/I`, `ї/Ї → ï/Ï`, `є/Є → ε/Ε` (Greek), `ґ/Ґ → г/Г`. Translation files store proper Ukrainian; substitution happens at build time.

### Other regions

Releases target the **EUR** HOME Menu (`0004003000009802`). The English slot exists in every region's title, so USA (`0004003000008F02`) and JPN (`0004003000008202`) only need a rebuild against a different Title ID — see [Building from source](#building-from-source) or open an Issue.

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
