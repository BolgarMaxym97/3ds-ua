/*
 * data/manifest.txt from tools/installer_manifest.py: which files make up each build, how
 * each file is stored in the romfs, and which title builds the code patches need.
 *
 * Plain C99, no libctru: the same file builds for the console and for the host tests.
 */
#ifndef PAYLOAD_MANIFEST_H
#define PAYLOAD_MANIFEST_H

#include <stddef.h>
#include <stdint.h>

typedef enum { SLOT_RU, SLOT_EN, SLOT_COUNT } Slot;
typedef enum { MODEL_OLD3DS, MODEL_NEW3DS, MODEL_COUNT } Model;
typedef enum { GLYPHS_DEFAULT, GLYPHS_REAL, GLYPHS_COUNT } Glyphs;

typedef struct {
    uint8_t sha[32];
    uint32_t size;
    char name[16];      /* romfs name under data/, e.g. "b/0001.z" */
    int base;           /* blob index of the delta base, -1 for a whole file */
} Blob;

typedef struct {
    int blob;           /* index into Manifest.blobs */
    char path[96];      /* SD path relative to the card root */
} Entry;

typedef struct {
    Entry *entries;
    size_t count;
} FileSet;

/* A stretch of NS's .code by IPS offset (the code's load address 0x100000 is offset 0). */
typedef struct {
    uint32_t off;
    uint32_t len;
} IpsRange;

#define NS_DEPS_MAX 16
#define ALTS_MAX 4

typedef struct {
    Model model;
    uint64_t folder;    /* luma/titles/<folder> */
    uint64_t title;     /* the title whose build the folder's patches are for */
    uint16_t remaster;
} Need;

/* A folder built for an update, not for the title on the NAND: luma/titles/<folder> holds it
 * in the payload, and it is installed as luma/titles/<target> - in place of that folder's
 * own files - when the update is on the card in that build (see manifest_apply_alts). */
typedef struct {
    uint64_t folder;    /* the update's title id, the folder's name in the payload */
    uint64_t target;    /* the title whose folder Luma reads for it */
    uint16_t remaster;
} Alt;

typedef enum { ALT_ABSENT, ALT_PRESENT, ALT_OTHER_BUILD } AltState;
typedef AltState (*AltProbe)(uint64_t title, uint16_t remaster, void *ctx);

typedef struct {
    char version[16];
    Blob *blobs;
    size_t blob_count;
    Need *needs;
    size_t need_count;
    uint16_t ns_remaster;
    uint8_t ns_code_sha[32];
    IpsRange ns_deps[NS_DEPS_MAX]; /* what the font stub relies on but does not write, sorted */
    size_t ns_dep_count;
    char font_path[96];
    char upturn[32];
    FileSet sets[SLOT_COUNT][MODEL_COUNT][GLYPHS_COUNT];
    FileSet font_set;   /* the NS patch files */
    Alt alts[ALTS_MAX];
    size_t alt_count;
} Manifest;

/* Parse `text` (not necessarily NUL-terminated). Returns 0, or the 1-based failing line. */
int manifest_parse(Manifest *m, const char *text, size_t len);
void manifest_free(Manifest *m);

/* Settle every `alt` against the card, in every set: the update is installed in the build the
 * folder was made for - its files move to the target folder and the target's own files go;
 * not installed - its files go; installed in another build - both go, the title is left
 * as Nintendo shipped it. Call once, right after manifest_parse. */
void manifest_apply_alts(Manifest *m, AltProbe probe, void *ctx);

/* Blob index for a sha, or -1. */
int manifest_find_blob(const Manifest *m, const uint8_t sha[32]);

#endif
