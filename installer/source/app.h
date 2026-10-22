/* The installer's state and its screens (docs/plan/installer-app.md, §6). */
#ifndef APP_H
#define APP_H

#include <3ds.h>
#include <stdbool.h>

#include "checks.h"
#include "engine/state.h"
#include "install.h"
#include "payload/manifest.h"

typedef enum {
    SCREEN_CHECK,
    SCREEN_MAIN,
    SCREEN_SLOT,
    SCREEN_PROGRESS,
    SCREEN_DONE,
    SCREEN_INSTALLED,
    SCREEN_RESCUE,
    SCREEN_HELP,
    SCREEN_CONFIRM,     /* "remove the mod?" */
    SCREEN_ERROR,
} ScreenId;

typedef struct {
    u32 down;           /* keys pressed this frame */
    bool tapped;        /* the stylus left the bottom screen this frame... */
    int tap_x, tap_y;   /* ...here */
} Input;

typedef struct {
    ScreenId screen;
    ScreenId back;      /* where B leads from Help, Check, Rescue */
    Console console;
    Manifest manifest;
    bool manifest_ok;
    Slot slot;
    int focus;          /* the highlighted choice on screens that have one */
    bool quit;

    Installed installed;    /* 3ds/3ds-ua/installed.txt, when has_installed */
    bool has_installed;
    bool live_letters;      /* the font NS loaded at boot has і ї є ґ */

    Worker worker;          /* the running or last operation */
    bool working;
    Op op;
    Slot op_slot;
    Glyphs op_glyphs;
    bool finishing;         /* the second half of an install, after the first reboot */
    int reboot_frames;      /* counting down to the reboot after a finished operation */
    u64 stage_ms[STAGE_COUNT + 1];  /* osGetTime() when each stage began, and at the end */
    int last_stage;
    bool rebooting;

    const char *error_title, *error_text;
    bool error_retry;       /* the error screen offers to run the operation again */
} App;

void app_init(App *app);
void app_exit(App *app);
void app_update(App *app, const Input *in);
void app_draw_top(const App *app);
void app_draw_bottom(const App *app);

#endif
