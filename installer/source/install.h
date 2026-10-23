/*
 * The console's side of an install: runs engine_run() on a worker thread with the HOME
 * button, sleep and background downloads held off, answers the engine's questions (which
 * title builds are installed, the font built from the console's own), and reboots.
 */
#ifndef INSTALL_H
#define INSTALL_H

#include <3ds.h>
#include <stdbool.h>

#include "checks.h"
#include "engine/engine.h"

#define DATA_ROOT "romfs:/data"
#define SD_ROOT "sdmc:"

typedef struct {
    Job job;
    Thread thread;
    volatile bool running;
    EngineStatus status;
    const char *font_note;  /* why the font did not go on, for the log; NULL if it did */
    /* the font, built on a thread of its own while the files are written */
    Thread font_thread;
    uint8_t *stock, *upturn;    /* its inputs, read before the threads start */
    size_t stock_len, upturn_len;
    uint8_t *font;
    size_t font_len;
} Worker;

/* The console qualifies for the NS font patch: Luma reads sysmodule patches (v13+) and NS
 * is the build the patch is for. `font_before`: the last install put the font on; if the
 * user has since turned external modules off, that was the rescue - leave it off. */
bool install_font_allowed(const Console *c, bool font_before);

/* The sha256 of the font this app builds, from its upturn.bin. */
bool install_font_sha(const Manifest *m, uint8_t sha[32]);

/* Starts the worker; false if the thread could not start. `build_font`: the font is not on
 * the card yet, start building it right away. */
bool install_start(Worker *w, const Manifest *m, const Console *c, Op op, Slot slot, Glyphs glyphs, bool want_font,
                   bool build_font);
/* True once the worker has finished (and has been joined). */
bool install_poll(Worker *w);

/* The live system font has і ї є ґ (and their capitals, and ʼ): NS loaded ours at boot. */
bool install_live_letters(void);

/* Reboot the console (to the HOME Menu). */
void install_reboot(void);

#endif
