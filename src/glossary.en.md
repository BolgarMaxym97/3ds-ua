# Glossary and style guide

*[Українською](glossary.md)*

One term, one translation. Check here before translating a new file.

The tables map the original wording (Russian and/or English, as it appears in the dumps) to the
Ukrainian the mod uses. Where a translation looks unexpectedly short, it is usually a width
limit — the on-screen slot is measured in pixels, and `tools/validate.py` rejects anything wider
than the widest official localisation of that string.

## System names

| Original (ru / en) | Ukrainian |
|---|---|
| Меню HOME / HOME Menu | Меню HOME |
| Настройки меню HOME | Налаштування HOME |
| программа / software | програма |
| Игровые заметки / Game Notes | Ігрові записи |
| Список друзей / Friend List | Список друзів |
| Сообщения / Notifications | Повідомлення |
| Интернет-браузер / Internet Browser | Інтернет-браузер |
| Руководство / Instruction Manual | Посібник |
| Настройки системы / System Settings | Налаштування системи |
| Загрузочные игры / Download Play | Гра по завантаженню |
| Обмен данными / Data Transfer | Перенесення даних |
| Карта SD / SD Card | Карта SD |
| Архив данных / Data Management | Керування даними |
| Режим ожидания / Sleep Mode | Режим сну |
| жетон / badge | жетон |
| папка / folder | папка |
| значок / icon | значок |
| Обмен изображениями | Обмін зображеннями |
| вид (меню) / layout | вигляд |

## Friend List

| Original (ru / en) | Ukrainian |
|---|---|
| карточка друга / friend card | картка друга |
| Код друга / Friend Code | Код друга |
| Регистрация друга / Register Friend | Реєстрація друга |
| Онлайн / Online | Онлайн |
| Офлайн / Offline | Офлайн |
| онлайн-статус / online status | стан у мережі |
| Сообщение (status on the card) / Message | Статус |
| Любимая игра / Favourite Title | Улюблена гра |
| Сейчас играет / Software in Use | Зараз грає |
| Локальный / Local (registration method) | Локально |
| Участвовать в игре / Join Friend's Game | Приєднатися до гри |
| приостановленная программа / suspended software | призупинена програма |

**Width exception:** `Settings` in the Friend List (`fri_option`, `fri_opti_title`) is
**Параметри**, not «Налаштування»: the slot is 168px and «Налаштування» renders at 178px.
Everywhere else in the mod `Settings` stays «Налаштування».

## Camera and Sound

| Original (en) | Ukrainian |
|---|---|
| Outer / Inner Camera | задня / передня камера (not «зовнішня» — it does not fit the slot) |
| Shoot | Зйомка |
| Graffiti | Малювання |
| Video Tools | Робота з відео |
| Trick Shot modes | особливі режими |
| Interval Shot / Frame Pick / Clip Link | Зйомка за часом / Вибір кадру / Зв'язка кліпів |
| Merge / Sparkle / Dream / Pinhole / Mystery / Low-Light | Злиття / Блиск / Мрія / Віньєтка / Загадка / Ніч |
| Manual Controls | ручні налаштування |
| Film / Sharpness / Contrast / Brightness | Плівка / Різкість / Контраст / Яскравість |
| Attention Sound | Звук уваги |
| Info Display | Показ даних |
| Photo Save Location | Місце збереження фото |
| Usage Tips | Поради |
| System Memory | пам'ять системи |
| Playlist | список (відтворення) |
| Autoplay / Shuffle All / Resume | Автогра / Усе впереміш / Далі |
| Hit Parade / Compatibility | хіт-парад / спорідненість |
| visualiser | візуалізація |
| `\ue004\ue005` Percussion | Ударні (the button glyphs stay) |
| Harmony (High / Low / Synth) | гармонія (висока / низька / синт-) |
| budgie (the mascot) | папужка (feminine gender, «цвірінь» instead of «chirp») |

**Width exceptions:** `Settings` in the Camera, in Sound and in their dialogs is **Параметри**
(141px slot, «Налаштування» renders at 178px); `Delete` on buttons is **Стерти**; `Copy` in
Sound is **Копія**; `Confirm` where the slot is 134px is **Готово**.

**The backwards magic words** (`D_080`–`D_084`, `D_116` in Sound) are built on English
phonetics, so they are translated by substituting Ukrainian words spelled backwards:
`тівирп` → «привіт», `юатів` → «вітаю», `уюкяд` → «дякую», `однетнін` → «нінтендо».

## StreetPass Mii Plaza

| Original (en) | Ukrainian |
|---|---|
| StreetPass Mii Plaza | Площа StreetPass Mii |
| Plaza | Площа |
| StreetPass Quest / Quest II | Порятунок Mii / Порятунок Mii II |
| Puzzle Swap | Збери пазл |
| StreetPass Map | Карта StreetPass |
| Play Coins | ігрові монетки (the `\ue075` glyph stays in front of them) |
| piece / panel | частинка / панель |
| hat | капелюх |
| hero / wanderer / old ally | герой / мандрівник / давній соратник |
| combo magic / combo blade | спільна магія / серія ударів |
| Venture Forth | У путь |
| Current Results | Проміжний результат |
| Accomplishments | Досягнення |
| StreetPass Hits | Зустрічей |
| Plaza Population | Мешканців |
| greeting (general / personal) | вітання (загальне / особисте) |
| rating / "fantastic" | оцінка / «чудово» |
| extra data | додаткові дані |

Label suffixes tell the speaker apart: `_prin` is the prince (masculine), `_pris` the princess
(feminine), no suffix is the ruler. Same for `_m`/`_f` in the Mii lines. Where the phrase is in
the present tense both variants come out identical — that is fine.

**Width exceptions:** `Confirm` in the Mii Selector is **Готово** (167px slot); `On`/`Off` in
the Plaza settings are **Так**/**Ні** (46px slot); `Mii Birthday` is **Народження** (183px
slot); `Current Results` in the music list is **Проміжний підсумок**.

## Notifications, Game Notes, the error applet

| Original (en) | Ukrainian |
|---|---|
| Notifications | Повідомлення |
| Unread Notifications | Непрочитані листи (width exception, 304px slot) |
| Unread: %d | Нових: %d (189px slot) |
| Game Notes | Ігрові записи |
| note | запис |
| Export (a note as a photo) | Зберегти |
| Clear (erase a note) | Стерти |
| suspended software | призупинена програма |
| User Agreement | Угода користувача |
| Privacy Policy | Політика конфіденційності |
| I Accept / I Decline | Приймаю / Не приймаю |
| Error Code | Код помилки |

**Width exceptions:** `Delete` in Notifications is **Стерти** (104px slot); `Launch software`
is **Відкрити програму** (238px slot); `View Documents` in the agreement is
**Переглянути тексти** (279px slot).

## Browser, eShop, games, System Transfer

| Original (en) | Ukrainian |
|---|---|
| Internet Browser | Інтернет-браузер |
| Bookmarks | Закладки |
| Page Info | Про сторінку |
| certificate / Root CA | сертифікат / кореневий ЦС |
| Text Wrap | Перенос тексту |
| Watch List | Список бажань |
| Add Funds / Balance | Додати кошти / Баланс |
| Account Activity | Історія покупок |
| Charts | Хіт-парад |
| Just for You Offers | Пропозиції для вас |
| Redeem Download Code | Використати код завантаження |
| Sleep Mode Download | Завантаження в режимі сну |
| blocks (memory) | блоки |
| add-on content | додатковий вміст |
| System Transfer | Перенесення даних |
| source / target system | консоль-джерело / консоль-приймач |
| AR Card | картка AR |
| Star Pics / Mii Pics | Фото героїв / Фото з Mii |
| Fresh Face | свіже обличчя |
| Share the Fun! | Гра для всіх! |
| Sneaky Snaps | Знімки зненацька |
| Nintendo Zone | Nintendo Zone |
| Saved Pages | Збережені сторінки |

**Width exceptions** — the shop and game slots are particularly tight: `Publisher` →
**Видав.**, `Download` → **Завантаж.**, `Free` → **Безкошт.**, `Month` → **Міс.**,
`Email address` → **Ел. пошта**, `Delete` → **Стерти**, `Sort By...` → **Сорт.**,
`Start in 2D/3D` → **Пуск у 2D/3D**, `Fishing` → **Рибалка**, `Clock` → **Час**,
`Shop` → **Магазин**.

## Never translated

`Nintendo`, `Nintendo 3DS`, `Nintendo eShop`, `StreetPass`, `SpotPass`, `Miiverse`, `Mii`,
`HOME`, `amiibo`, `microSD`, `Wi-Fi`, `NNID`, `PIN`.

## Buttons and actions

Infinitive forms: `Запустити`, `Видалити`, `Скопіювати`, `Створити`, `Відкрити`, `Закрити`,
`Скасувати`, `Гаразд` (but `OK` stays `OK`), `Далі`, `Назад`, `Так` / `Ні`.

## Style

- address the user as «ви», lowercase;
- do not add «будь ласка» where the original had no "please";
- quotation marks are «guillemets», the dash is `—`, the ellipsis is `…`;
- no calques from Russian: `настройки` → `налаштування`, `загрузка` → `завантаження`,
  `удалить` → `видалити`, `включить` → `увімкнути`, `подключение` → `з'єднання`/`підключення`,
  `сохранить` → `зберегти`, `текущий` → `поточний`, `следующий` → `наступний`,
  `коснитесь` → `торкніться`, `выберите` → `виберіть`;
- the apostrophe is ASCII `'` (U+02BC is not in the font).

## Technical constraints

- control tokens `{t:group.type:hex}` / `{/t:group.type}` — do not touch, reorder or add them;
- substitutions `%d`, `%s`, `%1$s` — keep the same count and order;
- button glyph characters (`` = A, `` = B and so on) — keep them;
- no more `\n` line breaks than the original has;
- the rendered line width must not exceed the widest official localisation
  (`tools/validate.py` enforces this);
- no characters outside `assets/font_charset.txt`: `і→i`, `І→I`, `ї→ï`, `Ї→Ï`, `є→ε`, `Є→Ε`,
  `ґ→г`. `tools/build.py` performs this substitution automatically — the JSON files hold
  **proper** Ukrainian.
