SHELL := /bin/bash
PY := python3

HOME_MENU_TID := 0004003000009802
FONT_TID := 0004009B00014002
VERSION := 1.8.0

# Which language the mod stands in place of. `ru` builds into dist/, `en` into dist_en/;
# the targets below build both, and SLOT= picks one for the single-slot targets (sd).
# See tools/variant.py.
SLOT := ru
DIST := $(if $(filter en,$(SLOT)),dist_en,dist)

# Which console the `sd` target copies for. `new3ds` lays $(DIST)/new3ds over the shared
# tree - the New 3DS copies of the browser and of Health and Safety, in the folders Luma
# reads for them. See write_loader_alias() in tools/build.py.
MODEL := old3ds

.PHONY: help extract extract-manuals font hud-font validate build build-ru build-en \
	manuals manuals-ru manuals-en all package package-ru package-en unistore unistore-check unistore-verify unistore-icon \
	clean sd

help:  ## show this list
	@grep -E '^[a-z-]+:.*?##' $(MAKEFILE_LIST) | sed 's/:.*##/\t—/'

extract: ## romfs in work/ -> src/strings/*.json (existing translations are kept)
	$(PY) tools/extract.py

font: ## re-read the system font -> assets/font_charset.txt + font_widths.json
	$(PY) tools/font_cmap.py work/$(FONT_TID)/cbf_std.bcfnt.lz assets/font_charset.txt

hud-font: ## re-render the added HUD glyphs -> assets/hud_glyphs.json (needs Pillow)
	$(PY) tools/hud_glyphs.py --report

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

package-ru: manuals-ru ## build 3ds-ua-from-ru-$(VERSION)-{old3ds,new3ds}.zip
	$(PY) tools/package.py $(VERSION) --slot ru

package-en: manuals-en ## build 3ds-ua-from-en-$(VERSION)-{old3ds,new3ds}.zip
	$(PY) tools/package.py $(VERSION) --slot en

# REV= bumps the store revision without a new release, for a store-only fix (a reworded
# script, a new icon). Universal-Updater refetches only when the revision grows.
unistore: ## regenerate unistore/3ds-ua.unistore from dist/ (REV=10801 for a store-only fix)
	$(PY) tools/unistore.py $(VERSION) $(if $(REV),--revision $(REV) --stamp)

unistore-check: ## walk the store's scripts and check them against TITLES and the built archives
	$(PY) tools/unistore.py $(VERSION) --check

unistore-verify: ## the same, plus resolve the download patterns against the published release
	$(PY) tools/unistore.py $(VERSION) --check --verify-release

# tex3ds comes from devkitPro, which the rest of the build does not need - so fall back to
# the container. Note the long `--atlas`: `-a` is rejected by tex3ds 2.3.0 despite its help.
unistore-icon: ## assets/unistore-icon.png -> unistore/3ds-ua.t3x (needs tex3ds or docker)
	@test -f assets/unistore-icon.png || $(PY) tools/unistore_icon.py
	@if command -v tex3ds >/dev/null; then \
		tex3ds --atlas -f rgba8888 -z auto -o unistore/3ds-ua.t3x assets/unistore-icon.png; \
	else \
		echo "no tex3ds, using docker"; \
		docker run --rm --user "$$(id -u):$$(id -g)" -v "$$PWD:/w" -w /w devkitpro/devkitarm \
			tex3ds --atlas -f rgba8888 -z auto -o unistore/3ds-ua.t3x assets/unistore-icon.png; \
	fi
	$(PY) tools/unistore.py $(VERSION)

sd: ## copy onto the SD card (SD=/Volumes/... , SLOT=ru|en, MODEL=old3ds|new3ds)
	@test -n "$(SD)" || { echo "pass SD=/Volumes/<name>"; exit 1; }
	$(MAKE) build-$(SLOT)
	rsync -av $(DIST)/luma/ "$(SD)/luma/"
	@test "$(MODEL)" != new3ds || rsync -av $(DIST)/new3ds/luma/ "$(SD)/luma/"

clean: ## remove the build output
	rm -rf dist dist_en
