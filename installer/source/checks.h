/*
 * What the installer finds out about the console before it lets anything happen
 * (docs/plan/installer-app.md, §3). Nothing here changes the console.
 */
#ifndef CHECKS_H
#define CHECKS_H

#include <3ds.h>
#include <stdbool.h>

#include "payload/manifest.h"

typedef enum { LEVEL_OK, LEVEL_INFO, LEVEL_WARN, LEVEL_FAIL } Level;

/* Luma3DS v13.0 reads NS patches from luma/sysmodules/; v10.3 is the floor for LayeredFS
 * on the HOME Menu and applets (memory: luma-min-version). */
#define LUMA_MIN SYSTEM_VERSION(10, 3, 0)
#define LUMA_FULL SYSTEM_VERSION(13, 0, 0)
#define SD_NEEDED (40ull * 1024 * 1024)
#define BATTERY_MIN 2           /* PTMU level 0-5; below this only on the charger */

typedef struct {
    bool is_luma;
    u32 luma_version;
    bool game_patching, external_modules;
    u8 region;
    bool region_ok;
    u8 model;                   /* CFG_SystemModel */
    bool is_new3ds;
    u64 sd_free;
    u8 battery;
    bool charging;
    int titles_checked, titles_skipped;
    bool ns_ok;                 /* NS is the build the font patch is for */
    bool installed_before;      /* a copy of the mod is already on the card */
    u8 language;                /* CFG_Language: what the console shows without the mod */
    bool config_editable;       /* luma/config.ini is one the app can switch the flags in */
} Console;

void checks_run(Console *c, const Manifest *m);

/* The remaster version of a NAND title (TMD version >> 10), as the code patches name it. */
bool checks_title_remaster(u64 tid, u16 *remaster);

/* The worst of the checks that block an install, and of all of them. */
Level checks_blocking(const Console *c);

/* "v13.4" / "v13.4.1" */
void checks_luma_string(const Console *c, char *out, size_t cap);
/* The system language's own name: "Русский", "English"... */
const char *checks_language_name(u8 language);
/* "Nintendo 3DS XL" etc. */
const char *checks_model_name(const Console *c);
/* "4,6 ГБ" / "820 МБ", with the Ukrainian decimal comma */
void checks_size_string(u64 bytes, char *out, size_t cap);

#endif
