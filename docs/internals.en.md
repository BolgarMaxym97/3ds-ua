# How it works inside

*[Українською](internals.md)*

The technical side of the project: why some titles are served by LayeredFS alone, why others
need a code patch, and why a few need their whole RomFS off the SD card; where the names under
the icons come from, how the top-bar font was extended, and how to build the mod from your own
dumps.

Users do not need any of this — installation instructions are in the [README](../README.md).

---

## What each folder under `luma/titles/` is

A folder name is the Title ID (TID) of the system title it overrides. Luma reads it only when that exact title launches, so nothing in the mod is spare.

| Folder (TID) | Title | Contents |
|---|---|---|
| `0004003000009802` | HOME Menu | `romfs/` + `code.ips` — LayeredFS plus the application names |
| `0004001000022000` | System Settings | `romfs/` + `code.ips` + `area/` — LayeredFS plus the country list from the `area` archive |
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
| `000400300000D602` | eShop applet (`mint`) | `romfs/` + `code.ips` + `exheader.bin` — LayeredFS plus a code patch |
| `0004003000009C02` | Game Notes | `romfs/` — LayeredFS |
| `0004003000009D02` | Internet Browser | `romfs/` — LayeredFS |
| `0004001000022900` | Nintendo eShop | `romfs/` + `exheader.bin` — LayeredFS plus a rights patch |
| `000400300000BE02` | Miiverse (`cave`) | `romfs/` + `code.ips` + `exheader.bin` + `msg_romfs.bin` — LayeredFS plus a rights patch and the error-message archive |
| `000400300000BA02` | Miiverse posting applet | `romfs/` + `exheader.bin` — LayeredFS plus a rights patch |
| `0004001000022A00` | System Transfer | `romfs/` — LayeredFS |
| `0004001000022B00` | Nintendo Zone | `romfs/` — LayeredFS |
| `0004001000022D00` | Face Raiders | `romfs/` — LayeredFS |
| `0004001000022E00` | AR Games | `romfs/` — LayeredFS |
| `0004001000022100` | Download Play | `code.ips` + `exheader.bin` + `dlplay_romfs.bin` — no LayeredFS, whole RomFS image off the SD card |
| `0004001000022300` | Health & Safety Information | `code.ips` + `exheader.bin` + `safe_romfs.bin` — no LayeredFS, whole RomFS image off the SD card |
| `000400300000D002` | Software Keyboard | `code.ips` + `exheader.bin` + `swkbd_romfs.bin` — no LayeredFS, whole RomFS image off the SD card |
| `000400300000C502` | Error applet | `code.ips` + `exheader.bin` + `error_romfs.bin` + `msg_romfs.bin` — no LayeredFS, whole RomFS image off the SD card plus the error-message archive |
| `000400300000F602` | 3DS Memo (`memolib`) | `code.ips` + `exheader.bin` + `memolib_romfs.bin` — no LayeredFS, whole RomFS image off the SD card |
| `000400300000CD02` | Circle Pad Pro applet (`extrapad`) | `code.ips` + `exheader.bin` + `extrapad_romfs.bin` — no LayeredFS, whole RomFS image off the SD card |
| `0004003000009902` | Camera applet (`L`+`R`) | `code.ips` + `camera_applet_romfs.bin` — no LayeredFS, whole RomFS image off the SD card; no `exheader.bin`, the title already has `DirectSdmc` |

Why some of them carry `code.ips`, and almost all of them `exheader.bin` too: see [What is in the release](#what-is-in-the-release). In short, Luma hooks the titles whose row says only `romfs/` by itself; the rest lack the rights or the code the build supplies.

Download Play, the Software Keyboard, Health & Safety Information, the error applet, the camera applet, 3DS Memo and the Circle Pad Pro applet ship no `romfs` folder on purpose — its mere presence halts those titles on an exception screen.

The eight titles that draw the date-and-clock line at the top of the screen also get a
replaced `Hud.bcfnt` (`Hud_JP.bcfnt` in some of them) next to their text: the bitmap font
that line is drawn with. It is not the system font — each such title carries its own copy,
whose Cyrillic covers the Russian weekday abbreviations and nothing else. Ukrainian `Нд`
had no letters to draw with, so the build adds `Н` and `д`; see
[The top-bar font](#the-top-bar-font).

TIDs are region-specific. The release targets **EUR**; on other regions the same folders have different names:

| Title | EUR | USA | JPN |
|---|---|---|---|
| HOME Menu | `0004003000009802` | `0004003000008F02` | `0004003000008202` |
| Friend List | `0004003000009F02` | `0004003000009602` | `0004003000008D02` |

## The Ukrainian keyboard layout

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

## The top-bar font

The date, clock and battery line at the top of the screen is **not** drawn with the shared
system font. Every title that shows it carries its own `Hud.bcfnt` in its romfs: a bitmap
font of 15x17 cells with 67 code points — digits, some Latin, six kanji, and exactly nine
Cyrillic letters, `В П С Ч б н р с т`. Precisely enough to spell `Вс Пн Вт Ср Чт Пт Сб`.

Ukrainian `Пн Вт Ср Чт Пт Сб` are covered by that set. `Нд` is not: the font has no `Н`
and no `д` at all, which is why Sunday used to render as empty brackets, `02.08 ( ) 00 25`.

The build adds the two letters. The glyphs come from `nintendo_NTLG-DB_001` — the same
typeface the rest of the font was rasterised from, and a copy of its TTF ships inside the
browser's romfs. The rasterisation parameters (size, pen, gamma, vertical placement) are
not guessed but fitted to reproduce the nine Cyrillic glyphs the font already has, as
closely as possible; see `tools/hud_glyphs.py`. The new glyphs go into free cells on the
last texture sheet, so the file grows by 12 bytes.

The letters are white with a one-pixel black outline, and that is encoded across both LA4
nibbles: **alpha is the whole silhouette, outline included; luminance is the white core
inside it**. So each letter is rasterised twice — once with a one-pixel pen for the
silhouette, once without for the core. Miss that and fill the luminance across the whole
silhouette, and the outline disappears while the letter gains a pixel on every side: on
hardware `Нд` then reads as a bolder font than the digits beside it.

Replaced in eight titles: HOME Menu, System Settings, Friend List, Notifications, Game
Notes, Browser, eShop, System Transfer. The path is `romfs/font/Hud.bcfnt` or
`Hud_JP.bcfnt` in most of them and `romfs/lang/Hud.bcfnt` in Game Notes; the file itself is
byte-identical across all eight. Nintendo Zone carries the same font but no weekday strings
of its own, so it is left alone.

## What is in the release

| Title | State |
|---|---|
| HOME Menu | ✅ translated, application names included — with a code patch, needs title version 29 (see below) |
| System Settings | ✅ translated |
| Mii Maker | ✅ translated |
| Nintendo 3DS Camera | ✅ translated |
| Nintendo 3DS Sound | ✅ translated |
| StreetPass Mii Plaza | ✅ translated, with a rights patch |
| Game Notes | ✅ translated |
| Internet Browser | ✅ translated |
| Nintendo eShop | ✅ translated, with a rights patch — needs title version 29 (see below) |
| Miiverse | ✅ translated, with a rights patch — needs title version 4 (see below) |
| Miiverse posting applet | ✅ translated, with a rights patch — needs title version 0 (see below) |
| System Transfer | ✅ translated |
| Nintendo Zone | ✅ translated |
| Face Raiders | ✅ translated |
| AR Games | ✅ translated |
| Health & Safety Information | ✅ translated, by replacing the whole RomFS — needs title version 3 (see below) |
| 3DS Memo | ✅ translated, by replacing the whole RomFS — needs title version 3 (see below) |
| Circle Pad Pro applet | ✅ translated, by replacing the whole RomFS — needs title version 4 (see below) |
| Activity Log | ✅ translated, application names included — with a code patch, needs title version 2 (see below) |
| Instruction Manual | ✅ translated, with a code patch — needs title version 5 (see below) |
| Friend List | ✅ translated, with a code patch — needs title version 6 (see below) |
| Mii Selector | ✅ translated, with a code patch — needs title version 3 (see below) |
| Notifications | ✅ translated, with a code patch — needs title version 4 (see below) |
| amiibo Settings | ✅ translated, with a code patch — needs title version 1 (see below) |
| eShop applet | ✅ translated, with a code patch — needs title version 22 (see below) |
| Error applet | ✅ translated, by replacing its whole RomFS — needs title version 7 (see below) |
| Download Play | ✅ translated, by replacing its whole RomFS — needs title version 3 (see below) |
| Software Keyboard | ✅ translated, by replacing its whole RomFS — needs title version 4 (see below) |
| Camera applet (`L`+`R`) | ✅ translated, by replacing its whole RomFS — needs title version 2 (see below) |

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

## Why these titles

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
| Miiverse | `0x0000000000000001` | **no**, but it has `fsMountArchive` |
| Miiverse posting applet | `0x0000000000000000` | **no**, but it has `fsMountArchive` |
| Software Keyboard | `0x0000000000000001` | **no** |
| Activity Log | `0x0000000000000001` | **no** |
| Download Play | `0x0000000000000001` | **no** |
| Instruction Manual | `0x0000000000000001` | **no** |
| Friend List | `0x0000000000000001` | **no** |
| Mii Selector | `0x0000000000000001` | **no** |
| Notifications | `0x0000000000000001` | **no** |
| amiibo Settings | `0x0000000000000001` | **no** |
| eShop applet | `0x0000000000000001` | **no** |
| Error applet | `0x0000000000000001` | **no** |
| Health & Safety Information | `0x0000000000000001` | **no** |

Titles without `DirectSdmc` have no access to the SD card, so Nintendo never linked any
SD-mounting code into them. The titles that work are the ones that hold that right.

StreetPass Mii Plaza, Nintendo eShop, Miiverse and the Miiverse posting applet are the
exception on both counts: they have no `DirectSdmc` right, yet they do have
`fsMountArchive` (the Plaza mounts its own extdata, the others their own storage). Luma
finds all five symbols and patches the title unaided, so no `code.ips` is needed — but the
payload it writes still reads its files off the SD card. So those folders carry an
`exheader.bin` with the `DirectSdmc` bit set and nothing else: no offsets, and therefore
nothing tied to a particular build beyond the title-version check.

The eShop went without that `exheader.bin` for a long time, and its translation was simply
never applied because of it: the romfs was in the folder, but the payload had nothing to
open `ARCHIVE_SDMC` with. Its `accessInfo` is `0x240001` — `CategorySysApplication`, `Shop`
and `SeedDB`, and not one bit of SD access.

How far that pruning went shows in the set of IPC commands each title can even issue:

| Title | `OpenArchive` | `OpenFile` | `CloseArchive` | `OpenFileDirectly` |
|---|---|---|---|---|
| Activity Log, Instruction Manual, Friend List, Mii Selector, Notifications, amiibo Settings, eShop applet | ✅ | ✅ | ✅ | ✅ |
| Download Play, Software Keyboard, Health & Safety, 3DS Memo, Circle Pad Pro applet | ❌ | ❌ | ❌ | ✅ |
| Error applet | ✅ | ❌ | ❌ | ✅ |

The last two can do exactly one thing: open a file directly and read it. They need a
different approach.

## How the Activity Log, the Instruction Manual, the Friend List, the Mii Selector, Notifications and amiibo Settings were fixed

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
| eShop applet | over `throwFatalError()`: the `.text` padding is 1880 bytes, so Luma takes the padding again. |

The stub comes in three variants, chosen by the register and stack frame the mount tail it
jumps into expects: `r4` on a 0x28 frame (Activity Log), `sl` on a 0x14 frame with the
result in `r8` (Instruction Manual, Friend List, eShop applet), or `r4` on a 0x18 frame (Mii Selector, Notifications, amiibo Settings).
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
| **HOME Menu (`menu`)** | **29** |
| **Friend List (`friend`)** | **6** |
| **Instruction Manual (`ebird`)** | **5** |
| **Software Keyboard (`swkbd`)** | **4** |
| **Download Play (`dlplay`)** | **3** |
| **Health & Safety (`safe`)** | **3** |
| **Mii Selector (`appletEd`)** | **3** |
| **Error applet (`error`)** | **7** |
| **Notifications (`newslist`)** | **4** |
| **amiibo Settings (`Cabinet`)** | **1** |
| **eShop applet (`mint`)** | **22** |
| **StreetPass Mii Plaza (`MEET`)** | **5** |
| **Nintendo eShop** | **29** |
| **Miiverse (`cave`)** | **4** |
| **Miiverse posting applet** | **0** |
| **Camera applet (`L`+`R`)** | **2** |
| **3DS Memo (`memolib`)** | **3** |
| **Circle Pad Pro applet (`extrapad`)** | **4** |
| Mii Maker (`EDIT`) | 2 |
| **Activity Log (`PLOG`)** | **2** |

These titles were updated a handful of times in the console's lifetime, so their builds are
what sits on every modern firmware, including the final `11.17.0-50` (May 2023, the last 3DS
update ever — and it touched none of them). In practice the patch fits almost everyone.

The build checks both `remaster_version` and the dump's sha256 and refuses to run on a
mismatch. That does not protect an end user, so the archive carries a note: if one of those
titles crashes, its build is older and its folder under `luma/titles/` should be deleted.

## How the error bodies were translated

What is written under "Error Code: XXX-YYYY" does not belong to the title showing it. The
error applet owns exactly fourteen strings - the frame, "OK", and the two empty
`short_error` / `long_error` slots it fills at run time. The messages themselves live in the
**shared data archive** `0x0004009B00012102`, the same class of title as the system font and
`area`, dumped from CTRNAND just like them (`docs/dumping.md`).

Inside is one MSBT per error module and language, and **every message's label is the error
number**: the body of `009-1003` is label `91003` in `EU_Russian/90000_msbt_LZ.bin`, the body
of `015-5004` is `155004` in `150000_msbt_LZ.bin`. 13 files, 259 messages in total.

Two titles read the archive. Both mount it as `msg:` and pick the file from a seven-entry
table indexed by console region (`12202 12302 12102 12102 12402 12502 12602`, so EUR is
`12102`):

| Title | What it shows |
|---|---|
| Error applet `000400300000C502` | every application's errors - eShop, the Plaza, updates, the SD Card |
| Miiverse `000400300000BE02` | its own, because it draws its error screen itself |

LayeredFS cannot reach it, and not for the same reason `area:` could not. The read goes
through `FSUSER_OpenFileDirectly` with `ARCHIVE_SAVEDATA_AND_CONTENT` and a **binary** path
carrying the archive's title id - while Luma's payload looks for textual mount-name prefixes
(`rom:`, `rex:`…) in the path. A binary path has none and can have none.

It is, however, exactly the situation the HOME Menu banner hook already exists for. The patch
replaces the instruction that loads the archive id (`ldr r3, =0x2345678A`) with a branch into
a stub that:

```
ldr ip, =table            table of {title id, path, length}
ldr r3, [ip]              zero title id ends the walk -> pass-through
ldr r1, [sp, #0x60]       the frame already holds the title id being read
cmpeq …[sp, #0x64]        both words
  match -> ASCII path into sp+0x10, empty archive path into sp+0x00, r3 = 9 (SDMC)
  pass  -> ldr r3, =0x2345678A, exactly as before
b   back
```

The comparison is not optional: the EULA archive (`0x0004009B00013102`) is read through the
same call and has to keep behaving as Nintendo wrote it.

The stubs (140 bytes) go into the `.text` padding - in the error applet behind its two romfs
redirect stubs, in Miiverse behind the 0x114 bytes Luma claims for its own payload. The path
strings go into the `.rodata` padding, in Miiverse behind the 48 bytes Luma claims there.

The translated archive is rebuilt into a RomFS image (`tools/romfs.py`) and shipped in **each
reader's folder** - `luma/titles/000400300000C502/msg_romfs.bin` and
`luma/titles/000400300000BE02/msg_romfs.bin`, 206 KB each. 13 of its 117 files differ; every
other language stays untouched, so switching the console language back still undoes the mod.

The archive needs no `exheader.bin` - it is data, not a process, and nothing about it is tied
to a build. The version and hash checks are on its two readers.

## How Download Play was fixed

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

### The camera applet: the one Thumb title

The camera applet — the one the HOME Menu opens on `L`+`R` — is built in Thumb, and that
decides everything else about it.

LayeredFS is impossible for it in principle. The five signatures `findLayeredFsSymbols()`
looks for are ARM instruction words, so they will never match Thumb code. Planting ARM stubs
would not be enough either: Luma patches the title's **own** `fsRegisterArchive` and
`fsTryOpenFile` so that the title's own file opens land on the SD card, and here those are
Thumb functions at other addresses. So this title goes the Download Play way.

Finding its FS wrappers took a different route as well. The IPC header is not a literal
here: the wrappers compose it at run time from (command id, normal and translate parameter
counts) held in registers, so there is no `0x08030204` or `0x080C00C2` anywhere in `.code`.
They were found by walking the callers of `svcSendSyncRequest` — the ARM leaf
`svc 0x32 ; bx lr` at `0x7EE1C`.

Both RomFS readers reach `FSUSER_OpenFileDirectly` at `0x7F068`: the one behind `rom:` calls
it at `0x2048`, the second reader at `0xCF08`. Nothing else in the title touches the RomFS —
its three `FSUSER_OpenArchive` calls use archives 7 and 8 plus one generic wrapper, and its
single `FSUSER_OpenFile` is unrelated.

The caller frame lays the arguments out exactly like the ARM titles: file path type at
`sp+0xC`, pointer at `sp+0x10`, size at `sp+0x14`, and the archive path is already the empty
one built by `MakeEmptyPath()` at `0x7F0F8` — which is what `ARCHIVE_SDMC` wants too.

Only the way into the stub differs. The ARM titles give up one word, `mov r3, #3`, to the
branch; 16 bits are not enough for one in Thumb, so the pair of instructions right before
the call — `str r5, [sp, #0x14] ; str r4, [sp, #0x1c]` — becomes a `bl` into a shared stub.
That stub (24 bytes inside the 1552 bytes of `.text` padding at `0xCB9F0`) sets the ASCII
path, repeats the displaced `str r4, [sp, #0x1c]`, puts 9 in `r3` instead of 3 and returns
with `bx lr`. The `bl` clobbers `lr`, which is safe: the next instruction at both sites is
the `bl` into the wrapper, which overwrites it anyway.

This title ships no `exheader.bin`: its `accessInfo` is `0xa1`, so `DirectSdmc` is already
there and the replacement would be byte-identical to the one in NAND.

## How the HOME Menu's application names were translated

This is the one `code.ips` in the mod that is **not** there to make LayeredFS work — Luma
hooks the HOME Menu unaided. It is there because the application names do not live in romfs.

The HOME Menu reads them from each title's SMDH, `ExeFS:/icon`, which LayeredFS cannot
reach. The **readers**, however, belong to the HOME Menu, and they can be intercepted. There
are **two** of them:

| What | Where | When it runs |
|---|---|---|
| `ReadTitleIcon()` — pulls all `0x36C0` bytes of an SMDH out of `ExeFS:/icon` | `0xEA40`, via the thunk at `0x131E60` (18 callers) | when the HOME Menu fills its icon cache |
| `CacheRead()` — reads the same `0x36C0` bytes out of that cache | `0x147D64` | **on every ordinary boot** |

The icon cache is `Cache.dat` in the HOME Menu's extdata **on the SD card** (EUR:
`Nintendo 3DS/<id0>/<id1>/extdata/00000000/00000098`). `CacheRead()` looks the title up in a
table of 16-byte records (up to 360: an 8-byte id, then a u32 and a mediatype byte), reads
the file at `index * 0x36C0` and hands back the **whole** SMDH, all 16 language slots
included. That is why switching the console language relabels everything without the cache
being rebuilt.

And it is why hooking only `ReadTitleIcon()` changes nothing on a console whose cache was
built before the mod was installed: after the first fill, that read simply never happens.
Both are hooked, and both hand the buffer to the same routine.

Nothing is written back to the cache — the file on the SD card stays as Nintendo left it, so
removing the mod restores the original names with no rebuild.

Between them these paths cover every screen that shows a name: the icon label, the upper
screen on highlight, the "software suspended" overlay, the close and delete prompts.

Do not look for the read site by the string `icon`: the `ExeFS:/icon` path is passed as the
4-byte **literal** `'icon'` (`0x6E6F6369`) in a binary lowpath, and the reliable marker for
the function itself is `mov r1, #0x36c0`, the size of an SMDH.

The thunk's arguments: `r0` = buffer, `r1` = mediatype, `r2`/`r3` = title id. Confirmed at
two call sites — `0x120ABC` (`ldrd r2, r3, [r4, #8]`, `ldrb r1, [r4, #0x10]`) and `0xBB5EC`
(`mov r1, #1`, i.e. NAND). Success is a zero return; failures come back as `0xC8804631`,
`0xC8804632` or the raw negative result.

`code.ips` lays down three records:

| Record | Where | Size |
|---|---|---|
| `b icon_hook` over the thunk's `push {r3, lr}` | `0x131E60` | 4 bytes |
| `b cache_hook` over `CacheRead()`'s prologue | `0x147D64` | 4 bytes |
| the blob: both hooks, a trampoline and the rewrite routine they share | end of the `.text` padding, `0x205EF4` | 268 bytes |
| the name table | `.rodata` padding, va `0x3295E4` | 1318 bytes |

`cache_hook` cannot simply jump into `CacheRead()`'s body: its epilogue pops `pc` off the
`lr` that the replaced prologue saved. So the prologue is reproduced in a trampoline, and a
`bl` to it hands control back to the hook.

Both locations are chosen to stay clear of Luma itself, which applies its LayeredFS patch
**after** the IPS and silently overwrites whatever was there:

| What Luma writes | Where | Size |
|---|---|---|
| the LayeredFS payload | **front** of the `.text` padding (`*payloadOffset = size`) | `0x114` |
| the string `lf:/luma/titles/<TID>/romfs` | **front** of the `.rodata` padding (`*pathOffset = roundedTextSize + roSize`) | 39 bytes |

So the stub goes at the **end** of the `.text` padding (2336 bytes still free after it), and
the table starts 48 bytes into the `.rodata` padding. The first version of this patch missed
that: the table began exactly at `pathOffset`, Luma overwrote its first entry, the walk ran
off into garbage — and the names stayed Russian, with no crash to point at it.

The stub reproduces the thunk's three instructions verbatim, because the reader takes a
fifth argument off the caller's stack and expects `ip` to be zero. Only slot 10 (Russian) is
touched, its short and long description; the publisher, the icon bitmaps and the other 15
languages are left alone. A failed read and an unknown title id leave the buffer as it was.

The strings live in `src/strings/home_menu/_app_names.json` alongside the other
translations and go through the same homoglyph substitution. The convention is taken from
Nintendo's own SMDHs: `ua` is the short description, one line; `ua_long` is the same name
carrying its own `\n`, and it may be omitted when the two are identical. The table format is
in `tools/smdh_names.py`.

Both hooks are verified by ARM emulation (unicorn), and the harness reproduces what Luma
writes on top afterwards — without that it passed on a broken patch. It checks: correct names
for three different titles down both paths, `r0`/`sp`/`r4-r7` intact on the way out, other
language slots and the icon bitmaps byte-for-byte, an unknown title id and a failed read
leaving the buffer alone, and `ReadTitleIcon()` receiving `arg5 = 0` and `ip = 0`.

## How the Activity Log's application names were translated

The Activity Log could not be fixed the same way: it never reads an SMDH at all. It has no
`am:*` and no `ns:s`, its single `ARCHIVE_SAVEDATA_AND_CONTENT` open leads to
`0x0004009B00010202` — the shared system font — and the `icon` in its code is a layout pane
name (`soft_record_top_icon`), not a file. Names reach it as finished strings.

What it does have is a function every string passes through. The most visible path to it
looks like this:

```
add r0, pc, #...     ; the MSBT label
bl  0x17D654         ; GetMessage(label) -> u16*
mov r1, r0           ; the text
add r2, pc, #...     ; the pane name
bl  0x17CE04         ; SetPaneText(layout, text, pane, ...)   72 callers
```

The hook, however, sits one level below that: `0x7BC28`, which 8 sites in three functions
reach, `SetPaneText` being only one of them. That is not a cosmetic difference — the software
card sets its panes through **another** of the three, so a hook on `SetPaneText` translated
the ratings list and left the card in Russian.

The name goes through that same setter, only its text does not come from an MSBT. So this
hook is a different animal from the HOME Menu's: it **writes to nobody's buffer**. It
compares the string against a table and swaps the **pointer** in `r1` for a string of ours.
The original is left untouched.

There are two shapes of match, because the same string arrives both on its own and with a
second line appended:

| What arrives | What the hook does |
|---|---|
| `Журнал действий` | `r1` points at our string, nothing is copied |
| `Журнал действий\nNintendo` | composes our string and the tail into a buffer of its own — the software card draws the name and the publisher as one string |

A partial match is not a match: the candidate has to end, or break the line, exactly where
the original does. The whole interface goes through this function, so anything looser would
corrupt unrelated strings.

There is one deliberate relaxation: **a space in the table also matches a line break**.
Nintendo breaks the long names itself — `AR Games:\nРасширенная реальность` — and where it
breaks them is not visible from outside. So the originals are written on one line and the
comparison tolerates a break wherever a space is. The length and the ending still have to
match exactly.

| Record | Where | Size |
|---|---|---|
| `b pane_hook` over the setter's prologue | `0x7BC28` | 4 bytes |
| the hook | end of the `.text` padding, `0xE0F24` | 220 bytes |
| the table, Russian name to Ukrainian | `.rodata` padding, va `0x1F1874` | 1632 bytes |
| the buffer it composes into | `.data` padding, va `0x200B18` | 512 bytes |

There is no return to arrange: the hook finishes comparing, replays the prologue it replaced
and jumps to `0x7BC28+4`. The function returns to its own caller as it always did.

The cost of the approach is that it keys on the **Russian** names. If Nintendo spelled one
differently from our table, the swap simply does not happen — no harm done, but no
translation either. That is why `src/app_names.json` carries a `ru` field next to `ua`, and
it has to match what the console displays byte for byte.

## How the country and region lists were translated

The longest road in the mod. Profile settings → Region Settings shows names that exist
**nowhere** in System Settings' romfs: the `.code` holds the paths `area:/EU/country_LZ.bin`
and `area:/EU/<code>_LZ.bin`, and `area:` is a separate **shared system data archive**,
`0x0004009B00010402` — the same class of title as the system font, and dumped from CTRNAND
the same way (`docs/dumping.en.md`).

LayeredFS does not reach it: Luma redirects the title's own romfs and only its own mount
points (`rom:`, `ro2:`, `rex:`…), and `area:` is not one of them. But the title already
carries everything needed:

```
000BEE8  bl 0x1C7C6C     MountByTitleId("area:", 0x00010402, 0x0004009B, ...)
000BEF4  ldr r0, =0x297900        the path table, one entry per console region
000BEFC  ldr r0, [r0, r1, lsl #2] "area:/EU/country_LZ.bin"
000BF04  bl 0x1C7BB4              read the whole file
000BF10  bl 0x1C7A54              Unmount("area:")

00A1654  MountSdmc(const char *name)    mov r1, #9 (ARCHIVE_SDMC); OpenArchive; register
```

`MountSdmc` takes the mount name as its **only argument, in `r0`** — and `r0` at both sites
already points at `"area:"`. So the whole patch is **two `bl` instructions** retargeted from
`MountByTitleId` to `MountSdmc`, after which `area:/…` resolves against the SD card, plus 14
pointers in `.data` moved to strings reading
`area:/luma/titles/0004001000022000/area/<region>/…` in the `.rodata` padding. No stub and no
exheader: this title already has `DirectSdmc`. The tid loads into `r2`/`r3` become dead code,
`MountSdmc` never reads the stack arguments, and the unmount is the same call either way.

The paths are repointed for **all six regions**, not just EU: the mount is unconditional, so a
console reporting another region has to find its files on the card too. That is why the mod
ships the whole dumped archive — 129 files, 564 KB, two of them changed.

### Why Russia becomes Ukraine instead of getting its own row

Nintendo's country code table has **no Ukraine at all**. The European block 64–127 is gapless:
`…96 Norway, 97 Poland, 98 Portugal, 99 Romania, 100 Russia, 101 Serbia & Kosovo…`. A country
code is a system-wide value that NNID, the eShop, StreetPass and the age ratings all depend on;
adding a row would mean rewriting a table half the system reads. So code **100 is taken over
exactly the way the language slot is**: the Russian slot reads «Україна» instead of «Россия»,
and the other 66 names are translated.

### The format, and the sorting

Both files are LZ11 and both are tables of **fixed-size** records, which is what lets a
translation be written in place: a name is a 128-byte UTF-16LE slot, and the 16 slots follow the
system's language order, where slot 10 is Russian — the same "block 10" as in an SMDH.

The important part is the **sort row**. Byte `j` of it is the record's position in language
`j`'s alphabetically sorted list, while the records themselves sit in Japanese order. Translate
the names without recomputing rank 10 and the Ukrainian list comes out ordered by the Russian
alphabet: «Австралія, Австрія, Азербайджан, Албанія» survives that, «Україна» in the middle of
the list does not. Every row exists twice, once in the record and once in a table at the end of
the file, and `tools/area.py` writes both. The model is checked against all 129 files of the
dump: recomputing the English and Russian columns reproduces what Nintendo wrote, byte for byte,
except in 17 files that follow a local order (Norwegian `Ø` after `Z`, Turkish `ı` before `i`,
the Asian lists ordered by prefecture code) — none of which the mod touches.

Code 100's region list is not translated but **replaced**: Russia has 83 regions, Ukraine has
27. Since every section is fixed-size, the file is re-emitted smaller (`area.resize()`) and the
country record's own count comes down with it. The Ukrainian names go into the Russian slot and
a transliteration into every other one: leaving Russian oblasts behind a row that now reads
«Україна» would be worse than a name no EUR console ever displays.

**Side effect:** switch the console to English and the row still reads `Russia`, but the 27
regions under it are Ukrainian. The mod only replaces its own slot, and here that boundary shows.

### The StreetPass Map

The StreetPass Map in Mii Plaza shows the same names and keeps its own tables for them,
`0004001000022800/romfs/param/country.csv` and `region.csv`. UTF-16 with a BOM, CRLF, one
column per language (Russian is 11), and rows of different lengths - the Japanese ones have no
Korean or Chinese columns at all. Plus a trailing comma before each line break, which a normal
CSV writer would turn into `""` and rewrite every line. So `tools/csvtab.py` **never
re-serialises a row it was not asked to change**: it splits on `","`, swaps the one field and
joins it back, leaving every other byte alone - an untouched file rebuilds byte for byte.

Rows are keyed `<country code>:<address id>`, and that id is the same one the `area` archive
numbers its regions with, so the two tables cannot drift apart. Code 100's block is likewise
rebuilt rather than translated: the 83 Russian rows go and 27 Ukrainian ones take ids 2..28 -
the same ids, in the same order, as the region file. In total **121 countries and 1314 regions**
translated, 27 rows rebuilt.

## What the mod does not translate

**Application names outside the HOME Menu.** The label under an icon, the text on the upper screen when you highlight it, the "software suspended" overlay, the close and delete prompts — all of it is the same short/long description from the title's **SMDH** (`CXI ExeFS:/icon`, 16 language structs). LayeredFS cannot reach ExeFS: Luma only redirects `romfs/`, `code.bin`, `code.ips`, `exheader.bin` and `locale.txt`, and an installed title's SMDH lives in NAND.

In the HOME Menu and the Activity Log this is worked around with a code patch — see the two sections above — so their screens are translated. But **Data Management, the eShop, System Transfer and Game Notes still show the names in the slot's language**: each reads them separately and needs a hook of its own.

Two titles carry a second copy of their SMDH inside their own `romfs`, and **LayeredFS does reach that one** with no code patch involved:

| File | Was | Now |
|---|---|---|
| `0004001000022700/romfs/icn/EU_appEdit.icn` | `Редактор Mii` | `Mii Maker` |
| `0004001000022B00/romfs/saveicon_EU.icn` | `Программа просмотра Nintendo Zone` | `Оглядач Nintendo Zone` |

Only the Russian slot (index 10) is touched — its short and long description, 40 and 82 bytes respectively. The icon bitmaps and the other 15 languages stay byte-for-byte identical: see `tools/smdh.py` and `build_smdh()`. The eShop and Face Raiders copies exist too, but their names are already in Latin script.

**The system font.** It has no Ukrainian letters, and LayeredFS cannot replace it: it lives in a separate system title the mod does not touch.

**Real Ukrainian letters from the keyboard.** The layout is Ukrainian (see [The Ukrainian keyboard layout](#the-ukrainian-keyboard-layout)), but the `і ї є` keys type `i ï ε` — the same substitute glyphs the rest of the mod uses. On the console that reads correctly and consistently; outside it — in a Mii name, a folder name, a post — it is Latin and Greek, not Ukrainian text. There is no way around it: real letters need a different font, which means modifying NAND.

**The text inside electronic manuals.** The Instruction Manual application itself is translated — `Back`, `Enlarge`, `Language`, `Page`, `Contents`, the language dialog. The documents it displays can be translated too now, but one at a time, and each has to be dumped off the console first. 0.10.0 ships two in full - the Internet Browser and System Settings; every other title shows the console's own manual.

That document does not belong to the Instruction Manual. Every title ships its own electronic manual as a separate NCCH — content index 1 within that same title. The Instruction Manual reaches it through `ARCHIVE_SAVEDATA_AND_CONTENT`, reading the documented title's content directly.

LayeredFS does not lead there. Luma's payload only intercepts mounts for `ARCHIVE_ROMFS` and only rewrites paths starting with `rom:` or the detected update mount — and of the ones Luma knows (`ro2:`, `rom2:`, `rex:`, `patch:`, `ext:`) the Instruction Manual's code contains none, only its own `rom:`. Luma has no mechanism for replacing content index 1 of a title.

It is also not one document but one per title: the Activity Log has its own, System Settings has its own, every game has its own. Translating them means rebuilding and reinstalling each title's content.

**How it is worked around.** The LayeredFS payload hooks `fsOpenFileDirectly` and `fsTryOpenFile` and looks at the path's **mount prefix**: `rom:`, plus the one "update" mount `loader` finds in the title's `.text` out of `ro2: rom2: rex: patch: ext:`. The viewer mounts the documented title's content as `man:`, a prefix Luma does not know, so nothing was redirected at first — confirmed on the console: both the HOME Menu button and the browser's own manual button showed Russian.

The patch renames the mount to `rex:` — the same four bytes, in place, in all three copies of the string. That is enough for Luma to substitute a file, but only one file for the whole console: the path in the code is constant, and Luma fills in the folder of the **process** (the viewer), not of the documented title.

So the path is built at runtime. The string `rex:/Manual.bcma` has **two** users, and that is this patch's trap:

```
148280  bl   0x147F58            mount, and open the file once to check it is there
148290  beq  0x1482A4            gone -> give up
148294  sub  r1, pc, #200        -> the same string in .text
14829C  bl   0x14797C            load the document
```

The first version of the patch rewrote that string and fixed up only the first user — and **every** manual on the console, translated or not, showed the loading screen and dropped back to the HOME Menu with no crash at all. The cross-reference scan that missed it looked for `add rX, pc, #imm` and did not know about the `sub` form.

Both sites now call one fifteen-word routine, which took the place of the converter loop:

```
1480D8  bl   builder             site 1: r1 = the path, then the same widening loop as before
1480F0  builder: ldr r3, =globals    the documented title's id, read where the mount reads it
1480FC           ldr r0, [r0]        its low word
148100           ldr r2, =table      a {title id, path} table in the .rodata padding
148104           ldr r1, [r2], #8 …  walk it
148118           ldr r1, [r2, #-4]   that title's path
148120           add r1, pc, #172    not in the table -> the constant, still in .text
148294  bl   builder             site 2: the same
```

The string itself is left alone, because it *is* the fallback. A title this build ships no file for asks for `Manual.bcma`, Luma finds no such file on the SD card and repeats the call with the original arguments: the console's own manual appears, exactly as before the mod. Nothing is written at runtime — the table and the paths are read-only data in the same `.rodata` padding that already carries the country-list paths.

Verified on hardware: the Browser and System Settings in Ukrainian, the Activity Log and a cartridge game with their own. See `manual_path` in `tools/luma_hook.py`.

That also means a manual need not live in its title's romfs. The Browser is the only title that carries its own there (`manual/Manual.bcma`) and keeps it; every other one is dumped out of content index 1 into `work/<TID>/manual/Manual.bcma` (see `docs/dumping.md`). `make extract-manuals` pulls the text into `src/manuals/<name>.json`, `make manuals` builds them all back into `dist`.

The format: `Manual.bcma` is an uncompressed DARC of LZ10-compressed DARCs (`BcmaInfo.arc`, `EUR_<lang>_{index,large,small,texture}.arc`) whose pages are BCLYT. The text is not stored as text: **every rendered line is its own `txt1` pane at its own coordinates**, a highlighted word is a second pane on the same `y`, and a button icon is a picture pane between them. Nothing wraps at runtime.

So `tools/manual.py` does the reflow itself. It groups the panes back into a paragraph, hands the translator one string with markers (`{i0}` an icon, `{s1|…}` a highlighted run, `{br}` a deliberate break), and on build re-wraps that string and moves every pane of the paragraph to where the new line breaks put it. The limits are checked rather than assumed: a paragraph may not outgrow the lines it occupies (the paragraph below it does not move), it may not use more highlighted runs than the page has panes in that colour, and a line is measured against the widest line the same paragraph has in any of the eight official localisations. Self-check: feeding the Russian original back in as the translation lays all 277 paragraphs out with no complaint, and the rebuild keeps every word.

Line width is `sum of glyph advances × fontSize / 24 + charSpace`. The 24 is the font's em, recovered from Nintendo's own coordinates (330 neighbouring panes: mean error 2px, p95 5px) — and it is that error the 10px of budget slack pays for.

**The language picker.** The viewer takes the language names not from MSBT but from the document's own `BcmaInfo.bclyt`: one text pane per localisation, named after it (`EUR_en` … `EUR_ru`), each holding the language written in itself. The slot the mod overwrites is the Russian one, so `tools/manual.py` sets the `EUR_ru` pane to **Українська** on build. The pane is 200px, the name draws at 135, and no coordinate moves.

**The title above the page.** The line across the top of every page is the short description from the **documented** title's SMDH (`ExeFS:/icon` in NAND), which `ebird` reads itself — out of LayeredFS's reach, exactly as in the HOME Menu. The fix is the same: hook the read. What differs is that there is one reader and no cache of any kind — the call at `0x115E84` hands over the buffer, the title id and the mediatype, and right after it the wrapper rewrites the SMDH's Russian slot from the same name table the HOME Menu uses (`smdh_names.py`), cut down to the titles this build ships a manual for. A title not in the table is left as it was.

Where the wrapper goes is its own problem: the `.text` padding here is 88 bytes with 84 already taken by the mount stub, and Luma claims `throwFatalError()` for its own payload. So the 216 bytes of wrapper go over the dead function at `0x12C6E8` — a second copy of the icon-tile copier that is also inlined at `0x115F04` and that nothing in the image reaches: no `bl`, no `b`, no absolute pointer in `.text`, `.rodata` or `.data`, and the title's one computed jump (`0x18FC90`) branches inside its own table. Those 636 bytes are pinned by a sha256 in `tools/luma_hook.py`, so a different build of the title fails the mod's build instead of the console.

**Nintendo DS Connection Settings.** The button in the internet settings launches `0004800542383841` — a separate **TWL** title (the only TWL TID in System Settings' `.code`). It runs under TWL_FIRM, where Luma's LayeredFS does not work at all. Besides, the DS/DSi language set has no Russian (JP/EN/FR/DE/IT/ES, later ZH/KO), so there is no slot to replace — the app opens in English whatever the console language.

All of these limits come down to the same thing: they require modifying NAND. A "Tier 2" release for people who accept that — with a NAND backup and the appropriate warnings — is a separate thing and is not part of this release.

## Building from source

No Nintendo files are included in this repository. You need a romfs dump from **your own**
console — see [Dumping from your own console](dumping.en.md) for how to take one.

```bash
make font extract validate build package
```

Python 3.11+, no dependencies. Tools: LZ11 (de)compressor, MSBT parser/builder with byte-exact round-trip, BCFNT reader/builder (also byte-exact) that can add glyphs to a font, extractor, validator, builder, width fitter, packager.

One tool sits outside the build: `tools/hud_glyphs.py` draws the `Н` and `д` added to the top-bar font and needs Pillow, so its output is committed as `assets/hud_glyphs.json`. Redraw it with `make hud-font`.

## Contributing translations

Edit the `ua` fields in `src/strings/<app>/*.json` (`en` holds the original). For terminology and style see the [glossary](../src/glossary.en.md): one term, one translation. Run `make validate` before opening a PR — it rejects glyphs missing from the font, strings wider or taller than the UI can fit, and invented control tags. Width/height budgets are derived from all 8 official localisations of the title.
