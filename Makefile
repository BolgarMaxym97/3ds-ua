SHELL := /bin/bash
PY := python3

HOME_MENU_TID := 0004003000009802
FONT_TID := 0004009B00014002
VERSION := 1.4.0

# Which language the mod stands in place of. `ru` builds into dist/, `en` into dist_en/;
# the targets below build both, and SLOT= picks one for the single-slot targets (sd).
# See tools/variant.py.
SLOT := ru
DIST := $(if $(filter en,$(SLOT)),dist_en,dist)

.PHONY: help extract extract-manuals font hud-font validate build build-ru build-en \
	manuals manuals-ru manuals-en all package package-ru package-en clean sd

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

package: package-ru package-en ## build both release archives

package-ru: manuals-ru ## build 3ds-ua-from-ru-$(VERSION).zip
	$(PY) tools/package.py $(VERSION) --slot ru

package-en: manuals-en ## build 3ds-ua-from-en-$(VERSION).zip
	$(PY) tools/package.py $(VERSION) --slot en

sd: ## copy onto the SD card (SD=/Volumes/... , SLOT=ru|en)
	@test -n "$(SD)" || { echo "pass SD=/Volumes/<name>"; exit 1; }
	$(MAKE) build-$(SLOT)
	rsync -av $(DIST)/luma/ "$(SD)/luma/"

clean: ## remove the build output
	rm -rf dist dist_en
