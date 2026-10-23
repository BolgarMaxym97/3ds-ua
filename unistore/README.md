# UniStore

Since 2.0.0 the mod is installed by its own app, «Українізатор 3DS» (`installer/`), and both
stores here only put that app's CIA on the console. Installing, updating, switching the slot
and removing the translation all happen inside the app.

- `3ds-ua.unistore` — the project's own Universal-Updater store, kept alive for users who
  added it in the 1.x days. One entry, one script: download the latest
  `3ds-ua-installer-<version>.cia` from GitHub Releases, install it, delete the download.

  ```
  https://raw.githubusercontent.com/BolgarMaxym97/3ds-ua/main/unistore/3ds-ua.unistore
  ```

- `universal-db.json` — the entry for [Universal-Team/db](https://github.com/Universal-Team/db)
  (`source/apps/3ds-ua.json`). No scripts of its own: Universal-DB generates one for the CIA
  asset, and `download_filter` keeps the four zips out of Universal-Updater.
- `3ds-ua.t3x` — the store icon, the same picture as the app's HOME Menu icon
  (`make unistore-icon`).

Do not edit these by hand — `make release` regenerates them from `tools/unistore.py` and the
version in `Makefile`, and `make unistore-check` checks them against the built assets. The
release order matters: publish the GitHub release with the CIA and the four archives
**before** pushing a regenerated store, or everyone who refreshes in between gets a download
error. See the «Випуск» section of `docs/internals.md`.
