#include "checks.h"

#include <stdio.h>
#include <string.h>
#include <sys/stat.h>

/* Luma's svcGetSystemInfo(0x10000, ...) - k11_extension/source/svc/GetSystemInfo.c:
 * 0 = version as SYSTEM_VERSION(major, minor, build), 3 = the config bitfield, whose
 * bit 1 is "Load external FIRMs and modules" and bit 2 "Enable game patching"
 * (sysmodules/rosalina/include/luma_config.h). */
#define LUMA_INFO 0x10000
#define LUMA_INFO_VERSION 0
#define LUMA_INFO_CONFIG 3
#define LUMA_CFG_EXTERNAL_MODULES (1u << 1)
#define LUMA_CFG_GAME_PATCHING (1u << 2)

/* A file only this mod puts there, in every build (tools/unistore.py INSTALLED_FILES), and
 * the app's own record. */
#define INSTALLED_MARK "sdmc:/luma/titles/0004003000009802/banner_22800.bin"
#define INSTALLED_RECORD "sdmc:/3ds/3ds-ua/installed.txt"

#define NS_TID 0x0004013000008002ull

bool checks_title_remaster(u64 tid, u16 *remaster)
{
    AM_TitleEntry info;
    if (R_FAILED(AM_GetTitleInfo(MEDIATYPE_NAND, 1, &tid, &info)))
        return false;
    *remaster = info.version >> 10; /* TMD v<major>.<minor>.<micro>: major is the remaster */
    return true;
}

void checks_run(Console *c, const Manifest *m)
{
    memset(c, 0, sizeof(*c));

    s64 out = 0;
    if (R_SUCCEEDED(svcGetSystemInfo(&out, LUMA_INFO, LUMA_INFO_VERSION))) {
        c->is_luma = true;
        c->luma_version = (u32)out;
        if (R_SUCCEEDED(svcGetSystemInfo(&out, LUMA_INFO, LUMA_INFO_CONFIG))) {
            c->external_modules = out & LUMA_CFG_EXTERNAL_MODULES;
            c->game_patching = out & LUMA_CFG_GAME_PATCHING;
        }
    }

    CFGU_SecureInfoGetRegion(&c->region);
    c->region_ok = c->region == CFG_REGION_EUR;
    CFGU_GetSystemModel(&c->model);
    CFGU_GetSystemLanguage(&c->language);
    APT_CheckNew3DS(&c->is_new3ds);

    FS_ArchiveResource sd;
    if (R_SUCCEEDED(FSUSER_GetArchiveResource(&sd, SYSTEM_MEDIATYPE_SD)))
        c->sd_free = (u64)sd.freeClusters * sd.clusterSize;

    PTMU_GetBatteryLevel(&c->battery);
    bool adapter = false;
    u8 charge = 0;
    PTMU_GetAdapterState(&adapter);
    PTMU_GetBatteryChargeState(&charge);
    c->charging = adapter || charge;

    Model model = c->is_new3ds ? MODEL_NEW3DS : MODEL_OLD3DS;
    for (size_t i = 0; m && i < m->need_count; i++) {
        const Need *n = &m->needs[i];
        if (n->model != model)
            continue;
        u16 remaster;
        c->titles_checked++;
        if (!checks_title_remaster(n->title, &remaster) || remaster != n->remaster)
            c->titles_skipped++;
    }
    u16 ns;
    c->ns_ok = m && checks_title_remaster(NS_TID, &ns) && ns == m->ns_remaster;

    struct stat st;
    c->installed_before = stat(INSTALLED_MARK, &st) == 0 || stat(INSTALLED_RECORD, &st) == 0;
}

Level checks_blocking(const Console *c)
{
    if (!c->is_luma || c->luma_version < LUMA_MIN || !c->region_ok || c->sd_free < SD_NEEDED)
        return LEVEL_FAIL;
    if (c->battery < BATTERY_MIN && !c->charging)
        return LEVEL_FAIL;
    return LEVEL_OK;
}

void checks_luma_string(const Console *c, char *out, size_t cap)
{
    u32 v = c->luma_version;
    if (GET_VERSION_REVISION(v))
        snprintf(out, cap, "v%lu.%lu.%lu", GET_VERSION_MAJOR(v), GET_VERSION_MINOR(v), GET_VERSION_REVISION(v));
    else
        snprintf(out, cap, "v%lu.%lu", GET_VERSION_MAJOR(v), GET_VERSION_MINOR(v));
}

const char *checks_language_name(u8 language)
{
    switch (language) {
    case CFG_LANGUAGE_JP: return "Japanese"; /* the UI font has no kana or kanji */
    case CFG_LANGUAGE_EN: return "English";
    case CFG_LANGUAGE_FR: return "Français";
    case CFG_LANGUAGE_DE: return "Deutsch";
    case CFG_LANGUAGE_IT: return "Italiano";
    case CFG_LANGUAGE_ES: return "Español";
    case CFG_LANGUAGE_NL: return "Nederlands";
    case CFG_LANGUAGE_PT: return "Português";
    case CFG_LANGUAGE_RU: return "Русский";
    }
    return "?";
}

const char *checks_model_name(const Console *c)
{
    switch (c->model) {
    case CFG_MODEL_3DS: return "Nintendo 3DS";
    case CFG_MODEL_3DSXL: return "Nintendo 3DS XL";
    case CFG_MODEL_N3DS: return "New Nintendo 3DS";
    case CFG_MODEL_2DS: return "Nintendo 2DS";
    case CFG_MODEL_N3DSXL: return "New Nintendo 3DS XL";
    case CFG_MODEL_N2DSXL: return "New Nintendo 2DS XL";
    }
    return c->is_new3ds ? "New Nintendo 3DS" : "Nintendo 3DS";
}

void checks_size_string(u64 bytes, char *out, size_t cap)
{
    if (bytes >= 1024ull * 1024 * 1024) {
        u64 tenths = bytes * 10 / (1024ull * 1024 * 1024);
        snprintf(out, cap, "%llu,%llu ГБ", tenths / 10, tenths % 10);
    } else {
        snprintf(out, cap, "%llu МБ", bytes / (1024 * 1024));
    }
}
