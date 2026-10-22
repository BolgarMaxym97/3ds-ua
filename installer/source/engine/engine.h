/*
 * Installing, updating and removing the mod on the card (docs/plan/installer-app.md, §4, §8).
 *
 * Portable C over stdio (fsutil.h): the console passes "sdmc:" and "romfs:/data", the host
 * tests a temporary directory, and everything that needs the console itself - which title
 * builds are installed, building the font from the console's own - comes in as callbacks.
 *
 * Safety, in order of the work:
 *  - pending.txt is written before the first change and removed after the last; an
 *    interrupted run leaves it, and the app finishes the same operation on its next start
 *    after engine_recover() has tidied the half-done folder swap;
 *  - every luma/titles/<TID> folder is staged whole in <TID>.3dsua-new and swapped in with
 *    two renames, so a title always sees a complete old or new set (or none: the stock
 *    title); the HOME Menu's folder goes last;
 *  - every file is checked against its sha256 after it is written;
 *  - files that are not the mod's are copied to 3ds/3ds-ua/backup/ before anything else
 *    and put back by a removal;
 *  - installed.txt is written last.
 */
#ifndef ENGINE_H
#define ENGINE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "../payload/manifest.h"
#include "state.h"

typedef enum {
    STAGE_CHECK,
    STAGE_BACKUP,
    STAGE_FILES,
    STAGE_FONT,
    STAGE_LUMA,
    STAGE_FINISH,
    STAGE_COUNT,
} Stage;

typedef enum {
    ENGINE_OK = 0,
    ENGINE_E_STATE,     /* installed.txt or the card's folders are not what the engine expects */
    ENGINE_E_PAYLOAD,   /* a file of the app does not restore */
    ENGINE_E_WRITE,     /* the card refused a write, or a written file reads back different */
    ENGINE_E_MEMORY,
} EngineStatus;

typedef bool (*NeedFn)(const Need *need, void *ctx);
/* The built font, malloc()ed, or NULL when it cannot be built on this console. */
typedef uint8_t *(*FontFn)(void *ctx, size_t *len);

typedef struct {
    /* in */
    const Manifest *m;
    const char *data_root;      /* the directory holding manifest.txt */
    const char *sd_root;        /* "sdmc:" */
    Op op;
    Slot slot;
    Model model;
    Glyphs glyphs;              /* GLYPHS_REAL: used only if the font goes on in the same run */
    bool want_font;             /* the console qualifies for the NS font patch (§3) */
    bool luma_game_on;          /* the running Luma's flags, for a config.ini the engine cannot read */
    bool luma_external_on;
    NeedFn need_met;
    FontFn build_font;
    void *ctx;
    uint64_t (*clock_ms)(void); /* optional: time the files stage for the log */
    void (*trace)(void *ctx, const char *path, uint32_t size, uint64_t restore_ms, uint64_t write_ms); /* optional */

    /* progress, for the UI thread */
    volatile int stage;
    volatile int done, total;

    /* out */
    int skipped;                /* folders left out: the title is another build */
    int kept;                   /* files a removal left because they were changed since */
    bool font;                  /* the font is on the card after the run */
    Glyphs glyphs_set;          /* the text variant that went on */
    bool luma_manual;           /* game patching is off and config.ini could not be edited */
    uint64_t restore_ms, write_ms; /* files stage: inflating/patching vs writing (clock_ms) */
    int moved;                  /* files of the files stage moved over unchanged, not written */
    char error[160];
} Job;

EngineStatus engine_run(Job *job);

/* Tidies what an interrupted run left: finishes or drops a half-done folder swap and
 * removes staging. Run before repeating the pending operation. */
EngineStatus engine_recover(const char *sd_root);

/* 0 and a parsed state, or -1 when there is none (or it does not parse). */
int engine_load_installed(const char *sd_root, Installed *s);
int engine_load_pending(const char *sd_root, Pending *p);

#endif
