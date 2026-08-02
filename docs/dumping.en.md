# Dumping from your own console

*[Українською](dumping.md)*

This repository contains no Nintendo files at all. To build the mod yourself — or to add a new
title to it — you need dumps from **your own console**. GodMode9 takes them.

If you only want to install the released archive, you don't need any of this: the installation
instructions are in the [README](../README.md).

---

## Before you start

- GodMode9 installed: `SD:/luma/payloads/GodMode9.firm` and the `SD:/gm9/` folder
- Luma's `Enable game patching` is `(x)`
- at least 2 GB free on the SD card (the NAND backup is about 1 GB)

GodMode9 keys: `A` select or enter, `B` back, `Y` copy or paste, `X` delete, `SELECT` clear the
clipboard, `R`+`A` file actions menu, `HOME` main menu, `START` reboot, `R`+`L` screenshot.

To launch it: power the console off → hold `START` → power on → pick `GodMode9`.

## 1. NAND backup — mandatory, once

1. `HOME` → `Scripts` → `GM9Megascript` → `Backup Options` → `SysNAND Backup` → `A`.
2. Wait 10–20 minutes. Result: `0:/gm9/out/<date>_sysnand_???.bin` and a `.sha` next to it.
3. Copy both files off the SD card onto your computer.

⚠️ The NAND backup contains your console's unique keys (OTP, `movable.sed`). **Never publish it
and never commit it to git.** Don't keep the only copy on the SD card either — this backup is
what saves the console if anything goes wrong.

## 2. Dumping a title's romfs

`romfs` is where the translatable text lives.

Example for the HOME Menu (EUR `0004003000009802`; USA `0004003000008F02`, JPN `0004003000008202`):

1. `[1:] SYSNAND CTRNAND` → `title` → `00040030` → `00009802` → `content`
2. Take the **largest `.app`** — that is the current version of the title. Smaller ones are old.
3. `A` → `NCCH image options...` → `Mount image to drive`
4. The mounted image shows `romfs/`, `exefs/`, `exheader.bin`
5. Put the cursor on **`romfs`**, do not enter it → `Y` to copy
6. `B` back to the drive list → `[0:] SDCARD` → `gm9` → `out`
7. **Create a folder named after the title:** `R`+`A` on empty space → `New folder` → type
   `0004003000009802` → `A`
8. Enter it → `Y` to paste, wait for the copy to finish
9. `B` back to `[1:] SYSNAND CTRNAND` and repeat from step 1 for the next title

**Don't skip step 7.** Pasting everything straight into `gm9/out` gets you `romfs`, `romfs2`,
`romfs3` — and no way to tell which is which afterwards.

⚠️ Applications live under `00040010`, applets under `00040030`. The keyboard, the Instruction
Manual, the Friend List and the HOME Menu are applets; System Settings, the Camera and the
Activity Log are applications.

## 3. Dumping `code` + `exheader` — the LayeredFS pre-flight check

`tools/layeredfs_check.py` needs these to predict whether Luma can hook LayeredFS into a title.
This is not a formality: if you place a `romfs` folder for a title Luma cannot hook, **every
launch of that title turns into an exception screen**.

1. Mount the title's `.app` as in step 2.
2. Cursor on the `.app` → `A` → `NCCH image options...` → **`Extract .code`**. GodMode9
   decompresses the BLZ itself and writes the file to `0:/gm9/out/`.

   Use `Extract .code` rather than copying `exefs/.code` by hand: a hand-copied file may still
   be compressed, and then none of the function signatures will be found in it.
3. In the mounted image, copy **`exthdr.bin`** to `0:/gm9/out/`.
4. Place both files next to the romfs dump:

   ```
   work/0004003000009802/code.bin
   work/0004003000009802/exthdr.bin
   ```

   The names are not fixed — the checker accepts `code.bin`, `*.code`, `code.dec.bin` and
   `exheader.bin`, `exthdr.bin`, `*.exthdr`. Only the `work/<TID>/` folder matters.

⚠️ The files come out with the same name (`exthdr.bin`) for every title. Either rename them in
GodMode9 right away (`R`+`A` → `Rename file`), or move them to your computer after each title.

### Validating the checker itself

Start with two control titles whose behaviour on hardware is known:

```bash
python3 tools/layeredfs_check.py work/0004003000009802   # expected: LayeredFS OK
python3 tools/layeredfs_check.py work/000400300000D002   # expected: LOADER WOULD CRASH
```

The HOME Menu works on a console; the keyboard crashes on its own. If the checker matches on
both, you can trust it for the rest. With no arguments it walks every folder in `work/`:

```
=== 0004001000022200
  code.bin + exthdr.bin: 1234560 bytes (already decompressed), text 987654, ro 12345, data 6789
    fsMountArchive       0x0012A4
    fsRegisterArchive    NOT FOUND
    fsTryOpenFile        0x0031C8
    fsOpenFileDirectly   0x004A10
    fsUnmountArchive     0x005C88
    payload space        ok
    path string space    ok   (payload via .text padding, path via .rodata padding)
  -> LOADER WOULD CRASH - mark blocked
```

The `NOT FOUND` line shows exactly which condition failed.

If the checker disagrees with reality, please [open an Issue](../../../issues) with its output and
with what the console actually does. A tool that is wrong is worse than no tool.

## 4. Dumping the system font

Needed for the glyph and width tables; `make validate` does not work without it.

1. `[1:] SYSNAND CTRNAND` → `title` → `0004009b` → `00014002` → `content` → largest `.app`
2. `A` → `NCCH image options...` → `Mount image to drive` → copy `romfs` to `0:/gm9/out`
3. On the computer, place the file as `work/0004009B00014002/cbf_std.bcfnt.lz`

## 4a. Dumping the `area` archive (country and region names)

Needed for the country list in Profile settings; without it `build.py` refuses to build
System Settings. Same three steps as the font, on a different title:

1. `[1:] SYSNAND CTRNAND` -> `title` -> `0004009b` -> `00010402` -> `content` -> largest `.app`
2. `A` -> `NCCH image options...` -> `Mount image to drive` -> copy `romfs` to `0:/gm9/out`
3. On the computer it has to end up as `work/0004009B00010402/romfs/EU/country_LZ.bin` and
   friends - six region folders, 129 files, 564 KB in total.


## 5. Moving to the computer and checking

`START` to reboot → power off → SD card into the computer:

```bash
cp -R /Volumes/<SD>/gm9/out/00040* work/
```

You want `work/<TID>/romfs/…` — exactly that nesting, with no extra level. Then:

```bash
python3 tools/dumpinfo.py work
```

For every dump it prints the language folders, the message files and the string counts:

```
=== 000400300000D002  (512 KiB)
  message/  languages: 8
    EU_Dutch, EU_English, ...
    EU_English/swkbd_msbt_LZ.bin: 214 strings
    -> 214 translatable strings
```

What should worry you:

| Symptom | Cause |
|---|---|
| `no romfs/ inside` | the wrong level was copied — check the folder nesting |
| `no message*/ folders` | this title keeps its text outside `message/`. That happens (Game Notes, the Camera, Face Raiders) — look through the romfs by hand |
| `!! no English folder` | the dump is from another region |
| 1–2 language folders instead of 8 | not the largest `.app` was taken, i.e. an old version of the title |
| `0 KiB` or very little | the copy was interrupted, do it again |

The language folder name differs per title: the HOME Menu uses `EU_Russian`, the Instruction
Manual uses `EU_Russia` without the `n`. Check each dump.

Quick font check:

```bash
python3 tools/lz11.py work/0004009B00014002/cbf_std.bcfnt.lz   # must print the magic b'CFNT'
```

## 6. Building

```bash
make font       # the font → assets/font_charset.txt + font_widths.json
make extract    # romfs → src/strings/*.json (existing translations are kept)
make validate   # checks glyphs, width, line count, tags
make build      # → dist/luma/titles/...
make package    # → 3ds-ua-<version>.zip
```

Python 3.11+, no external dependencies.

## SD card space

The dumps add up to about 50 MB (System Settings is the largest). If space is tight, delete the
NAND backup from `gm9/out` — it should already be on your computer.
