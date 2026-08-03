SHELL := /bin/bash
PY := python3

HOME_MENU_TID := 0004003000009802
FONT_TID := 0004009B00014002
VERSION := 0.8.0

.PHONY: help extract extract-manuals font validate build manuals all package clean sd

help:  ## show this list
	@grep -E '^[a-z-]+:.*?##' $(MAKEFILE_LIST) | sed 's/:.*##/\t—/'

extract: ## romfs in work/ -> src/strings/*.json (existing translations are kept)
	$(PY) tools/extract.py work/$(HOME_MENU_TID) home_menu

font: ## re-read the system font -> assets/font_charset.txt + font_widths.json
	$(PY) tools/font_cmap.py work/$(FONT_TID)/cbf_std.bcfnt.lz assets/font_charset.txt

hud-font: ## re-render the added HUD glyphs -> assets/hud_glyphs.json (needs Pillow)
	$(PY) tools/hud_glyphs.py --report

validate: ## check translations (glyphs, width, line count, tags)
	$(PY) tools/validate.py

build: validate ## build dist/luma/titles/...
	$(PY) tools/build.py

extract-manuals: ## Manual.bcma in work/ -> src/manuals/*.json (existing translations are kept)
	$(PY) tools/manual.py extract all

manuals: build ## rebuild the electronic manuals into dist/ (after build, which writes the rest)
	$(PY) tools/manual.py build all

all: manuals ## validate + build + manuals

package: manuals ## build the 3ds-ua-$(VERSION).zip release archive
	$(PY) tools/package.py $(VERSION)

sd: build ## copy onto the SD card (SD=/Volumes/...)
	@test -n "$(SD)" || { echo "pass SD=/Volumes/<name>"; exit 1; }
	rsync -av dist/luma/ "$(SD)/luma/"

clean: ## remove the build output
	rm -rf dist
