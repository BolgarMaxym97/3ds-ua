#include "install.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "payload/payload.h"
#include "sysfont/sysfont.h"

#define FONT_TID 0x0004009B00014002ull /* the shared font archive, EUR/USA/JPN */
#define FONT_FILE "sysfont:/cbf_std.bcfnt.lz"
#define STACK_SIZE (64 * 1024)

bool install_font_allowed(const Console *c, bool font_before)
{
    /* New 3DS too: its NS (a New 3DS XL, 2026-10-22) is byte for byte the Old 3DS one, and
     * the extra NS patch Luma applies on a New 3DS (0x10E1EC) is clear of ours */
    if (!c->is_luma || c->luma_version < LUMA_FULL || !c->ns_ok)
        return false;
    return !(font_before && !c->external_modules);
}

static bool need_met(const Need *n, void *ctx)
{
    (void)ctx;
    u16 remaster;
    return checks_title_remaster(n->title, &remaster) && remaster == n->remaster;
}

/* The console's font and our overlay, read before any thread starts: mounting another
 * title's RomFS changes libctru's device list, which the worker reads romfs:/ through. */
static bool read_font_inputs(Worker *w)
{
    char path[64];
    size_t len;
    if (R_FAILED(romfsMountFromTitle(FONT_TID, MEDIATYPE_NAND, "sysfont"))) {
        w->font_note = "cannot open the system font";
        return false;
    }
    int status = payload_read_file(FONT_FILE, &w->stock, &len);
    romfsUnmount("sysfont");
    w->stock_len = len;
    snprintf(path, sizeof(path), DATA_ROOT "/%s", w->job.m->upturn);
    if (status || payload_read_file(path, &w->upturn, &len)) {
        w->font_note = "cannot read the font files";
        return false;
    }
    w->upturn_len = len;
    return true;
}

static void free_font_inputs(Worker *w)
{
    free(w->stock);
    free(w->upturn);
    w->stock = w->upturn = NULL;
}

static uint8_t *make_font(Worker *w, size_t *len)
{
    uint8_t *out = NULL;
    if (!w->stock && !read_font_inputs(w)) {
        free_font_inputs(w);
        return NULL;
    }
    SysfontStatus status = sysfont_build(w->stock, w->stock_len, w->upturn, w->upturn_len, &out, len);
    free_font_inputs(w);
    if (status != SYSFONT_OK) {
        w->font_note = sysfont_error(status);
        return NULL;
    }
    return out;
}

bool install_font_sha(const Manifest *m, uint8_t sha[32])
{
    /* upturn.bin names the font it makes: "UAUP", version, count, sha of the source, sha of
     * the result (tools/sysfont_glyphs.py write_upturn) */
    uint8_t *upturn;
    size_t len;
    char path[64];
    bool ok = false;
    snprintf(path, sizeof(path), DATA_ROOT "/%s", m->upturn);
    if (!payload_read_file(path, &upturn, &len)) {
        ok = len >= 6 + 64 && !memcmp(upturn, "UAUP", 4);
        if (ok)
            memcpy(sha, upturn + 6 + 32, 32);
        free(upturn);
    }
    return ok;
}

static void font_work(void *arg)
{
    Worker *w = arg;
    w->font = make_font(w, &w->font_len);
}

/* The engine's FontFn: the font from the thread started with the job, or built now. */
static uint8_t *build_font(void *ctx, size_t *len)
{
    Worker *w = ctx;
    if (!w->font_thread)
        return make_font(w, len);
    threadJoin(w->font_thread, U64_MAX);
    threadFree(w->font_thread);
    w->font_thread = NULL;
    uint8_t *font = w->font;
    *len = w->font_len;
    w->font = NULL;
    return font;
}

static uint64_t clock_ms(void)
{
    return osGetTime();
}

static void exclusive(bool on)
{
    aptSetHomeAllowed(!on);
    aptSetSleepAllowed(!on);
    if (on) {
        if (R_SUCCEEDED(ndmuInit())) {
            NDMU_EnterExclusiveState(NDM_EXCLUSIVE_STATE_INFRASTRUCTURE);
            NDMU_LockState();
        }
    } else {
        NDMU_UnlockState();
        NDMU_LeaveExclusiveState();
        ndmuExit();
    }
}

static void work(void *arg)
{
    Worker *w = arg;
    w->status = engine_run(&w->job);
    w->running = false;
}

bool install_start(Worker *w, const Manifest *m, const Console *c, Op op, Slot slot, Glyphs glyphs, bool want_font,
                   bool build_font_now)
{
    memset(w, 0, sizeof(*w));
    Job *j = &w->job;
    j->m = m;
    j->data_root = DATA_ROOT;
    j->sd_root = SD_ROOT;
    j->op = op;
    j->slot = slot;
    j->model = c->is_new3ds ? MODEL_NEW3DS : MODEL_OLD3DS;
    j->glyphs = glyphs;
    j->want_font = want_font;
    j->luma_game_on = c->game_patching;
    j->luma_external_on = c->external_modules;
    j->need_met = need_met;
    j->build_font = build_font;
    j->ctx = w;
    j->clock_ms = clock_ms;

    s32 prio = 0x30;
    svcGetThreadPriority(&prio, CUR_THREAD_HANDLE);
    exclusive(true);
    w->running = true;
    /* Below the UI thread, so the screens keep drawing. The font builder goes lower still:
     * the 3DS kernel does not time-slice threads of one priority, so it runs exactly while
     * the worker waits on the SD card - the files and the font take the time of the longer. */
    install_font_sha(m, j->font_sha);
    if (want_font && build_font_now && read_font_inputs(w))
        w->font_thread = threadCreate(font_work, w, STACK_SIZE, prio + 2, -2, false);
    if (!w->font_thread)
        free_font_inputs(w); /* the engine builds it itself if it gets that far */
    w->thread = threadCreate(work, w, STACK_SIZE, prio + 1, -2, false);
    if (!w->thread) {
        w->running = false;
        if (w->font_thread) {
            threadJoin(w->font_thread, U64_MAX);
            threadFree(w->font_thread);
            w->font_thread = NULL;
        }
        free(w->font);
        exclusive(false);
        return false;
    }
    return true;
}

bool install_poll(Worker *w)
{
    if (!w->thread || w->running)
        return false;
    threadJoin(w->thread, U64_MAX);
    threadFree(w->thread);
    w->thread = NULL;
    if (w->font_thread) { /* the engine did not need it (the font was already on the card) */
        threadJoin(w->font_thread, U64_MAX);
        threadFree(w->font_thread);
        w->font_thread = NULL;
    }
    free(w->font);
    w->font = NULL;
    free_font_inputs(w);
    exclusive(false);
    return true;
}

bool install_live_letters(void)
{
    static const u32 letters[] = {0x0456, 0x0406, 0x0457, 0x0407, 0x0454, 0x0404, 0x0491, 0x0490, 0x02BC};
    CFNT_s *font = fontGetSystemFont();
    if (!font)
        return false;
    int missing = fontGetInfo(font)->alterCharIndex;
    for (size_t i = 0; i < sizeof(letters) / sizeof(*letters); i++)
        if (fontGlyphIndexFromCodePoint(font, letters[i]) == missing)
            return false;
    return true;
}

/* A plain reboot. NS_RebootToTitle (back into the app) left an Old 3DS with Luma 13.4 on a
 * black screen until the power button was held (2026-10-22): never again. */
void install_reboot(void)
{
    APT_HardwareResetAsync();
}
