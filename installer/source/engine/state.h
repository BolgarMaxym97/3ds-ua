/*
 * What the installer leaves on the card about itself, in the manifest's plain-text style:
 *
 * 3ds/3ds-ua/installed.txt - written last by an install: its presence means "installed"
 *     3DSUA-INSTALLED 1
 *     version <x.y.z>
 *     slot ru|en
 *     model old3ds|new3ds
 *     glyphs default|real
 *     font 0|1                     the NS patch and the built font are on the card
 *     luma <game> <external>       1 = that Luma flag was off and the installer turned it on
 *     skipped <n>                  folders left out: the title is another build
 *     file <sha256> <size> <path>  every file the installer wrote, paths from the card root
 *     end
 *
 * 3ds/3ds-ua/pending.txt - written before the first change, removed after the last
 *     3DSUA-PENDING 1
 *     op install|remove
 *     slot ru|en
 *     glyphs default|real
 *     end
 */
#ifndef ENGINE_STATE_H
#define ENGINE_STATE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "../payload/manifest.h"

#define STATE_DIR "3ds/3ds-ua"
#define INSTALLED_FILE STATE_DIR "/installed.txt"
#define PENDING_FILE STATE_DIR "/pending.txt"
#define BACKUP_DIR STATE_DIR "/backup"
#define CONFIG_BACKUP STATE_DIR "/config.ini.bak"
#define VERIFY_FILE STATE_DIR "/verify"

typedef struct {
    uint8_t sha[32];
    uint32_t size;
    char path[96];
} StateFile;

typedef struct {
    char version[16];
    Slot slot;
    Model model;
    Glyphs glyphs;
    bool font;
    bool luma_game, luma_external;
    int skipped;
    StateFile *files;
    size_t count, cap;
} Installed;

typedef enum { OP_INSTALL, OP_REMOVE } Op;

typedef struct {
    Op op;
    Slot slot;
    Glyphs glyphs;
} Pending;

/* 0, or the 1-based failing line. */
int installed_parse(Installed *s, const char *text, size_t len);
/* malloc()ed text; NULL when out of memory. */
char *installed_format(const Installed *s, size_t *len);
int installed_add(Installed *s, const uint8_t sha[32], uint32_t size, const char *path);
const StateFile *installed_find(const Installed *s, const char *path);
void installed_free(Installed *s);

int pending_parse(Pending *p, const char *text, size_t len);
/* At most 96 bytes. */
size_t pending_format(const Pending *p, char *out, size_t cap);

const char *slot_name(Slot slot);
const char *model_name(Model model);
const char *glyphs_name(Glyphs glyphs);

#endif
