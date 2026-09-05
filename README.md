# 3DS UA 🇺🇦

**Українська мова для Nintendo 3DS.** Мод стає на місце однієї з мов консолі: у списку мов з'являється «Українська», і система починає говорити українською. Решта мов лишається на місці.

Збірки однакові за перекладом, а різняться двома речами — чию клітинку займає українська і для якої консолі архів:

- **`3ds-ua-from-ru-<версія>-old3ds.zip`** — замість російської, для 3DS / 3DS XL / 2DS.
- **`3ds-ua-from-ru-<версія>-new3ds.zip`** — замість російської, для New 3DS / New 3DS XL / New 2DS XL.
- **`3ds-ua-from-en-<версія>-old3ds.zip`** — замість англійської, для 3DS / 3DS XL / 2DS.
- **`3ds-ua-from-en-<версія>-new3ds.zip`** — замість англійської, для New 3DS / New 3DS XL / New 2DS XL.

Ставте одну з них, не кілька. Архіви для різних консолей саме тому й окремі, що New 3DS має власні копії Інтернет-браузера і Здоров'я і безпеки, а Luma шукає файли для них у папці Old3DS-івського титулу — той самий файл на різних консолях мусить бути різним. Не той архів дає креш Здоров'я і безпеки й наполовину неперекладений браузер.

Файли самої консолі не змінюються — усе живе на SD-карті. Видалили папки, і все повернулося як було.

**Ціль проєкту — повний українізатор системи:** усе, що видно на екрані, має бути українською. Зараз перекладено **31 частина системи плюс одинадцять електронних довідників**, робота триває.

[Українською](#що-вже-українською) · [In English](#in-english)

---

<table>
<tr>
<td><img src="assets/pictures/language-picker.png" width="250" alt="Налаштування системи: вибір мови, вибрано «Українська»"></td>
<td><img src="assets/pictures/home-menu-activity-log.png" width="250" alt="Меню HOME: банер Журналу дій"></td>
<td><img src="assets/pictures/home-menu-system-settings.png" width="250" alt="Меню HOME: назва додатка «Налаштування системи»"></td>
</tr>
<tr>
<td><img src="assets/pictures/system-settings.png" width="250" alt="Головний екран Налаштувань системи"></td>
<td><img src="assets/pictures/friend-list.png" width="250" alt="Список друзів"></td>
<td><img src="assets/pictures/ar-games.png" width="250" alt="Меню HOME: банер AR Games"></td>
</tr>
<tr>
<td><img src="assets/pictures/home-menu-streetpass-plaza.png" width="250" alt="Меню HOME: банер Площі StreetPass Mii"></td>
<td><img src="assets/pictures/manual-system-settings-contents.png" width="250" alt="Електронний довідник Налаштувань системи: зміст"></td>
<td><img src="assets/pictures/manual-system-settings-page.png" width="250" alt="Електронний довідник Налаштувань системи: сторінка «Під'єднання до Інтернету»"></td>
</tr>
</table>

## Що вже українською

Меню HOME (разом з назвами додатків під іконками) · Налаштування системи (разом з назвами програм у **Керуванні даними**) · Mii Maker · Журнал дій · Електронний посібник · Гра по завантаженню · екранна клавіатура з українською розкладкою · Список друзів · Камера Nintendo 3DS · швидка камера на `L`+`R` · Звук Nintendo 3DS · Здоров'я і безпека · Площа StreetPass Mii · Вибір Mii · Сповіщення (разом з **вбудованими підказками**, що прийшли з першим запуском консолі) · Ігрові записи · екран помилки · Інтернет-браузер · Nintendo eShop · Перенесення даних · Оглядач Nintendo Zone · Face Raiders · AR Games · Налаштування amiibo · аплет покупок і оновлень eShop · 3DS Memo · аплет Circle Pad Pro · Miiverse · публікація в Miiverse · **Дані Nintendo Network ID** (повністю: вхід, інформація про користувача, налаштування пароля, зміна Mii, підтвердження пошти — усі 290 написів) · **тексти помилок системи** (усі 259 повідомлень) · список країн і регіонів у налаштуваннях профілю та на Карті StreetPass (усі 67 країн і всі 724 їхні області) · назва панелі в Обміні частинками · **електронні довідники** дванадцяти додатків: Інтернет-браузера, Налаштувань системи, Журналу дій, Гри по завантаженню, Камери, Звуку, Mii Maker, Площі StreetPass Mii, Nintendo eShop, Face Raiders, AR Games та Інтернет-браузера New 3DS · **власні титули New 3DS**: банер і назва Здоров'я і безпеки, сам додаток Здоров'я і безпека разом з його документом та окремий Інтернет-браузер New 3DS.

## Що потрібно

- Nintendo 3DS / 2DS / New 3DS **європейського (EUR) регіону**
- встановлена **Luma3DS** — кастомна прошивка
- SD-карта з ~55 МБ вільного місця
- за бажанням — **Universal-Updater**: з ним усе ставиться прямо з консолі, без виймання картки

Немає Luma3DS? Спершу пройдіть [3ds.hacks.guide](https://3ds.hacks.guide/) — без неї мод не працює.

## Встановлення через Universal-Updater

Найпростіший шлях: картку виймати не треба, оновлення потім приходять самі.

**1. Додайте магазин**

Відкрийте [Universal-Updater](https://github.com/Universal-Team/Universal-Updater) → `Settings` → `Select UniStore` → `Add new` → `Add with keyboard` і введіть:

```
https://raw.githubusercontent.com/BolgarMaxym97/3ds-ua/main/unistore/3ds-ua.unistore
```

**2. Встановіть**

Знайдіть у списку **3DS UA** і виберіть скрипт для своєї консолі:

| Скрипт | Кому |
|---|---|
| `1. Встановити: New 3DS / New 2DS XL · замість російської` | New 3DS, New 3DS XL, New 2DS XL |
| `2. Встановити: New 3DS / New 2DS XL · замість англійської` | те саме, але замість англійської |
| `3. Встановити: 3DS / 2DS · замість російської` | 3DS, 3DS XL, 2DS |
| `4. Встановити: 3DS / 2DS · замість англійської` | те саме, але замість англійської |

Модель написана спереду під нижнім екраном: якщо там `New`, беріть перші два.

Жодних питань скрипт не ставить: Universal-Updater виконує все у своїй **черзі**, і будь-яке питання чекало б там на окремому екрані, який легко не помітити. Тому вибір — це просто потрібний рядок у списку.

Помилилися з вибором — запустіть відповідний скрипт `Видалити:`, тоді потрібний `Встановити:`.

**3. Далі — кроки 2 і 3 з ручного встановлення нижче** (`Enable game patching` і вибір мови). Їх не обійти жодним застосунком.

Коли вийде нова версія, на іконці **3DS UA** з'явиться зелена стрілка — запустіть той самий скрипт `Встановити:`, що й першого разу. Він перезапише файли поверх.

## Встановлення вручну (з SD-карти)

**1. Скопіюйте файли на SD-карту**

Візьміть з [Releases](../../releases) один архів: `-from-ru-` ставить українську замість російської, `-from-en-` — замість англійської; `-old3ds` для 3DS / 3DS XL / 2DS, `-new3ds` для New 3DS / New 3DS XL / New 2DS XL. Вимкніть консоль, вставте SD-карту в комп'ютер, розпакуйте архів і скопіюйте папку `luma` в корінь картки — туди, де вже є папка `luma`. Комп'ютер спитає, чи об'єднати папки — погодьтеся.

Поверніть картку в консоль.

**2. Увімкніть патчі в Luma**

Натисніть і **тримайте SELECT**, тоді увімкніть консоль — з'явиться синє меню.

Знайдіть рядок **`Enable game patching`** (сьомий згори), натисніть **A**, щоб навпроти з'явилося `(x)`. Натисніть **START** — консоль збережеться й перезавантажиться.

**3. Виберіть українську**

`Налаштування системи` → `Інші налаштування` → `Мова` → **Українська** → `OK`.

Це той пункт, де раніше було «Русский» (у збірці `from-en` — «English»). Він завжди підписаний «Українська», хай якою мовою зараз говорить консоль, тож ви побачите його одразу.

Консоль перезавантажиться сама. Готово.

## Як видалити

Будь-який спосіб:

1. **У Universal-Updater** → **3DS UA** → скрипт `Видалити:` для того самого варіанта, який ставили. Прибирає рівно ті файли, які клав, і нічого не питає. Якщо він обірветься з помилкою (таке буває, коли частину файлів уже видалено вручну або стоїть старіша версія) — є запасний `9. Видалити примусово`, той питає підтвердження на кожну папку, зате працює за будь-якого стану картки.
2. **Змінити мову консолі** на будь-яку іншу — переклад просто не застосується.
3. **Видалити папки мода** з `SD:/luma/titles/` вручну.
4. **Вимкнути `Enable game patching`** у меню Luma (це вимкне й інші моди).

Системні файли не змінювалися, тому видалення нічого не ламає.

**Один виняток.** Вбудовані підказки у Сповіщеннях консоль колись скопіювала собі в NAND, і файлами на SD-карті їх уже не дістати — мод переписує їх у самій базі. Після видалення мода вони лишаться українськими (не зіпсованими — просто українськими). Якщо цього не хочеться, видаліть `SD:/luma/titles/0004003000009802/code.ips` **до** першого запуску з модом: тоді підказки лишаться мовою, яку мод займає, разом з назвами додатків і банерами, які той самий файл перекладає.

## Чого поки що немає

- **України в списку країн немає.** У таблиці кодів країн Nintendo її немає взагалі: європейський блок суцільний, без пропусків, `…99 Румунія, 100 Росія, 101 Сербія…`. Код країни — системна величина, від якої залежать NNID, eShop і вікові рейтинги, і нового рядка в таблицю не вставити. Раніше мод перейменовував код `100` на «Україна» разом з його областями — але **назву за цим кодом кожен читає своєю таблицею**, тому інші гравці в онлайні, NNID, eShop і StreetPass однаково бачили «Росія», а українська область показувалася їм російською, що стоїть під тим самим номером. Тепер список показує те, що консоль справді повідомляє: код `100` — це `росія (болота)` з її ж 83 областями, усе з малої літери. Плутанини регіонів в онлайні більше немає.

  **Мова й країна в 3DS ніяк не пов'язані:** переклад стоїть на мовному слоті, тому інтерфейс лишиться повністю українським з будь-якою країною в профілі — ставте будь-яку.
- **Українських `і ї є ґ`.** У шрифті самої консолі їх немає, тому мод показує візуально близькі `i ï ε г`. Замінити шрифт можна лише правкою системних файлів — а проєкт цього свідомо не робить.
- **Справжніх літер з клавіатури.** Розкладка українська (`ы`→`і`, `ъ`→`ї`, `э`→`є`, а на місці `ё` тепер апостроф), але вводяться ті самі символи-замінники.
- **Електронних довідників решти додатків.** Переглядач бере довідник кожного додатка окремо, тож кожен треба здампити з вашої консолі й перекласти. Готові дванадцять — Інтернет-браузера, Налаштувань системи, Журналу дій, Гри по завантаженню, Камери, Звуку, Mii Maker, Площі StreetPass Mii, Nintendo eShop, Face Raiders, AR Games та Інтернет-браузера New 3DS, усі повністю; решта показує той самий довідник, що й раніше. Місця лишилося небагато: таблиця шляхів переглядача та таблиця назв додатків займають 617 із 1064 байтів вільного місця в його коді. Довідники ігор належать іграм, а не системі, тож лишаються як є.
- **Назв додатків у eShop, Перенесенні даних та Ігрових записах** — там вони лишаються мовою, яку мод займає. У Меню HOME, Журналі дій, Керуванні даними та Електронному довіднику вони українські.
- **Електронні довідники у збірці `from-en`** беруть за основу російський документ: у нього більше сторінок, ніж в англійського, тому в українську клітинку лягає він цілком, зі своїми знімками екрана. Сам російський довідник при цьому лишається на місці.
- **Кириличної клавіатури на російській мові у збірці `from-en`.** Аплет клавіатури дозволяє кирилицю рівно одній мові консолі, і в цій збірці вона віддана українській. Сам російський інтерфейс лишається на місці, але клавіатура на ньому буде латинською. У `from-ru` такого немає.
- **Збірки для консолей USA та JPN.** Європейських мовних слотів у них немає, тож потрібна окрема збірка — напишіть в Issues, якщо вона вам потрібна.

## Якщо щось пішло не так

| Що бачите | Що робити |
|---|---|
| Інтерфейс лишився як був | Не увімкнено `Enable game patching`. Ця галочка злітає після оновлення Luma — поставте знову. |
| Не українською, а галочка стоїть | Перевірте шлях: має бути `luma/titles/…`, а не `luma/luma/titles/…`. Ще перевірте, що архів той: `from-ru` вмикається на пункті «Русский», `from-en` — на «English». |
| У списку мов немає «Українська» | Архів скопіювався не повністю, або консоль не EUR-регіону. |
| Частина тексту не українською | Так і має бути: технічні написи (`OK`, `Miiverse`, формати дат) лишені як є. |
| У списку країн немає України | Свого коду в системі Україна не має — [чому](#чого-поки-що-немає). Ставте будь-яку країну, інтерфейс лишиться українським. |
| `An exception occurred` при запуску додатка | Перейменуйте `SD:/luma/titles/<номер>/romfs` цього додатка на `_romfs` і перезавантажте — він запуститься без перекладу. І [напишіть в Issues](../../issues) з фото екрана. |
| Меню HOME не завантажується | Видаліть `SD:/luma/titles/0004003000009802/code.ips`. Не допомогло — усю папку `0004003000009802`. |
| Universal-Updater не бачить магазин | Звірте посилання посимвольно. Після оновлення магазину дайте ~5 хвилин: GitHub кешує файл. |
| У Universal-Updater помилка завантаження | Реліз ще не опубліковано або зникла мережа — спробуйте пізніше чи візьміть архів вручну. Ще одна причина — збита дата на консолі: тоді не проходить перевірка сертифіката. |
| Не вистачає місця | Під час встановлення треба ~55 МБ вільних: 23 МБ архіву плюс 30 МБ розпакованого. |
| Після запуску скрипта нічого не відбувається | Universal-Updater кладе роботу в **чергу**. Відкрийте її третьою іконкою в лівій панелі на нижньому екрані — там видно поступ. |
| `Видалити:` обірвався помилкою | Частини файлів уже немає. Запустіть `9. Видалити примусово` — він працює за будь-якого стану картки. |
| Якийсь додаток крешить після встановлення | У вас старіша його версія. Видаліть папку цього додатка з `SD:/luma/titles/` — решта перекладу працюватиме. Номери папок є в [технічному описі](docs/internals.md). |

Порожні квадрати замість літер, обрізані чи накладені написи — це баг. [Відкрийте Issue](../../issues) з фото екрана.

## Як допомогти

- **Знайшли помилку чи кривий переклад** — [відкрийте Issue](../../issues/new/choose). Там два шаблони: «Баг на консолі» і «Кривий переклад» — вони самі спитають усе потрібне. Фото екрана допомагає найбільше.
- **Хочете виправити самі** — правте поле `ua` у `src/strings/<додаток>/*.json` (поруч у полі `en` — оригінал) і надсилайте Pull Request. Терміни звіряйте з [глосарієм](src/glossary.md), а перед PR запустіть `make validate`: воно перевірить, що текст влазить на екран і не містить символів, яких у шрифті немає. Про збірки думати не треба — переклад один на обидві, бо межі ширини рахуються від найдовшої офіційної локалізації, а не від слота.
- **Знаєте, чого ще бракує** — [напишіть в Issues](../../issues). Там же видно, що вже взяте в роботу.

## Технічні деталі

Як воно влаштовано: за що відповідає кожна папка, чому частині додатків потрібна правка коду, звідки беруться назви під іконками і як добудовано шрифт верхнього рядка — **[docs/internals.md](docs/internals.md)**.

Зібрати мод самому зі своїх дампів — **[docs/dumping.md](docs/dumping.md)**.

## Ліцензія

Код інструментів і текст перекладу — MIT. Файлів Nintendo в репозиторії немає; збірка потребує дампу з власної консолі. Проєкт неофіційний, з Nintendo не пов'язаний.

---

## In English

**Ukrainian system language for the Nintendo 3DS.** The mod takes the place of one of the console's languages: «Українська» appears in the language list and the console starts speaking Ukrainian. Every other language stays untouched.

The builds carry the same translation and differ in two things — whose slot Ukrainian takes, and which console the archive is for:

- **`3ds-ua-from-ru-<version>-old3ds.zip`** — in place of Russian, for the 3DS / 3DS XL / 2DS.
- **`3ds-ua-from-ru-<version>-new3ds.zip`** — in place of Russian, for the New 3DS / New 3DS XL / New 2DS XL.
- **`3ds-ua-from-en-<version>-old3ds.zip`** — in place of English, for the 3DS / 3DS XL / 2DS.
- **`3ds-ua-from-en-<version>-new3ds.zip`** — in place of English, for the New 3DS / New 3DS XL / New 2DS XL.

Install one of them, not several. The per-console split exists because a New 3DS runs its own copies of the Internet Browser and of Health and Safety while Luma keeps reading the Old 3DS title's folder for them: the same file has to hold different bytes on the two consoles. The wrong archive crashes Health and Safety and leaves the browser half translated.

Nothing on the console itself is modified — it all lives on the SD card. Delete the folders and everything is back to stock.

**The goal is a complete Ukrainian localisation** of everything visible on screen. **31 parts of the system plus eleven electronic manuals** are done so far; work continues.

### Already in Ukrainian

HOME Menu (including the application names under the icons) · System Settings (including the software names in **Data Management**) · Mii Maker · Activity Log · Instruction Manual · Download Play · Software Keyboard with a Ukrainian layout · Friend List · Camera · the quick camera on `L`+`R` · Sound · Health & Safety · StreetPass Mii Plaza · Mii Selector · Notifications (including the **built-in tips** that arrived with the console's first boot) · Game Notes · error applet · Internet Browser · Nintendo eShop · System Transfer · Nintendo Zone · Face Raiders · AR Games · amiibo Settings · the eShop purchase/update applet · 3DS Memo · the Circle Pad Pro applet · Miiverse · Miiverse posting · **Nintendo Network ID Settings** (in full: sign-in, user information, password settings, Mii, email verification - all 290 strings) · the **system error messages** (all 259 of them) · the country and region lists in the profile settings and on the StreetPass Map (all 67 countries and all 724 of their regions) · the Puzzle Swap panel name · the **electronic manuals** of twelve titles, in full: Internet Browser, System Settings, Activity Log, Download Play, Camera, Sound, Mii Maker, StreetPass Mii Plaza, Nintendo eShop, Face Raiders, AR Games and the New 3DS Internet Browser · the **New 3DS titles of its own**: the Health & Safety banner and icon name, the Health & Safety application together with its document, and the separate New 3DS Internet Browser.

### Requirements

- a Nintendo 3DS / 2DS / New 3DS of the **European (EUR) region**
- **Luma3DS** custom firmware installed
- an SD card with ~55 MB free
- optionally **Universal-Updater**: with it everything is done from the console, no card removal

No Luma3DS yet? Follow [3ds.hacks.guide](https://3ds.hacks.guide/) first — the mod does nothing without it.

### Installation via Universal-Updater

The easy path: the card stays in the console, and later updates announce themselves.

**1. Add the store**

Open [Universal-Updater](https://github.com/Universal-Team/Universal-Updater) → `Settings` → `Select UniStore` → `Add new` → `Add with keyboard`, and enter:

```
https://raw.githubusercontent.com/BolgarMaxym97/3ds-ua/main/unistore/3ds-ua.unistore
```

**2. Install**

Find **3DS UA** in the list and pick the script for your console:

| Script | For |
|---|---|
| `1. Встановити: New 3DS / New 2DS XL · замість російської` | New 3DS, New 3DS XL, New 2DS XL |
| `2. Встановити: New 3DS / New 2DS XL · замість англійської` | the same, replacing English |
| `3. Встановити: 3DS / 2DS · замість російської` | 3DS, 3DS XL, 2DS |
| `4. Встановити: 3DS / 2DS · замість англійської` | the same, replacing English |

The model is printed on the front, below the bottom screen: if it says `New`, take one of the first two.

The scripts ask nothing. Universal-Updater runs everything through its **queue**, where a prompt would sit on a separate screen that is easy to miss — so the choice is simply which line you pick.

Picked wrong? Run the matching `Видалити:` script, then the right `Встановити:` one.

**3. Then do steps 2 and 3 of the manual installation below** (`Enable game patching` and picking the language). No app can do those for you.

When a new version ships, a green arrow appears on the **3DS UA** icon — run the same `Встановити:` script as before; it overwrites in place.

### Installation from the SD card (manual)

**1. Copy the files onto the SD card**

Grab one archive from [Releases](../../releases): `-from-ru-` puts Ukrainian in place of Russian, `-from-en-` in place of English; `-old3ds` is for the 3DS / 3DS XL / 2DS, `-new3ds` for the New 3DS / New 3DS XL / New 2DS XL. Power the console off, put the SD card in your computer, unpack the archive and copy the `luma` folder into the card's root — where a `luma` folder already exists. Agree when your computer offers to merge them.

Put the card back.

**2. Enable patching in Luma**

Hold **SELECT** and power the console on — the blue Luma menu appears.

Select **`Enable game patching`** (7th line), press **A** so it reads `(x)`, then press **START** to save and reboot.

**3. Pick Ukrainian**

`System Settings` → `Other Settings` → `Language` → **Українська** → `OK`.

That is the entry that used to read «Русский» — «English» in the `from-en` build. It is labelled «Українська» whatever language the console currently runs in, so you can find it right away.

The console reboots itself. Done.

### Uninstalling

Any of these:

1. **In Universal-Updater** → **3DS UA** → the `Видалити:` script for the variant you installed. It removes exactly the files it put there and asks nothing. If it stops with an error (some files already gone, or an older version installed), use the fallback `9. Видалити примусово` — it confirms every folder, but works whatever state the card is in.
2. **Switch the console language** to anything else — the translation simply won't apply.
3. **Delete the mod folders** from `SD:/luma/titles/` by hand.
4. **Turn `Enable game patching` off** in the Luma menu (this disables other mods too).

Nothing in the system was modified, so removal cannot break anything.

**One exception.** The built-in Notification tips were copied into NAND by the console long ago, and no file on the SD card can reach them — the mod rewrites them inside that database. After you remove the mod they stay Ukrainian (not corrupted — simply Ukrainian). If you'd rather they didn't, delete `SD:/luma/titles/0004003000009802/code.ips` **before** the first boot with the mod: the tips then stay Russian, along with the application names and banners that same file translates.

### Known limits

- **Ukraine is not in the country list.** Nintendo's country table has no Ukraine at all: the European block runs unbroken, `…99 Romania, 100 Russia, 101 Serbia…`. The country code is a system-wide value that NNID, the eShop and age ratings depend on, and no new row fits in the table. The mod used to rename code `100` to «Україна» along with its regions — but **every other machine resolves that code with its own table**, so other players online, NNID, the eShop and StreetPass saw Russia anyway, and a Ukrainian oblast reached them as the Russian one sharing its index. The list now says what the console actually reports: code `100` is `росія (болота)` with its own 83 oblasts, lowercase throughout. No more region mix-ups online.

  **Language and country are unrelated on the 3DS:** the translation hangs off the language slot, so the interface stays fully Ukrainian whatever country your profile says — pick any.
- **The Ukrainian letters `і ї є ґ`** are not in the console's font, so the mod shows the visually closest `i ï ε г`. Replacing the font would mean modifying the system itself, which this project deliberately avoids.
- **Typing them.** The keyboard layout is Ukrainian (`ы`→`і`, `ъ`→`ї`, `э`→`є`, `ё`→apostrophe), but it types those same substitute characters.
- **The electronic manuals of the remaining titles.** The viewer reads each title's own manual, and each one has to be dumped off your console and translated separately. Twelve ship in full; every other title shows the manual it always did. The ceiling is space, not text: the viewer's path table and its SMDH name table share one 1064-byte window of `.rodata` padding, and twelve titles use 617 of it. A game's manual belongs to the game, not to the system, so those stay as they are.
- **Application names in the eShop, System Transfer and Game Notes** are still in the language the mod replaces. In the HOME Menu, the Activity Log, Data Management and the Instruction Manual they are Ukrainian.
- **The electronic manuals in the `from-en` build** are built from the Russian document: it has more pages than the English one, so it is copied into the Ukrainian slot whole, its own screenshots included. The Russian manual itself stays where it was.
- **A Cyrillic keyboard under Russian in the `from-en` build.** The keyboard applet grants Cyrillic to exactly one system language, and in this build that is Ukrainian. The Russian interface itself stays where it was, but its keyboard will be Latin. The `from-ru` build has no such catch.
- **USA and JPN consoles** have none of the European language slots and need a separate build. Open an Issue if you want one.

### If something goes wrong

| Symptom | Fix |
|---|---|
| Interface is unchanged | `Enable game patching` is off. It resets when you update Luma — turn it back on. |
| Still not Ukrainian, the option is on | Check the path: `luma/titles/…`, not `luma/luma/titles/…`. And check the archive matches the entry you picked: `from-ru` turns on at «Русский», `from-en` at «English». |
| No «Українська» in the language list | The archive was not copied fully, or the console is not EUR. |
| Some text is not Ukrainian | Expected: technical strings (`OK`, `Miiverse`, date formats) are left as they are. |
| Ukraine is missing from the country list | The system has no country code for it, see [Known limits](#known-limits). Pick any country; the interface stays Ukrainian. |
| `An exception occurred` when opening an app | Rename that app's `SD:/luma/titles/<id>/romfs` to `_romfs` and reboot — it will start untranslated. Please [open an Issue](../../issues) with a photo. |
| HOME Menu won't boot | Delete `SD:/luma/titles/0004003000009802/code.ips`. If that doesn't help, delete the whole `0004003000009802` folder. |
| Universal-Updater doesn't see the store | Check the URL character by character. After the store is updated, give it ~5 minutes: GitHub caches the file. |
| Download error in Universal-Updater | The release isn't published yet, or the network dropped — try later or grab the archive by hand. Another cause is a wrong console clock, which fails the certificate check. |
| Not enough space | Installing needs ~55 MB free: 23 MB of archive plus 30 MB unpacked. |
| Nothing happens after starting a script | Universal-Updater puts the work in a **queue**. Open it with the third icon in the left sidebar on the bottom screen to watch progress. |
| A `Видалити:` script stopped with an error | Some files are already gone. Run `9. Видалити примусово`, which works whatever state the card is in. |
| An app crashes after installing | You have an older build of it. Delete that app's folder from `SD:/luma/titles/` — the rest keeps working. Folder numbers are in the [technical write-up](docs/internals.en.md). |

Empty boxes instead of letters, clipped or overlapping text — that's a bug. [Open an Issue](../../issues) with a photo.

### Contributing

- **Found a mistake or an awkward wording** — [open an Issue](../../issues/new/choose). Two templates are there — «Баг на консолі» (a bug) and «Кривий переклад» (a wording problem) — and they ask for everything needed. A photo of the screen helps most.
- **Want to fix it yourself** — edit the `ua` field in `src/strings/<app>/*.json` (`en` next to it is the original) and send a Pull Request. Check terms against the [glossary](src/glossary.en.md), and run `make validate` first: it checks that the text fits on screen and uses no characters the font lacks. No need to think about the two builds — the translation is shared, because the width budgets come from the longest official localisation rather than from the slot.
- **Know what else is missing** — [tell us in an Issue](../../issues).

### Technical details

How it works — what each folder does, why some titles need a code patch, where the names under the icons come from, how the top-bar font was extended: **[docs/internals.en.md](docs/internals.en.md)**.

Building the mod from your own dumps: **[docs/dumping.en.md](docs/dumping.en.md)**.

### Licence

Tooling code and translation text are MIT. No Nintendo files are in this repository; building requires a dump from your own console. Unofficial project, not affiliated with Nintendo.
