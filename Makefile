SHELL := /bin/bash
PY := python3

HOME_MENU_TID := 0004003000009802
FONT_TID := 0004009B00014002
VERSION := 2.1.0

# Which language the mod stands in place of. `ru` builds into dist/, `en` into dist_en/;
# the targets below build both, and SLOT= picks one for the single-slot targets (sd).
# See tools/variant.py.
SLOT := ru
DIST := $(if $(filter en,$(SLOT)),dist_en,dist)

# Which console the `sd` target copies for. `new3ds` lays $(DIST)/new3ds over the shared
# tree - the New 3DS copies of the browser and of Health and Safety, in the folders Luma
# reads for them. See write_loader_alias() in tools/build.py.
MODEL := old3ds

# Which homoglyph variant of src/homoglyphs.json the text is built with; empty = its
# `default`. `real` keeps і ї є ґ as they are and is only for a console whose system font
# has them - see `sysfont` below and tools/sysfont_glyphs.py.
GLYPHS :=
export UA_GLYPHS := $(GLYPHS)

.PHONY: help extract extract-manuals font hud-font sysfont sysfont-cia nsfont installer-data installer-fonts installer installer-art installer-cia installer-makerom installer-test release validate build build-ru build-en \
	manuals manuals-ru manuals-en all package package-ru package-en unistore unistore-check unistore-verify unistore-icon udb \
	clean sd

help:  ## show this list
	@grep -E '^[a-z-]+:.*?##' $(MAKEFILE_LIST) | sed 's/:.*##/\t—/'

extract: ## romfs in work/ -> src/strings/*.json (existing translations are kept)
	$(PY) tools/extract.py

font: ## re-read the system font -> assets/font_charset.txt + font_widths.json
	$(PY) tools/font_cmap.py work/$(FONT_TID)/cbf_std.bcfnt.lz assets/font_charset.txt

hud-font: ## re-render the added HUD glyphs -> assets/hud_glyphs.json (needs Pillow)
	$(PY) tools/hud_glyphs.py --report

sysfont: ## opt-in: add і ї є ґ ʼ to the system font -> dist_sysfont/ (needs Pillow + fontTools)
	$(PY) tools/sysfont_glyphs.py --report --png dist_sysfont/glyphs.png
	mkdir -p dist_sysfont/sd/gm9/scripts && cp tools/gm9/sysfont_*.gm9 dist_sysfont/sd/gm9/scripts/

sysfont-cia: ## opt-in: STOCK=<stock_standard.cia> -> the patched font title for GodMode9, in dist_sysfont/sd/
	@test -n "$(STOCK)" || { echo "pass STOCK=<stock_standard.cia written by sysfont_backup.gm9>"; exit 1; }
	$(PY) tools/sysfont_cia.py build "$(STOCK)" --out dist_sysfont/sd/gm9/3ds-ua/sysfont/sysfont_patched.cia

nsfont: sysfont ## opt-in, no NAND write: NS reads the patched font off SD -> dist_sysfont/sd/ (Luma 13+)
	$(PY) tools/ns_font.py --check

# The installer app carries all eight builds (2 slots x 2 consoles x 2 glyph variants) and
# the NS font patch; tools/installer_manifest.py packs them as whole files + deltas. The
# `real` builds have to be made first and moved aside, then the default ones rebuilt.
# Needs PY with Pillow, fontTools and bsdiff4 (the font and the deltas): PY=.venv/bin/python
installer-data: ## everything the installer app ships -> dist_installer/romfs/data
	$(MAKE) manuals GLYPHS=real
	rm -rf dist_real dist_en_real && cp -R dist dist_real && cp -R dist_en dist_en_real
	$(MAKE) manuals
	$(MAKE) nsfont
	$(PY) tools/installer_manifest.py $(VERSION)

# The UI font: Nunito (OFL, installer/assets/fonts) at 700 and 800, cut to the characters
# the app draws, as bcfnt for citro2d. fontTools instances the variable font; mkbcfnt and the
# app itself build in the devkitARM container, like `make unistore-icon`.
INSTALLER_FONT := installer/assets/fonts/Nunito[wght].ttf
DKA := docker run --rm --user "$$(id -u):$$(id -g)" -v "$$PWD:/w" -w /w devkitpro/devkitarm

installer-fonts: ## the installer's UI fonts -> dist_installer/romfs/gfx (needs fontTools + docker)
	@mkdir -p dist_installer/fonts dist_installer/romfs/gfx
	for w in 700 800; do $(PY) -m fontTools.varLib.instancer "$(INSTALLER_FONT)" wght=$$w -q -o dist_installer/fonts/Nunito-$$w.ttf || exit 1; done
	$(PY) -c "cps = [*range(0x20, 0x7F), *range(0xA0, 0x100), *range(0x400, 0x460), 0x490, 0x491, 0x2BC, 0x2013, 0x2014, 0x2018, 0x2019, 0x201C, 0x201D, 0x201E, 0x2026, 0x2116, 0x2248, 0x2192]; open('dist_installer/fonts/charset.txt', 'w').write(' '.join(map(str, cps)))"
	$(DKA) sh -c 'for w in 700 800; do /opt/devkitpro/tools/bin/mkbcfnt -s 24 -w dist_installer/fonts/charset.txt -o dist_installer/romfs/gfx/nunito_$$w.bcfnt dist_installer/fonts/Nunito-$$w.ttf || exit 1; done'

installer-art: ## the installer's icon, HOME Menu banner and its sound -> dist_installer/art (after installer-fonts)
	$(PY) tools/installer_art.py dist_installer/fonts/Nunito-800.ttf dist_installer/art

installer: installer-data installer-fonts installer-art ## the installer app -> installer/3ds-ua-installer.3dsx (PY=.venv/bin/python)
	$(DKA) make -C installer

# The CIA wraps the same ELF and RomFS. makerom (3DSGuy/Project_CTR) and bannertool
# (carstene1ns/3ds-bannertool) are not in the devkitARM image: point these at local builds.
MAKEROM ?= tmp/tools/makerom/makerom
BANNERTOOL ?= tmp/tools/bannertool.bin
INSTALLER_CIA := installer/3ds-ua-installer.cia
# The release asset, next to the four zips; tools/package.py:installer_name() spells it for the
# stores, so keep the two in step.
INSTALLER_ASSET := 3ds-ua-installer-$(VERSION).cia
installer-cia: installer ## the installer as a CIA, with its HOME Menu banner -> $(INSTALLER_ASSET)
	$(BANNERTOOL) makebanner -i dist_installer/art/banner.png -a dist_installer/art/banner.wav -o dist_installer/art/banner.bnr
	$(MAKE) installer-makerom
	@if [ -f $(HOME_MENU_CODE) ]; then \
		$(PY) tools/installer_logo.py render $(INSTALLER_CIA) dist_installer/fonts/Nunito-800.ttf dist_installer/logo && \
		$(DKA) sh -c 'for n in waves logo; do /opt/devkitpro/tools/bin/tex3ds -f etc1 -q high -z none -r -o dist_installer/logo/$$n.etc1 dist_installer/logo/$$n.png || exit 1; done' && \
		$(PY) tools/installer_logo.py pack dist_installer/logo $(HOME_MENU_CODE) && \
		$(MAKE) installer-makerom CIA_LOGO="-logo ../dist_installer/logo/logo.bcma.lz"; \
	else echo "no $(HOME_MENU_CODE): the CIA keeps makerom's homebrew splash"; fi
	cp $(INSTALLER_CIA) $(INSTALLER_ASSET)
	@ls -la $(INSTALLER_ASSET)

# The splash is signed with the HOME Menu's key (tools/installer_logo.py), read from the
# console's own HOME Menu code; first build with makerom's homebrew logo, which it reworks.
HOME_MENU_CODE := work/0004003000009802/code.bin
installer-makerom:
	cd installer && ../$(MAKEROM) -f cia -o 3ds-ua-installer.cia -target t -exefslogo $(CIA_LOGO) -rsf cia.rsf \
		-elf 3ds-ua-installer.elf -icon 3ds-ua-installer.smdh -banner ../dist_installer/art/banner.bnr \
		-major $(word 1,$(subst ., ,$(VERSION))) -minor $(word 2,$(subst ., ,$(VERSION))) -micro $(word 3,$(subst ., ,$(VERSION)))

installer-test: ## host tests of the installer's font builder, payload, install engine and stats report (after installer-data)
	@mkdir -p tmp
	cc -std=c99 -O2 -Wall -Wextra -Werror -o tmp/sysfont_test installer/tests/sysfont_test.c installer/source/sysfont/*.c
	tmp/sysfont_test work/$(FONT_TID)/cbf_std.bcfnt.lz dist_sysfont/upturn.bin dist_sysfont/cbf_std.bcfnt.lz
	cc -std=c99 -O2 -Wall -Wextra -Werror -o tmp/payload_test installer/tests/payload_test.c \
		installer/source/payload/*.c installer/source/sysfont/sha256.c -lz
	tmp/payload_test dist_installer/romfs/data
	cc -std=c99 -O2 -Wall -Wextra -Werror -D_DEFAULT_SOURCE -o tmp/engine_test installer/tests/engine_test.c \
		installer/source/engine/*.c installer/source/payload/*.c installer/source/sysfont/sha256.c -lz
	tmp/engine_test dist_installer/romfs/data tmp/console/config.ini tmp/engine_sd
	cc -std=c99 -O2 -Wall -Wextra -Werror -o tmp/report_test installer/tests/report_test.c installer/source/stats/report.c
	tmp/report_test

validate: ## check translations (glyphs, width, line count, tags) - covers both slots at once
	$(PY) tools/validate.py

build: build-ru build-en ## build dist/ (over Russian) and dist_en/ (over English)

build-ru: validate ## build dist/luma/titles/... over the Russian slot
	$(PY) tools/build.py --slot ru

build-en: validate ## build dist_en/luma/titles/... over the English slot
	$(PY) tools/build.py --slot en

extract-manuals: ## Manual.bcma in work/ -> src/manuals/*.json (existing translations are kept)
	$(PY) tools/manual.py extract all

manuals: manuals-ru manuals-en ## rebuild the electronic manuals into both builds

manuals-ru: build-ru ## rebuild the manuals into dist/ (after build, which writes the rest)
	$(PY) tools/manual.py build all --slot ru

manuals-en: build-en ## rebuild the manuals into dist_en/
	$(PY) tools/manual.py build all --slot en

all: manuals ## validate + build + manuals, both slots

package: package-ru package-en ## build all four release archives (2 slots x 2 consoles)

release: installer-cia package ## every release asset: the installer CIA and the four zips (PY=.venv/bin/python)
	$(PY) tools/unistore.py $(VERSION)
	$(PY) tools/unistore.py $(VERSION) --udb
	$(PY) tools/unistore.py $(VERSION) --check

package-ru: manuals-ru ## build 3ds-ua-from-ru-$(VERSION)-{old3ds,new3ds}.zip
	$(PY) tools/package.py $(VERSION) --slot ru

package-en: manuals-en ## build 3ds-ua-from-en-$(VERSION)-{old3ds,new3ds}.zip
	$(PY) tools/package.py $(VERSION) --slot en

# REV= bumps the store revision without a new release, for a store-only fix (a reworded
# script, a new icon). Universal-Updater refetches only when the revision grows.
unistore: ## regenerate unistore/3ds-ua.unistore (REV=20001 for a store-only fix)
	$(PY) tools/unistore.py $(VERSION) $(if $(REV),--revision $(REV) --stamp)

udb: ## write unistore/universal-db.json - the submission file for Universal-Team/db
	$(PY) tools/unistore.py $(VERSION) --udb

unistore-check: ## check the store and the Universal-DB file against the built release assets
	$(PY) tools/unistore.py $(VERSION) --check

unistore-verify: ## the same, plus resolve the download pattern against the published release
	$(PY) tools/unistore.py $(VERSION) --check --verify-release

# The store shows the installer's own HOME Menu icon (tools/installer_art.py), so the app looks
# the same in Universal-Updater and on the HOME Menu; assets/unistore-icon.png is the committed
# copy Universal-DB fetches by URL. tex3ds comes from devkitPro - fall back to the container.
# Note the long `--atlas`: `-a` is rejected by tex3ds 2.3.0 despite its help.
unistore-icon: installer-art ## the installer's icon -> assets/unistore-icon.png + unistore/3ds-ua.t3x
	cp dist_installer/art/icon.png assets/unistore-icon.png
	@if command -v tex3ds >/dev/null; then \
		tex3ds --atlas -f rgba8888 -z auto -o unistore/3ds-ua.t3x assets/unistore-icon.png; \
	else \
		echo "no tex3ds, using docker"; \
		$(DKA) tex3ds --atlas -f rgba8888 -z auto -o unistore/3ds-ua.t3x assets/unistore-icon.png; \
	fi

sd: ## copy onto the SD card (SD=/Volumes/... , SLOT=ru|en, MODEL=old3ds|new3ds)
	@test -n "$(SD)" || { echo "pass SD=/Volumes/<name>"; exit 1; }
	$(MAKE) build-$(SLOT)
	rsync -av $(DIST)/luma/ "$(SD)/luma/"
	@test "$(MODEL)" != new3ds || rsync -av $(DIST)/new3ds/luma/ "$(SD)/luma/"

clean: ## remove the build output
	rm -rf dist dist_en dist_sysfont dist_real dist_en_real dist_installer installer/build
