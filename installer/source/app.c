#include "app.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "engine/engine.h"
#include "engine/fsutil.h"
#include "engine/lumacfg.h"
#include "payload/payload.h"
#include "sysfont/sha256.h"
#include "qr.h"
#include "ui.h"

#define MANIFEST_PATH DATA_ROOT "/manifest.txt"
/* Outside 3ds/3ds-ua, which a removal deletes. */
#define LOG_PATH SD_ROOT "/3ds/3ds-ua-installer.log"
#define REBOOT_SECONDS 10

typedef struct {
    float x, y, w, h;
} Rect;

static bool hit(const Input *in, Rect r)
{
    return in->tapped && in->tap_x >= r.x && in->tap_x < r.x + r.w && in->tap_y >= r.y && in->tap_y < r.y + r.h;
}

static void go(App *app, ScreenId screen)
{
    if (screen == SCREEN_HELP || screen == SCREEN_CHECK || screen == SCREEN_RESCUE) {
        if (app->screen != SCREEN_HELP && app->screen != SCREEN_RESCUE && app->screen != SCREEN_CHECK)
            app->back = app->screen;
    }
    app->screen = screen;
    app->focus = 0;
}

static ScreenId home_screen(const App *app)
{
    return app->console.installed_before ? SCREEN_INSTALLED : SCREEN_MAIN;
}

static void show_error(App *app, const char *title, const char *text, bool retry)
{
    app->error_title = title;
    app->error_text = text;
    app->error_retry = retry;
    go(app, SCREEN_ERROR);
}

/* The real letters go on with the font in the same run (the engine falls back to the
 * stand-ins if the font does not), except where a font of ours is on the card but did not
 * load at boot: that would only show empty places again. */
static Glyphs wanted_glyphs(const App *app)
{
    return app->has_installed && app->installed.font && !app->live_letters ? GLYPHS_DEFAULT : GLYPHS_REAL;
}

static void start_op(App *app, Op op, Slot slot, Glyphs glyphs)
{
    if (!app->manifest_ok) {
        show_error(app, "Застосунок пошкоджено", "Встановіть його ще раз з Universal-Updater.", false);
        return;
    }
    bool font_before = app->has_installed && app->installed.font;
    bool want_font = op == OP_INSTALL && install_font_allowed(&app->console, font_before);
    /* the font on the card is this app's own when its recorded sha is the one upturn.bin
     * names; otherwise (none, or an older build of it) start building at once */
    bool font_current = false;
    uint8_t sha[32];
    const StateFile *font_file = font_before ? installed_find(&app->installed, app->manifest.font_path + 1) : NULL;
    if (font_file && install_font_sha(&app->manifest, sha))
        font_current = !memcmp(font_file->sha, sha, 32);
    app->op = op;
    app->op_slot = slot;
    app->op_glyphs = glyphs;
    app->reboot_at = 0;
    app->reboot_deadline = 0;
    if (!install_start(&app->worker, &app->manifest, &app->console, op, slot, glyphs, want_font, !font_current)) {
        show_error(app, "Не вдалося почати", "Закрийте застосунок і відкрийте його знову.", true);
        return;
    }
    app->working = true;
    memset(app->stage_ms, 0, sizeof(app->stage_ms));
    app->stage_ms[STAGE_CHECK] = osGetTime();
    app->last_stage = STAGE_CHECK;
    go(app, SCREEN_PROGRESS);
}

/* One line per operation: what ran, how it ended, how long each stage took. It goes to the
 * log on the card and, as the report's log, to the statistics. */
static void op_line(const App *app, char *out, size_t cap)
{
    static const char *stage_names[STAGE_COUNT] = {
        [STAGE_CHECK] = "check", [STAGE_BACKUP] = "backup", [STAGE_FILES] = "files",
        [STAGE_FONT] = "font",   [STAGE_LUMA] = "luma",     [STAGE_FINISH] = "finish",
    };
    const Job *j = &app->worker.job;
    size_t n = 0;
#define ADDF(...) (n += n < cap ? (size_t)snprintf(out + n, cap - n, __VA_ARGS__) : 0)
    ADDF("%s slot=%s glyphs=%s->%s status=%d font=%d", app->op == OP_REMOVE ? "remove" : "install",
         slot_name(app->op_slot), glyphs_name(app->op_glyphs), glyphs_name(j->glyphs_set), app->worker.status, j->font);
    if (app->finishing)
        ADDF(" auto=1");
    if (app->console.installed_before && !app->has_installed)
        ADDF(" took_over=1");
    if (j->foreign_ns)
        ADDF(" foreign_ns=1");
    if (app->worker.font_note)
        ADDF(" font_note=\"%s\"", app->worker.font_note);
    if (j->error[0])
        ADDF(" error=\"%s\"", j->error);
    ADDF(" files=%d moved=%d skipped=%d kept=%d luma_manual=%d restore=%.1fs write=%.1fs |", j->total, j->moved,
         j->skipped, j->kept, j->luma_manual, (double)j->restore_ms / 1000.0, (double)j->write_ms / 1000.0);
    /* stages in the order they ran (a removal runs them in another order than an install) */
    for (int i = 0; i < STAGE_COUNT; i++) {
        if (!app->stage_ms[i])
            continue;
        u64 end = app->stage_ms[STAGE_COUNT];
        for (int k = 0; k < STAGE_COUNT; k++)
            if (app->stage_ms[k] > app->stage_ms[i] && app->stage_ms[k] < end)
                end = app->stage_ms[k];
        ADDF(" %s=%.1fs", stage_names[i], (double)(end - app->stage_ms[i]) / 1000.0);
    }
    extern u32 __ctru_heap_size, __ctru_linear_heap_size;
    ADDF(" heap=%luMB linear=%luMB", __ctru_heap_size >> 20, __ctru_linear_heap_size >> 20);
    ADDF(" total=%.1fs", (double)(app->stage_ms[STAGE_COUNT] - app->stage_ms[STAGE_CHECK]) / 1000.0);
#undef ADDF
}

/* Why the real letters are or are not on after an install, in a word for the statistics. */
static const char *font_reason(const App *app)
{
    const Job *j = &app->worker.job;
    const Console *c = &app->console;
    if (j->font && j->glyphs_set == GLYPHS_REAL)
        return "ok";
    if (j->foreign_ns)
        return "foreign_ns";
    if (!j->want_font) {
        if (!c->is_luma || c->luma_version < LUMA_FULL)
            return "old_luma";
        return c->ns_ok ? "external_off" : "ns_unknown";
    }
    return app->worker.font_note ? app->worker.font_note : "not_loaded";
}

/* The statistics report for the operation that just ended; "skip" for one nobody asked to
 * count (a slot change). */
static const char *send_report(App *app, const char *line)
{
    static const char *stage_names[STAGE_COUNT] = {
        [STAGE_CHECK] = "check", [STAGE_BACKUP] = "backup", [STAGE_FILES] = "files",
        [STAGE_FONT] = "font",   [STAGE_LUMA] = "luma",     [STAGE_FINISH] = "finish",
    };
    const Job *j = &app->worker.job;
    const Console *c = &app->console;
    const char *before = app->has_installed ? app->installed.version : NULL;
    Report r = {.app = app->manifest.version, .ms = -1, .code = -1, .log = line};
    if (app->worker.status != ENGINE_OK) {
        r.event = "error";
        r.stage = stage_names[app->last_stage];
        r.code = app->worker.status;
        r.detail = j->error[0] ? j->error : NULL;
    } else if (app->op == OP_REMOVE) {
        r.event = "remove";
    } else if (!before) {
        r.event = "install";
    } else if (strcmp(before, app->manifest.version)) {
        r.event = "update";
    } else if (app->installed.slot != app->op_slot) {
        return "skip";
    } else {
        r.event = "reinstall";
    }
    r.prev = before;
    char luma[24], region[8];
    checks_luma_string(c, luma, sizeof(luma));
    if (c->region_ok)
        strcpy(region, "EUR");
    else
        snprintf(region, sizeof(region), "%u", c->region);
    r.model = checks_model_name(c);
    r.luma = c->is_luma ? luma + 1 : NULL;
    r.region = region;
    if (app->op == OP_INSTALL && app->worker.status == ENGINE_OK) {
        r.slot = slot_name(app->op_slot);
        r.glyphs = glyphs_name(j->glyphs_set);
        r.font = font_reason(app);
    }
    r.ms = (int64_t)(app->stage_ms[STAGE_COUNT] - app->stage_ms[STAGE_CHECK]);
    return stats_send(&app->stats, &r);
}

static void log_op(App *app)
{
    char line[1024];
    op_line(app, line, sizeof(line));
    const char *stats = send_report(app, line);
    FILE *f = fopen(LOG_PATH, "a");
    if (!f)
        return;
    fprintf(f, "%s %s stats=%s\n", app->manifest.version, line, stats);
    fclose(f);
}

static const char *engine_message(EngineStatus status)
{
    switch (status) {
    case ENGINE_E_PAYLOAD: return "Файл застосунку пошкоджено. Встановіть застосунок ще раз з Universal-Updater.";
    case ENGINE_E_WRITE: return "SD-карта не прийняла запис. Перевірте, чи на ній є місце і чи не захищена вона від запису.";
    case ENGINE_E_MEMORY: return "Застосунку забракло пам'яті. Спробуйте ще раз; якщо повториться — напишіть нам.";
    default: return "Сталася внутрішня помилка застосунку.";
    }
}

static void op_finished(App *app)
{
    app->working = false;
    app->stage_ms[STAGE_COUNT] = osGetTime();
    log_op(app);
    const Job *j = &app->worker.job;
    if (app->worker.status != ENGINE_OK) {
        show_error(app, "Не вдалося завершити", engine_message(app->worker.status), true);
        return;
    }
    if (j->luma_manual) {
        go(app, SCREEN_LUMA);
        return;
    }
    /* done: say so now, then reboot by itself - nothing is left to do after the reboot */
    /* by the clock, not by frames: the frame rate is not steady while a report is sent */
    app->reboot_at = osGetTime() + REBOOT_SECONDS * 1000;
    go(app, SCREEN_DONE);
}

/* What the app does by itself on start: finish an interrupted operation, take the real
 * letters off if the font did not load at boot, or put them on if it now does. True if it
 * took over. */
static bool run_auto(App *app)
{
    Pending p;
    if (engine_load_pending(SD_ROOT, &p) == 0) {
        app->finishing = true;
        /* the font of an interrupted install is not live yet: judge as a fresh start would */
        start_op(app, p.op, p.slot, p.glyphs == GLYPHS_REAL ? wanted_glyphs(app) : GLYPHS_DEFAULT);
        return true;
    }
    if (app->has_installed && app->installed.font && app->installed.glyphs == GLYPHS_DEFAULT && app->live_letters) {
        app->finishing = true;
        start_op(app, OP_INSTALL, app->installed.slot, GLYPHS_REAL);
        return true;
    }
    /* installed, but asleep: Luma's game patching was turned off since (or never could be
     * turned on). Checked before the font: without game patching nothing of ours runs. */
    if (app->has_installed && app->console.is_luma && !app->console.game_patching) {
        go(app, SCREEN_LUMA);
        return true;
    }
    if (app->has_installed && app->installed.glyphs == GLYPHS_REAL && !app->live_letters) {
        app->finishing = true;
        start_op(app, OP_INSTALL, app->installed.slot, GLYPHS_DEFAULT);
        return true;
    }
    return false;
}

/* ---------------------------------------------------------------- shared pieces */

static void draw_header(const App *app, const char *status, u32 status_color, bool dot)
{
    char line[64];
    ui_flag(22, 18, 48);
    ui_text(82, 18, 22, FONT_HEAVY, COL_INK, "Українізатор 3DS");
    if (status) {
        float x = 82;
        if (dot) {
            ui_circle(86, 53, 4, status_color);
            x = 95;
        }
        ui_text(x, 46, 12, FONT_BOLD, status_color, status);
    } else {
        snprintf(line, sizeof(line), "Версія %s · %s", app->manifest_ok ? app->manifest.version : "?",
                 checks_model_name(&app->console));
        ui_text(82, 46, 12, FONT_BOLD, COL_MUTED, line);
    }
}

static void draw_telegram_line(float x, float y, const char *text)
{
    ui_icon(ICON_TELEGRAM, x + 6, y + 7, 12, COL_TELEGRAM);
    ui_text(x + 17, y, 11.5f, FONT_BOLD, COL_MUTED, text); /* smaller and the "_" fades out */
}

static void draw_hints(const char *left_key, const char *left, const char *right_key, const char *right)
{
    if (left_key)
        ui_key_hint(14, 212, left_key, left);
    if (right_key) {
        float w = (strlen(right_key) > 1 ? ui_text_width(8, FONT_HEAVY, right_key) + 12 : 17) + 4 +
                  ui_text_width(11, FONT_BOLD, right);
        ui_key_hint(BOTTOM_W - 14 - w, 212, right_key, right);
    }
}

static void draw_primary(Rect r, Icon icon, const char *title, const char *subtitle, bool enabled)
{
    if (enabled) {
        ui_rrect(r.x, r.y + 3, r.w, r.h, 14, COL_BLUE_DARK);
        ui_rrect(r.x, r.y, r.w, r.h, 14, COL_BLUE);
    } else {
        ui_rrect(r.x, r.y, r.w, r.h, 13, COL_DISABLED);
    }
    u32 ink = enabled ? COL_WHITE : COL_MUTED;
    if (subtitle) {
        ui_icon(icon, r.x + 32, r.y + r.h / 2, 32, ink);
        ui_text(r.x + 64, r.y + r.h / 2 - 22, 22, FONT_HEAVY, ink, title);
        ui_text(r.x + 64, r.y + r.h / 2 + 6, 11, FONT_BOLD, ink, subtitle);
    } else if (enabled && icon != ICON_CHECK) {
        ui_icon(icon, r.x + 30, r.y + r.h / 2, 26, ink);
        ui_text(r.x + 54, r.y + r.h / 2 - 12, 19, FONT_HEAVY, ink, title);
    } else {
        ui_text_center(r.x + r.w / 2, r.y + r.h / 2 - 11, 17, FONT_HEAVY, ink, title);
    }
}

static void draw_tile(Rect r, Icon icon, const char *label, u32 color, bool vertical)
{
    ui_card(r.x, r.y, r.w, r.h, 11, COL_CARD, 1.5f);
    if (vertical) {
        ui_icon(icon, r.x + 12 + 9, r.y + r.h / 2 - 9, 18, color);
        ui_text(r.x + 12, r.y + r.h / 2 + 4, 13, FONT_HEAVY, color, label);
    } else {
        ui_icon(icon, r.x + 12 + 8, r.y + r.h / 2, 16, color);
        ui_text(r.x + 34, r.y + r.h / 2 - 8, 12.5f, FONT_HEAVY, color, label);
    }
}

/* A quiet full-width "Вийти" at the bottom of the home screens (START does the same). */
static void draw_exit(Rect r)
{
    ui_card(r.x, r.y, r.w, r.h, 10, COL_CARD, 1.5f);
    float w = 14 + 6 + ui_text_width(12.5f, FONT_HEAVY, "Вийти");
    float x = r.x + (r.w - w) / 2;
    ui_icon(ICON_POWER, x + 7, r.y + r.h / 2, 14, COL_MUTED);
    ui_text(x + 20, r.y + r.h / 2 - 8, 12.5f, FONT_HEAVY, COL_MUTED, "Вийти");
}

static void draw_chip(float *x, float y, const char *text, bool ok)
{
    float w = ui_text_width(11, FONT_BOLD, text) + 32;
    ui_rrect(*x, y, w, 22, 11, ok ? COL_GREEN_BG : COL_AMBER_BG);
    ui_icon(ok ? ICON_CHECK : ICON_WARN, *x + 14, y + 11, 12, ok ? COL_GREEN_TEXT : COL_AMBER);
    ui_text(*x + 23, y + 3.5f, 11, FONT_BOLD, ok ? COL_GREEN_TEXT : COL_AMBER_TEXT, text);
    *x += w + 6;
}

/* ---------------------------------------------------------------- check */

typedef struct {
    Level level;
    const char *label;
    char value[48];
} Row;

static int check_rows(const App *app, Row *rows)
{
    const Console *c = &app->console;
    int n = 0;
    char size[24];

    Row *r = &rows[n++];
    r->label = "Luma3DS";
    if (!c->is_luma) {
        r->level = LEVEL_FAIL;
        snprintf(r->value, sizeof(r->value), "не знайдено");
    } else {
        checks_luma_string(c, r->value, sizeof(r->value));
        r->level = c->luma_version < LUMA_MIN ? LEVEL_FAIL : c->luma_version < LUMA_FULL ? LEVEL_WARN : LEVEL_OK;
        if (r->level != LEVEL_OK)
            strncat(r->value, " — оновіть", sizeof(r->value) - strlen(r->value) - 1);
    }

    r = &rows[n++];
    r->label = "Консоль і регіон";
    r->level = c->region_ok ? LEVEL_OK : LEVEL_FAIL;
    snprintf(r->value, sizeof(r->value), "%s · %s", checks_model_name(c), c->region_ok ? "EUR" : "не EUR");

    r = &rows[n++];
    r->label = "Налаштування Luma";
    bool both = c->game_patching && c->external_modules;
    r->level = both ? LEVEL_OK : c->config_editable ? LEVEL_INFO : LEVEL_WARN;
    snprintf(r->value, sizeof(r->value), both ? "увімкнено" : c->config_editable ? "увімкнемо самі" : "увімкніть вручну");

    r = &rows[n++];
    r->label = "Місце на SD";
    checks_size_string(c->sd_free, size, sizeof(size));
    r->level = c->sd_free >= SD_NEEDED ? LEVEL_OK : LEVEL_FAIL;
    snprintf(r->value, sizeof(r->value), c->sd_free >= SD_NEEDED ? "%s вільно" : "лише %s", size);

    r = &rows[n++];
    bool low = c->battery < BATTERY_MIN && !c->charging;
    r->label = low ? "Низький заряд" : "Заряд";
    r->level = low ? LEVEL_FAIL : LEVEL_OK;
    snprintf(r->value, sizeof(r->value), low ? "підключіть зарядку" : c->charging ? "заряджається" : "достатньо");

    if (c->titles_skipped) {
        r = &rows[n++];
        r->label = "Системні програми";
        r->level = LEVEL_WARN;
        snprintf(r->value, sizeof(r->value), "%d не тієї версії", c->titles_skipped);
    }
    return n;
}

static void draw_status_icon(Level level, float cx, float cy)
{
    static const struct {
        u32 bg, fg;
        Icon icon;
    } look[] = {
        [LEVEL_OK] = {COL_GREEN_BG, COL_GREEN_TEXT, ICON_CHECK},
        [LEVEL_INFO] = {COL_BLUE_BG, COL_BLUE, ICON_INFO},
        [LEVEL_WARN] = {COL_YELLOW, COL_INK, ICON_WARN},
        [LEVEL_FAIL] = {COL_YELLOW, COL_INK, ICON_WARN},
    };
    ui_circle(cx, cy, 9, look[level].bg);
    ui_icon(look[level].icon, cx, cy, 12, look[level].fg);
}

static void draw_check_top(const App *app)
{
    Row rows[8];
    int n = check_rows(app, rows);
    ui_text(20, 14, 18, FONT_HEAVY, COL_INK, "Перевірка консолі");
    float step = n > 5 ? 30 : 34;
    for (int i = 0; i < n; i++) {
        float y = 44 + i * step;
        bool bad = rows[i].level == LEVEL_FAIL;
        ui_card(20, y, 360, step - 4, 8, bad ? COL_AMBER_BG : COL_CARD, 0);
        draw_status_icon(rows[i].level, 39, y + (step - 4) / 2);
        ui_text(56, y + (step - 4) / 2 - 8, 12, bad ? FONT_HEAVY : FONT_BOLD, COL_INK, rows[i].label);
        u32 vc = bad ? COL_AMBER_TEXT : rows[i].level == LEVEL_INFO ? COL_BLUE : COL_MUTED;
        ui_text_right(370, y + (step - 4) / 2 - 7, 11, bad || rows[i].level == LEVEL_INFO ? FONT_HEAVY : FONT_BOLD, vc,
                      rows[i].value);
    }
}

static const char *blocking_reason(const Console *c, const char **title)
{
    *title = "Потрібна дія";
    if (!c->is_luma)
        return "Не знайдено Luma3DS. Встановіть її за інструкцією 3ds.hacks.guide.";
    if (c->luma_version < LUMA_MIN)
        return "Ця версія Luma3DS застара. Оновіть її за інструкцією 3ds.hacks.guide.";
    if (!c->region_ok)
        return "Українізатор поки є лише для консолей європейського регіону (EUR).";
    if (c->sd_free < SD_NEEDED)
        return "Звільніть на SD-карті щонайменше 40 МБ.";
    *title = "Майже готово";
    return "Встановлення не можна переривати. Підключіть зарядку — і можна починати.";
}

static Rect check_button = {14, 112, 292, 60};

static void draw_check_bottom(const App *app)
{
    const Console *c = &app->console;
    bool ok = checks_blocking(c) != LEVEL_FAIL;
    const char *title = "Усе гаразд", *text = "Консоль готова до українізації.";
    if (!ok)
        text = blocking_reason(c, &title);
    ui_card(14, 14, 292, 88, 11, COL_CARD, 0);
    ui_icon(ok ? ICON_SHIELD : ICON_WARN, 14 + 12 + 14, 14 + 24, 28, ok ? COL_GREEN : COL_AMBER);
    ui_text(66, 22, 14, FONT_HEAVY, COL_INK, title);
    ui_text_wrap(66, 42, 230, 11.5f, FONT_BOLD, COL_BODY, text);
    bool charger = !ok && c->is_luma && c->luma_version >= LUMA_MIN && c->region_ok && c->sd_free >= SD_NEEDED;
    draw_primary(check_button, ICON_CHECK, ok ? "Продовжити" : charger ? "Чекаю на зарядку…" : "Вийти", NULL, ok);
    draw_hints("B", "Назад", NULL, NULL);
}

static void update_check(App *app, const Input *in)
{
    const Console *c = &app->console;
    bool ok = checks_blocking(c) != LEVEL_FAIL;
    bool charger = !ok && c->is_luma && c->luma_version >= LUMA_MIN && c->region_ok && c->sd_free >= SD_NEEDED;
    bool pressed = (in->down & KEY_A) || hit(in, check_button);

    if (ok && pressed) {
        if (!run_auto(app))
            go(app, app->back == SCREEN_CHECK ? home_screen(app) : app->back);
    } else if (!ok && !charger && pressed) {
        app->quit = true;
    } else if (in->down & KEY_B) {
        if (ok) {
            app->screen = app->back;
            app->focus = 0;
        } else {
            app->quit = true;
        }
    }
}

/* ---------------------------------------------------------------- main */

static Rect main_install = {14, 14, 292, 80}, main_check = {14, 102, 142, 58}, main_help = {164, 102, 142, 58};
static Rect main_exit = {14, 168, 292, 38};

static void draw_main_top(const App *app)
{
    const Console *c = &app->console;
    char luma[24], size[24], buf[48];
    draw_header(app, NULL, 0, false);
    ui_card(22, 80, 356, 84, 10, COL_CARD, 1);
    ui_circle(40, 96, 4, COL_FAINT);
    ui_text(50, 87, 14, FONT_HEAVY, COL_INK, "Ще не встановлено");
    ui_text_wrap(36, 110, 330, 12, FONT_BOLD, COL_BODY,
                 "Українізація всієї системи консолі. Займе кілька хвилин, потім консоль перезавантажиться сама.");

    float x = 22;
    checks_luma_string(c, luma, sizeof(luma));
    snprintf(buf, sizeof(buf), "Luma %s", luma + 1);
    draw_chip(&x, 178, buf, c->is_luma && c->luma_version >= LUMA_FULL);
    draw_chip(&x, 178, "EUR", c->region_ok);
    checks_size_string(c->sd_free, size, sizeof(size));
    snprintf(buf, sizeof(buf), "%s вільно", size);
    draw_chip(&x, 178, buf, c->sd_free >= SD_NEEDED);
    draw_chip(&x, 178, "Заряд", c->battery >= BATTERY_MIN || c->charging);
    if (app->stats.enabled)
        ui_text(24, 212, 10, FONT_BOLD, COL_FAINT, "Анонімна статистика увімкнена — змінити в Допомозі");
}

static void draw_main_bottom(const App *app)
{
    (void)app;
    draw_primary(main_install, ICON_DOWNLOAD, "Встановити", "кілька хвилин", true);
    draw_tile(main_check, ICON_LIST, "Перевірка", COL_INK, true);
    draw_tile(main_help, ICON_HELP, "Допомога", COL_INK, true);
    draw_exit(main_exit);
}

/* Install or update: an update keeps the slot of the last install; a first install, or a
 * copy installed without the app, asks. */
static void start_install(App *app)
{
    if (checks_blocking(&app->console) == LEVEL_FAIL)
        go(app, SCREEN_CHECK);
    else if (app->has_installed)
        start_op(app, OP_INSTALL, app->installed.slot, wanted_glyphs(app));
    else
        go(app, SCREEN_SLOT);
}

static void update_main(App *app, const Input *in)
{
    if ((in->down & KEY_A) || hit(in, main_install))
        start_install(app);
    else if ((in->down & KEY_Y) || hit(in, main_check))
        go(app, SCREEN_CHECK);
    else if (hit(in, main_help))
        go(app, SCREEN_HELP);
    else if (hit(in, main_exit))
        app->quit = true;
}

/* ---------------------------------------------------------------- slot */

static Rect slot_card[2] = {{14, 14, 292, 80}, {14, 103, 292, 80}};

static void draw_slot_top(const App *app)
{
    (void)app;
    ui_text_wrap(24, 20, 352, 19, FONT_HEAVY, COL_INK, "Яку мову замінить українська?");
    ui_text_wrap(24, 78, 352, 12.5f, FONT_BOLD, COL_BODY,
                 "У консолі немає вільного місця для нової мови, тож українська стає на місце однієї з наявних. "
                 "Решта мов лишається.");
    ui_card(24, 180, 352, 36, 8, COL_CARD, 0);
    ui_icon(ICON_UPDATE, 44, 198, 15, COL_BLUE);
    ui_text(60, 191, 11, FONT_BOLD, COL_BODY, "Змінити можна будь-коли, без перевстановлення.");
}

static void draw_slot_bottom(const App *app)
{
    static const char *code[2] = {"RU", "EN"};
    static const char *title[2] = {"Замість російської", "Замість англійської"};
    static const char *note[2] = {"«Русский» зникне зі списку мов", "«English» зникне зі списку мов"};
    for (int i = 0; i < 2; i++) {
        Rect r = slot_card[i];
        bool on = app->focus == i;
        ui_rrect(r.x, r.y, r.w, r.h, 12, on ? COL_BLUE : COL_DISABLED);
        ui_rrect(r.x + 2, r.y + 2, r.w - 4, r.h - 4, 10, COL_CARD);
        ui_rrect(r.x + 15, r.y + r.h / 2 - 18, 36, 36, 9, on ? COL_BLUE_BG : COL_LINE);
        ui_text_center(r.x + 33, r.y + r.h / 2 - 10, 15, FONT_HEAVY, on ? COL_BLUE : COL_BODY, code[i]);
        ui_text(r.x + 64, r.y + r.h / 2 - 18, 16, FONT_HEAVY, COL_INK, title[i]);
        ui_text(r.x + 64, r.y + r.h / 2 + 4, 10.5f, FONT_BOLD, COL_MUTED, note[i]);
    }
    draw_hints("B", "Назад", "A", "Вибрати");
}

static void choose_slot(App *app, int slot)
{
    app->slot = slot ? SLOT_EN : SLOT_RU;
    start_op(app, OP_INSTALL, app->slot, wanted_glyphs(app));
}

static void update_slot(App *app, const Input *in)
{
    for (int i = 0; i < 2; i++)
        if (hit(in, slot_card[i]))
            choose_slot(app, i);
    if (app->screen == SCREEN_SLOT && (in->down & KEY_B))
        go(app, home_screen(app));
}

/* ---------------------------------------------------------------- progress */

typedef struct {
    Stage stage;
    const char *label;
} Step;

static const Step INSTALL_STEPS[] = {
    {STAGE_CHECK, "Перевірка"},          {STAGE_BACKUP, "Резервні копії"},     {STAGE_FILES, "Файли перекладу"},
    {STAGE_FONT, "Шрифт системи"},       {STAGE_LUMA, "Налаштування Luma"},    {STAGE_FINISH, "Завершення"},
};
static const Step REMOVE_STEPS[] = {
    {STAGE_CHECK, "Перевірка"},          {STAGE_FILES, "Файли перекладу"},     {STAGE_FONT, "Шрифт системи"},
    {STAGE_BACKUP, "Резервні копії"},    {STAGE_LUMA, "Налаштування Luma"},    {STAGE_FINISH, "Завершення"},
};
#define STEP_COUNT 6

static const Step *progress_steps(const App *app)
{
    return app->op == OP_REMOVE ? REMOVE_STEPS : INSTALL_STEPS;
}

/* The step under way, and how far the whole operation is (0..1). */
static int progress_state(const App *app, float *fraction)
{
    const Step *steps = progress_steps(app);
    const Job *j = &app->worker.job;
    if (!app->working) {
        *fraction = 1;
        return STEP_COUNT - 1;
    }
    int at = 0;
    for (int i = 0; i < STEP_COUNT; i++)
        if (steps[i].stage == j->stage)
            at = i;
    float sub = steps[at].stage == STAGE_FILES && j->total > 0 ? (float)j->done / (float)j->total : 0;
    /* the files are most of the work: give them half the ring */
    float weight[STEP_COUNT];
    float sum = 0, before = 0;
    for (int i = 0; i < STEP_COUNT; i++) {
        weight[i] = steps[i].stage == STAGE_FILES ? 5 : 1;
        sum += weight[i];
        if (i < at)
            before += weight[i];
    }
    *fraction = (before + weight[at] * sub) / sum;
    return at;
}

static void draw_progress_top(const App *app)
{
    const Step *steps = progress_steps(app);
    float fraction;
    int at = progress_state(app, &fraction);
    char pct[8];
    snprintf(pct, sizeof(pct), "%d%%", (int)(fraction * 100));
    ui_ring(82, 120, 60, 49, fraction, COL_BLUE, COL_TRACK);
    /* the digits on the ring's centre, the caption under them (measured on the console: the
     * digits' ink sits 25 px below the text origin at 32 px, the caption's 12 px at 11 px) */
    ui_text_center(82, 95, 32, FONT_HEAVY, COL_INK, pct);
    ui_text_center(82, 132, 11, FONT_BOLD, COL_MUTED,
                   app->op == OP_REMOVE ? "видалення" : app->finishing ? "завершення" : "встановлення");
    for (int i = 0; i < STEP_COUNT; i++) {
        float y = 34 + i * 30;
        if (i < at) {
            ui_circle(172.5f, y + 10.5f, 8.5f, COL_GREEN);
            ui_icon(ICON_CHECK, 172.5f, y + 10.5f, 11, COL_WHITE);
            ui_text(190, y + 1, 12.5f, FONT_BOLD, COL_BODY, steps[i].label);
        } else if (i == at) {
            ui_circle(172.5f, y + 10.5f, 8.5f, COL_BLUE);
            ui_circle(172.5f, y + 10.5f, 3.5f, COL_WHITE);
            ui_text(190, y + 1, 12.5f, FONT_HEAVY, COL_INK, steps[i].label);
        } else {
            ui_rrect(164, y + 2, 17, 17, 8.5f, COL_TRACK);
            ui_rrect(166, y + 4, 13, 13, 6.5f, COL_BG);
            ui_text(190, y + 1, 12.5f, FONT_BOLD, COL_FAINT, steps[i].label);
        }
    }
}

static void draw_progress_bottom(const App *app)
{
    float fraction;
    progress_state(app, &fraction);
    ui_icon(ICON_POWER, 160, 46, 40, COL_BLUE);
    ui_text_center(160, 76, 17, FONT_HEAVY, COL_INK, "Не вимикайте консоль");
    const char *text = "Кнопка HOME тимчасово не працює. Коли все буде готово, консоль перезавантажиться сама.";
    float h = ui_text_wrap_height(270, 12, FONT_BOLD, text);
    float w = 270;
    ui_text_wrap((BOTTOM_W - w) / 2, 104, w, 12, FONT_BOLD, COL_BODY, text);
    ui_rrect(18, 120 + h, 284, 8, 4, COL_TRACK);
    if (fraction > 0)
        ui_rrect(18, 120 + h, 8 + 276 * fraction, 8, 4, COL_BLUE);
}

static void update_progress(App *app, const Input *in)
{
    (void)app;
    (void)in;
}

/* ---------------------------------------------------------------- done */

static Rect done_button = {14, 104, 292, 64};

static void draw_done_top(const App *app)
{
    char line[64];
    bool removed = app->op == OP_REMOVE;
    ui_circle(46, 42, 24, COL_GREEN);
    ui_icon(ICON_CHECK, 46, 42, 28, COL_WHITE);
    ui_text(84, 18, 22, FONT_HEAVY, COL_INK, removed ? "Українізатор видалено" : "Готово!");
    ui_text(84, 46, 13, FONT_BOLD, COL_BODY, removed ? "Консоль повернеться до звичайного вигляду." : "Консоль українізовано.");
    if (removed) {
        ui_card(24, 84, 352, 112, 10, COL_CARD, 0);
        ui_text(38, 99, 12, FONT_BOLD, COL_MUTED, "Мова консолі");
        ui_text_right(362, 99, 12, FONT_HEAVY, COL_INK, checks_language_name(app->console.language));
        ui_rect(38, 124, 324, 1, COL_LINE);
        ui_text_wrap(38, 134, 324, 11.5f, FONT_BOLD, COL_BODY,
                     "Змінити мову: Налаштування системи → Інші налаштування → Мова.");
    } else {
        ui_card(24, 84, 352, 112, 10, COL_CARD, 0);
        snprintf(line, sizeof(line), "Українська, замість %s", app->op_slot == SLOT_EN ? "англійської" : "російської");
        const char *labels[3] = {"Мова", "Перекладено", "Версія"};
        const char *values[3] = {line, app->worker.job.skipped ? "майже вся система" : "уся система",
                                 app->manifest_ok ? app->manifest.version : "?"};
        for (int i = 0; i < 3; i++) {
            float y = 92 + i * 34;
            ui_text(38, y + 7, 12, FONT_BOLD, COL_MUTED, labels[i]);
            ui_text_right(362, y + 7, 12, FONT_HEAVY, COL_INK, values[i]);
            if (i < 2)
                ui_rect(38, y + 32, 324, 1, COL_LINE);
        }
    }
    draw_telegram_line(24, 212, "Новини й нові версії — t.me/side_quest_ua");
}

static void draw_done_bottom(const App *app)
{
    char countdown[48];
    ui_rrect(14, 14, 292, 78, 11, COL_BLUE_BG);
    ui_icon(ICON_INFO, 36, 34, 18, COL_BLUE);
    ui_text_wrap(56, 22, 240, 11.5f, FONT_BOLD, COL_INK,
                 app->op == OP_REMOVE ? "Щоб зміни набули сили, консоль зараз перезавантажиться. Застосунок лишається в Меню HOME."
                                      : "Щоб українська запрацювала всюди, консоль зараз перезавантажиться. Відкривати застосунок "
                                        "знову не потрібно.");
    u64 now = osGetTime();
    int left = app->reboot_at > now ? (int)((app->reboot_at - now + 999) / 1000) : 1;
    snprintf(countdown, sizeof(countdown), "автоматично через %d с", left);
    draw_primary(done_button, ICON_POWER, "Перезавантажити", app->rebooting ? "перезавантаження…" : countdown, true);
    draw_hints("A", "Перезавантажити зараз", NULL, NULL);
}

static void update_done(App *app, const Input *in)
{
    if (((in->down & KEY_A) || hit(in, done_button)) && !app->rebooting && app->reboot_at > osGetTime())
        app->reboot_at = osGetTime(); /* app_update() reboots on the next frame */
}

/* ---------------------------------------------------------------- installed */

static Rect inst_update = {14, 14, 292, 60};
static Rect inst_tile[4] = {{14, 84, 142, 48}, {164, 84, 142, 48}, {14, 139, 142, 48}, {164, 139, 142, 48}};
static Rect inst_exit = {14, 195, 292, 34};

/* The installed copy is this app's version: nothing to update, only to repair. */
static bool up_to_date(const App *app)
{
    return app->has_installed && app->manifest_ok && !strcmp(app->installed.version, app->manifest.version);
}

static void draw_installed_top(const App *app)
{
    char line[64];
    if (up_to_date(app)) {
        draw_header(app, "Українізатор встановлено", COL_GREEN_TEXT, true);
        ui_rrect(22, 82, 356, 92, 10, COL_GREEN_BG);
        ui_rrect(36, 100, 36, 36, 10, COL_GREEN);
        ui_icon(ICON_CHECK, 54, 118, 20, COL_WHITE);
        snprintf(line, sizeof(line), "Версія %s — актуальна", app->installed.version);
        ui_text(84, 94, 15, FONT_HEAVY, COL_INK, line);
        ui_text_wrap(84, 116, 280, 11.5f, FONT_BOLD, COL_BODY,
                     "Якщо щось працює не так, встановіть ще раз: це безпечно.");
    } else {
        draw_header(app, "Знайдено встановлений українізатор", COL_GREEN_TEXT, true);
        ui_rrect(22, 82, 356, 92, 10, COL_AMBER_BG);
        ui_rrect(36, 100, 36, 36, 10, COL_YELLOW);
        ui_icon(ICON_UPDATE, 54, 118, 20, COL_INK);
        snprintf(line, sizeof(line), "Версія %s у застосунку", app->manifest_ok ? app->manifest.version : "?");
        ui_text(84, 94, 15, FONT_HEAVY, COL_INK, line);
        ui_text_wrap(84, 116, 280, 11.5f, FONT_BOLD, COL_BODY,
                     "Нові переклади й виправлення. Застосунок уже містить усе потрібне, мережа не знадобиться.");
    }
    draw_telegram_line(22, 212, "Новини проєкту — t.me/side_quest_ua");
}

static void draw_installed_bottom(const App *app)
{
    draw_primary(inst_update, ICON_UPDATE, up_to_date(app) ? "Встановити ще раз" : "Оновити", NULL, true);
    draw_tile(inst_tile[0], ICON_SWAP, "Змінити слот", COL_INK, false);
    draw_tile(inst_tile[1], ICON_LIST, "Перевірка", COL_INK, false);
    draw_tile(inst_tile[2], ICON_HELP, "Допомога", COL_INK, false);
    draw_tile(inst_tile[3], ICON_TRASH, "Видалити", COL_RED, false);
    draw_exit(inst_exit);
}

static void update_installed(App *app, const Input *in)
{
    if ((in->down & KEY_A) || hit(in, inst_update))
        start_install(app);
    else if (hit(in, inst_tile[0]))
        go(app, checks_blocking(&app->console) == LEVEL_FAIL ? SCREEN_CHECK : SCREEN_SLOT);
    else if ((in->down & KEY_Y) || hit(in, inst_tile[1]))
        go(app, SCREEN_CHECK);
    else if (hit(in, inst_tile[2]))
        go(app, SCREEN_HELP);
    else if (hit(in, inst_tile[3]))
        go(app, SCREEN_CONFIRM);
    else if (hit(in, inst_exit))
        app->quit = true;
}

/* ---------------------------------------------------------------- rescue */

static Rect rescue_button = {14, 112, 292, 56};

/* Three numbered steps on cards: the Luma boot menu by hand. */
static void draw_steps(const char *title, const char *const steps[3])
{
    ui_text(20, 14, 17, FONT_HEAVY, COL_INK, title);
    for (int i = 0; i < 3; i++) {
        float y = 46 + i * 60;
        char n[2] = {(char)('1' + i), 0};
        ui_card(20, y, 360, 52, 8, COL_CARD, 0);
        ui_circle(42, y + 26, 11, COL_BLUE);
        ui_text_center(42, y + 18, 12, FONT_HEAVY, COL_WHITE, n);
        float h = ui_text_wrap_height(306, 12, FONT_BOLD, steps[i]);
        ui_text_wrap(62, y + 26 - h / 2, 306, 12, FONT_BOLD, COL_INK, steps[i]);
    }
}

static void draw_rescue_top(const App *app)
{
    (void)app;
    static const char *const steps[3] = {
        "Вимкніть консоль. Тримайте SELECT і ввімкніть її.",
        "Зніміть галочку Enable loading external FIRMs and modules",
        "Натисніть START — консоль запуститься.",
    };
    draw_steps("Якщо консоль не запускається", steps);
}

static void draw_rescue_bottom(const App *app)
{
    (void)app;
    ui_card(14, 14, 292, 88, 11, COL_CARD, 0);
    ui_icon(ICON_SHIELD, 40, 40, 26, COL_GREEN);
    ui_text(64, 22, 13.5f, FONT_HEAVY, COL_INK, "Нічого не зламано");
    ui_text_wrap(64, 42, 232, 11.5f, FONT_BOLD, COL_BODY,
                 "Системні файли консолі не змінювалися. Після запуску відкрийте цей застосунок — він сам усе виправить.");
    draw_primary(rescue_button, ICON_CHECK, "Зрозуміло", NULL, true);
}

static void update_rescue(App *app, const Input *in)
{
    if ((in->down & (KEY_A | KEY_B)) || hit(in, rescue_button))
        app->screen = app->back, app->focus = 0;
}

/* ---------------------------------------------------------------- help */

static Rect help_row[3] = {{14, 14, 292, 52}, {14, 74, 292, 52}, {14, 134, 292, 52}};

static void draw_help_top(const App *app)
{
    const float module = 4, quiet = 10, size = QR_SIZE * module + 2 * quiet;
    float x0 = 18, y0 = (SCREEN_H - size) / 2;
    ui_card(x0, y0, size, size, 12, COL_WHITE, 1.5f);
    for (int y = 0; y < QR_SIZE; y++)
        for (int x = 0; x < QR_SIZE; x++)
            if (QR_ROWS[y][x] == '#')
                ui_rect(x0 + quiet + x * module, y0 + quiet + y * module, module, module, COL_INK);

    float tx = x0 + size + 18, tw = TOP_W - tx - 18;
    ui_text_wrap(tx, 40, tw, 19, FONT_HEAVY, COL_INK, "Щось пішло не так?");
    ui_text_wrap(tx, 72, tw, 12, FONT_BOLD, COL_BODY,
                 "Напишіть у наш Telegram-канал — там можна запитати про будь-яку проблему з українізатором.");
    ui_card(tx, 162, tw, 32, 7, COL_CARD, 0);
    ui_icon(ICON_TELEGRAM, tx + 17, 178, 15, COL_TELEGRAM);
    ui_text(tx + 32, 170, 13, FONT_HEAVY, COL_INK, QR_URL);

    /* small on purpose: for a photo of this screen sent to us, not for reading */
    char id[REPORT_ID_LEN + 2], line[24];
    report_id_display(app->stats.id, id);
    snprintf(line, sizeof(line), "ID %s", id);
    ui_text(TOP_W - 10 - ui_text_width(9, FONT_BOLD, line), SCREEN_H - 16, 9, FONT_BOLD, COL_MUTED, line);
}

/* The statistics box: a tile with a tick on its right. */
static void draw_stats_tile(Rect r, bool on)
{
    draw_tile(r, ICON_SHIELD, "Анонімна статистика", COL_INK, false);
    float bx = r.x + r.w - 38, by = r.y + (r.h - 24) / 2;
    if (on) {
        ui_rrect(bx, by, 24, 24, 6, COL_GREEN);
        ui_icon(ICON_CHECK, bx + 12, by + 12, 14, COL_WHITE);
    } else {
        ui_rrect(bx, by, 24, 24, 6, COL_FAINT);
        ui_rrect(bx + 2, by + 2, 20, 20, 5, COL_WHITE);
    }
}

static void draw_help_bottom(const App *app)
{
    draw_tile(help_row[0], ICON_POWER, "Консоль не запускається", COL_INK, false);
    draw_tile(help_row[1], ICON_LIST, "Перевірити консоль", COL_INK, false);
    draw_stats_tile(help_row[2], app->stats.enabled);
    draw_hints("B", "Назад", NULL, NULL);
}

static void update_help(App *app, const Input *in)
{
    if (hit(in, help_row[0]))
        go(app, SCREEN_RESCUE);
    else if (hit(in, help_row[1]))
        go(app, SCREEN_CHECK);
    else if (hit(in, help_row[2]))
        stats_set_enabled(&app->stats, !app->stats.enabled);
    else if (in->down & KEY_B)
        app->screen = app->back, app->focus = 0;
}

/* ---------------------------------------------------------------- confirm removal */

static Rect confirm_remove = {14, 14, 292, 60}, confirm_cancel = {14, 84, 292, 52};

static void draw_confirm_top(const App *app)
{
    ui_circle(46, 42, 24, COL_RED);
    ui_icon(ICON_TRASH, 46, 42, 24, COL_WHITE);
    ui_text(84, 18, 20, FONT_HEAVY, COL_INK, "Видалити українізатор?");
    ui_text(84, 46, 12, FONT_BOLD, COL_BODY, "Консоль перезавантажиться сама.");
    ui_card(24, 84, 352, 116, 10, COL_CARD, 0);
    char text[512];
    snprintf(text, sizeof(text),
             "Усе, що застосунок замінив, буде повернено, і консоль показуватиме мову з Налаштувань системи: %s. "
             "Сам застосунок лишиться: українізувати знову можна будь-коли.",
             checks_language_name(app->console.language));
    ui_text_wrap(40, 98, 320, 12, FONT_BOLD, COL_BODY, text);
}

static void draw_confirm_bottom(const App *app)
{
    (void)app;
    ui_rrect(confirm_remove.x, confirm_remove.y + 3, confirm_remove.w, confirm_remove.h, 14, RGBA(0x7A, 0x14, 0x0E, 0xFF));
    ui_rrect(confirm_remove.x, confirm_remove.y, confirm_remove.w, confirm_remove.h, 14, COL_RED);
    ui_icon(ICON_TRASH, confirm_remove.x + 30, confirm_remove.y + confirm_remove.h / 2, 24, COL_WHITE);
    ui_text(confirm_remove.x + 54, confirm_remove.y + confirm_remove.h / 2 - 12, 19, FONT_HEAVY, COL_WHITE, "Видалити");
    draw_tile(confirm_cancel, ICON_CHECK, "Залишити як є", COL_INK, false);
    draw_hints("B", "Скасувати", NULL, NULL);
}

static void update_confirm(App *app, const Input *in)
{
    if (hit(in, confirm_remove))
        start_op(app, OP_REMOVE, app->has_installed ? app->installed.slot : SLOT_RU, GLYPHS_DEFAULT);
    else if ((in->down & KEY_B) || hit(in, confirm_cancel))
        go(app, home_screen(app));
}

/* ---------------------------------------------------------------- error */

static Rect error_button = {14, 112, 292, 56};

static void draw_error_top(const App *app)
{
    ui_circle(46, 42, 24, COL_YELLOW);
    ui_icon(ICON_WARN, 46, 42, 26, COL_INK);
    ui_text_wrap(84, 18, 300, 19, FONT_HEAVY, COL_INK, app->error_title ? app->error_title : "");
    ui_card(24, 84, 352, 100, 10, COL_CARD, 0);
    ui_text_wrap(40, 98, 320, 12.5f, FONT_BOLD, COL_BODY, app->error_text ? app->error_text : "");
    if (app->error_retry && app->worker.job.error[0])
        ui_text_wrap(40, 160, 320, 9.5f, FONT_BOLD, COL_FAINT, app->worker.job.error);
    draw_telegram_line(24, 212, "Допомога — t.me/side_quest_ua");
}

static void draw_error_bottom(const App *app)
{
    if (app->error_retry) {
        ui_card(14, 14, 292, 88, 11, COL_CARD, 0);
        ui_icon(ICON_SHIELD, 40, 40, 26, COL_GREEN);
        ui_text(64, 22, 13.5f, FONT_HEAVY, COL_INK, "Нічого не зламано");
        ui_text_wrap(64, 42, 232, 11.5f, FONT_BOLD, COL_BODY,
                     "Застосунок продовжить з того самого місця — зараз або під час наступного запуску.");
        draw_primary(error_button, ICON_UPDATE, "Спробувати ще раз", NULL, true);
        draw_hints("B", "Вийти", NULL, NULL);
    } else {
        draw_primary(error_button, ICON_CHECK, "Зрозуміло", NULL, true);
    }
}

static void update_error(App *app, const Input *in)
{
    bool pressed = (in->down & KEY_A) || hit(in, error_button);
    if (app->error_retry && pressed)
        start_op(app, app->op, app->op_slot, app->op_glyphs);
    else if (pressed || (in->down & KEY_B))
        app->quit = true;
}

/* ---------------------------------------------------------------- Luma game patching */

/* The mod is on the card but game patching is off, so none of it runs. With a config.ini
 * the app understands it switches the flag itself and reboots; otherwise (Luma before v13
 * keeps its settings in config.bin) the steps by hand - Luma reads SELECT at every boot,
 * so the reboot here is also the way into its menu. */
static Rect luma_button = {14, 112, 292, 60};

static void draw_luma_top(const App *app)
{
    if (app->console.config_editable) {
        ui_text(20, 14, 17, FONT_HEAVY, COL_INK, "Українізатор вимкнено в Luma");
        ui_card(20, 46, 360, 112, 8, COL_CARD, 0);
        ui_text_wrap(36, 62, 328, 12.5f, FONT_BOLD, COL_BODY,
                     "У налаштуваннях Luma знято галочку Enable game patching. Без неї українізатор не працює. "
                     "Застосунок увімкне її сам і перезавантажить консоль.");
        return;
    }
    static const char *const steps[3] = {
        "Натисніть «Перезавантажити» і тримайте SELECT, доки не з'явиться меню Luma.",
        "Позначте Enable game patching (кнопка A).",
        "Натисніть START — консоль запуститься українською.",
    };
    draw_steps("Увімкніть одне налаштування Luma", steps);
}

static void draw_luma_bottom(const App *app)
{
    bool editable = app->console.config_editable;
    ui_card(14, 14, 292, 88, 11, COL_CARD, 0);
    ui_icon(ICON_INFO, 40, 40, 24, COL_BLUE);
    ui_text(64, 22, 13.5f, FONT_HEAVY, COL_INK, "Майже готово");
    ui_text_wrap(64, 42, 232, 11.5f, FONT_BOLD, COL_BODY,
                 editable ? "Українізатор на місці, лишилося ввімкнути одне налаштування."
                          : "Українізатор на місці. Застосунок не може сам змінити це налаштування у вашій версії Luma.");
    const char *sub = app->rebooting ? "перезавантаження…" : editable ? "і перезавантажити" : "тримайте SELECT";
    draw_primary(luma_button, ICON_POWER, editable ? "Увімкнути" : "Перезавантажити", sub, true);
    draw_hints("B", "Пізніше", NULL, NULL);
}

/* Game patching on in luma/config.ini, exactly that one character; then reboot at once,
 * before Rosalina could save its own copy of the settings over it (§4.4). */
static bool enable_game_patching(void)
{
    uint8_t *text;
    size_t len;
    if (payload_read_file(SD_ROOT "/luma/config.ini", &text, &len))
        return false;
    LumaConfig flags;
    bool ok = !lumacfg_parse(&flags, (char *)text, len);
    if (ok) {
        *flags.game = '1';
        uint8_t sha[32];
        sha256(text, len, sha);
        ok = !fs_replace_verified(SD_ROOT "/luma/config.ini", text, len, sha);
    }
    free(text);
    return ok;
}

static void update_luma(App *app, const Input *in)
{
    if (((in->down & KEY_A) || hit(in, luma_button)) && !app->rebooting) {
        if (app->console.config_editable && !enable_game_patching()) {
            show_error(app, "Не вдалося змінити налаштування", "Файл luma/config.ini не вдалося записати.", false);
            return;
        }
        app->reboot_at = osGetTime();
    } else if (in->down & KEY_B) {
        go(app, home_screen(app));
    }
}

/* ---------------------------------------------------------------- dispatch */

void app_init(App *app)
{
    memset(app, 0, sizeof(*app));
    uint8_t *text;
    size_t len;
    if (!payload_read_file(MANIFEST_PATH, &text, &len)) {
        app->manifest_ok = manifest_parse(&app->manifest, (const char *)text, len) == 0;
        free(text);
    }
    checks_run(&app->console, app->manifest_ok ? &app->manifest : NULL);
    stats_init(&app->stats);

    /* a cut during an earlier run: finish the folder swaps it left before anything else */
    engine_recover(SD_ROOT);
    app->has_installed = engine_load_installed(SD_ROOT, &app->installed) == 0;
    if (app->has_installed) {
        app->slot = app->installed.slot;
        app->live_letters = install_live_letters();
    }

    app->back = home_screen(app);
    if (checks_blocking(&app->console) == LEVEL_FAIL)
        app->screen = SCREEN_CHECK;
    else if (!run_auto(app))
        app->screen = home_screen(app);
}

void app_exit(App *app)
{
    if (app->working) /* the app is closing (power, APT): let the worker reach a clean stop */
        while (!install_poll(&app->worker))
            svcSleepThread(10 * 1000 * 1000);
    stats_exit(&app->stats);
    if (app->has_installed)
        installed_free(&app->installed);
    if (app->manifest_ok)
        manifest_free(&app->manifest);
}

/* ---------------------------------------------------------------- buttons */

/* Everything on the touch screen can be reached with the D-pad and pressed with A, for
 * consoles whose touch screen no longer reads right. Each screen lists its controls; the
 * first is the one A presses without moving (the main action - on the removal question,
 * keeping things as they are). */
typedef struct {
    const Rect *r;
    float radius;
} Target;

static int screen_targets(const App *app, Target *t)
{
    int n = 0;
#define ADD(rect, rad) (t[n++] = (Target){&(rect), (rad)})
    switch (app->screen) {
    case SCREEN_CHECK: ADD(check_button, 14); break;
    case SCREEN_MAIN: ADD(main_install, 14); ADD(main_check, 11); ADD(main_help, 11); ADD(main_exit, 10); break;
    case SCREEN_SLOT: ADD(slot_card[0], 12); ADD(slot_card[1], 12); break;
    case SCREEN_DONE: ADD(done_button, 14); break;
    case SCREEN_INSTALLED:
        ADD(inst_update, 14);
        for (int i = 0; i < 4; i++)
            ADD(inst_tile[i], 11);
        ADD(inst_exit, 10);
        break;
    case SCREEN_RESCUE: ADD(rescue_button, 14); break;
    case SCREEN_HELP: ADD(help_row[0], 11); ADD(help_row[1], 11); ADD(help_row[2], 11); break;
    case SCREEN_CONFIRM: ADD(confirm_cancel, 11); ADD(confirm_remove, 14); break;
    case SCREEN_ERROR: ADD(error_button, 14); break;
    case SCREEN_LUMA: ADD(luma_button, 14); break;
    case SCREEN_PROGRESS: break;
    }
#undef ADD
    return n;
}

/* The next control in the pressed direction, the way the eye goes: the nearest row (or
 * column) by the gap between edges, and in it the one most nearly opposite. Up and down may
 * land on a control that shares no column only when nothing else is there; left and right
 * never leave the row.
 * (By centres alone, Down from "Встановити" jumped over the two tiles to the wide "Вийти".) */
static int move_focus(const Target *t, int n, int from, u32 keys)
{
    const Rect *a = t[from].r;
    bool vertical = keys & (KEY_DUP | KEY_DDOWN);
    int sign = keys & (KEY_DUP | KEY_DLEFT) ? -1 : 1;
    int best = from;
    float best_cost = 1e9f;
    for (int i = 0; i < n; i++) {
        if (i == from)
            continue;
        const Rect *b = t[i].r;
        float a0 = vertical ? a->y : a->x, a1 = a0 + (vertical ? a->h : a->w);
        float b0 = vertical ? b->y : b->x, b1 = b0 + (vertical ? b->h : b->w);
        float centre = sign * ((b0 + b1) / 2 - (a0 + a1) / 2);
        if (centre <= 1)
            continue; /* not that way */
        float gap = sign > 0 ? b0 - a1 : a0 - b1;
        float c0 = vertical ? a->x : a->y, c1 = c0 + (vertical ? a->w : a->h);
        float d0 = vertical ? b->x : b->y, d1 = d0 + (vertical ? b->w : b->h);
        bool shares_band = d0 < c1 && c0 < d1;
        if (!vertical && !shares_band)
            continue; /* left and right stay in the row: a full-width button has no neighbours */
        float across = (d0 + d1) / 2 - (c0 + c1) / 2;
        float cost = (shares_band ? 0 : 10000) + (gap > 0 ? gap : 0) * 10 + (across < 0 ? -across : across);
        if (cost < best_cost) {
            best_cost = cost;
            best = i;
        }
    }
    return best;
}

/* D-pad moves the focus; A becomes a tap on the focused control, so every screen keeps
 * one set of handlers for both. */
static Input with_buttons(App *app, const Input *in)
{
    Input out = *in;
    Target t[8];
    int n = screen_targets(app, t);
    if (in->tapped)
        app->keys_nav = false;
    if (!n)
        return out;
    if (app->focus >= n)
        app->focus = 0;
    u32 dpad = in->down & (KEY_DUP | KEY_DDOWN | KEY_DLEFT | KEY_DRIGHT);
    if (dpad) {
        if (app->keys_nav || app->screen == SCREEN_SLOT) /* the slot cards show focus anyway */
            app->focus = move_focus(t, n, app->focus, dpad);
        app->keys_nav = true; /* the first press only shows where the focus is */
    }
    if (in->down & KEY_A) {
        out.down &= ~KEY_A;
        out.tapped = true;
        out.tap_x = (int)(t[app->focus].r->x + t[app->focus].r->w / 2);
        out.tap_y = (int)(t[app->focus].r->y + t[app->focus].r->h / 2);
    }
    return out;
}

static void draw_focus(const App *app)
{
    Target t[8];
    int n = screen_targets(app, t);
    /* the slot cards show their choice themselves */
    if (!app->keys_nav || !n || app->focus >= n || app->screen == SCREEN_SLOT)
        return;
    const Rect *r = t[app->focus].r;
    ui_rrect(r->x - 3, r->y - 3, r->w + 6, r->h + 6, t[app->focus].radius + 3, COL_YELLOW);
}

void app_update(App *app, const Input *raw)
{
    static int frames;
    Input buttons = with_buttons(app, raw);
    const Input *in = &buttons;
    /* Waiting on the check screen - the charger, say: look again once a second. */
    if (app->screen == SCREEN_CHECK && ++frames % 60 == 0 && checks_blocking(&app->console) == LEVEL_FAIL)
        checks_run(&app->console, app->manifest_ok ? &app->manifest : NULL);
    if (app->working && app->worker.job.stage != app->last_stage) {
        app->last_stage = app->worker.job.stage;
        app->stage_ms[app->last_stage] = osGetTime();
    }
    if (app->working && install_poll(&app->worker))
        op_finished(app);
    if (app->reboot_at && osGetTime() >= app->reboot_at && !app->rebooting) {
        /* a report still on its way: hold the reboot a little, never more than STATS_WAIT_MS */
        if (!app->reboot_deadline)
            app->reboot_deadline = osGetTime() + STATS_WAIT_MS;
        if (stats_settled(&app->stats, app->reboot_deadline)) {
            app->rebooting = true;
            install_reboot();
        }
    }
    if (app->screen == SCREEN_PROGRESS)
        return; /* nothing to press while it works, START included */
    if (in->down & KEY_START) {
        app->quit = true;
        return;
    }
    switch (app->screen) {
    case SCREEN_CHECK: update_check(app, in); break;
    case SCREEN_MAIN: update_main(app, in); break;
    case SCREEN_SLOT: update_slot(app, in); break;
    case SCREEN_PROGRESS: update_progress(app, in); break;
    case SCREEN_DONE: update_done(app, in); break;
    case SCREEN_INSTALLED: update_installed(app, in); break;
    case SCREEN_RESCUE: update_rescue(app, in); break;
    case SCREEN_HELP: update_help(app, in); break;
    case SCREEN_CONFIRM: update_confirm(app, in); break;
    case SCREEN_ERROR: update_error(app, in); break;
    case SCREEN_LUMA: update_luma(app, in); break;
    }
}

void app_draw_top(const App *app)
{
    switch (app->screen) {
    case SCREEN_CHECK: draw_check_top(app); break;
    case SCREEN_MAIN: draw_main_top(app); break;
    case SCREEN_SLOT: draw_slot_top(app); break;
    case SCREEN_PROGRESS: draw_progress_top(app); break;
    case SCREEN_DONE: draw_done_top(app); break;
    case SCREEN_INSTALLED: draw_installed_top(app); break;
    case SCREEN_RESCUE: draw_rescue_top(app); break;
    case SCREEN_HELP: draw_help_top(app); break;
    case SCREEN_CONFIRM: draw_confirm_top(app); break;
    case SCREEN_ERROR: draw_error_top(app); break;
    case SCREEN_LUMA: draw_luma_top(app); break;
    }
}

void app_draw_bottom(const App *app)
{
    draw_focus(app); /* under the control: its edges show as a frame */
    switch (app->screen) {
    case SCREEN_CHECK: draw_check_bottom(app); break;
    case SCREEN_MAIN: draw_main_bottom(app); break;
    case SCREEN_SLOT: draw_slot_bottom(app); break;
    case SCREEN_PROGRESS: draw_progress_bottom(app); break;
    case SCREEN_DONE: draw_done_bottom(app); break;
    case SCREEN_INSTALLED: draw_installed_bottom(app); break;
    case SCREEN_RESCUE: draw_rescue_bottom(app); break;
    case SCREEN_HELP: draw_help_bottom(app); break;
    case SCREEN_CONFIRM: draw_confirm_bottom(app); break;
    case SCREEN_ERROR: draw_error_bottom(app); break;
    case SCREEN_LUMA: draw_luma_bottom(app); break;
    }
}
