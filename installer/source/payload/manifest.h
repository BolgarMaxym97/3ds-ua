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

typedef struct {
    Model model;
    uint64_t folder;    /* luma/titles/<folder> */
    uint64_t title;     /* the title whose build the folder's patches are for */
    uint16_t remaster;
} Need;

typedef struct {
    char version[16];
    Blob *blobs;
    size_t blob_count;
    Need *needs;
    size_t need_count;
    uint16_t ns_remaster;
    uint8_t ns_code_sha[32];
    char font_path[96];
    char upturn[32];
    FileSet sets[SLOT_COUNT][MODEL_COUNT][GLYPHS_COUNT];
    FileSet font_set;   /* the NS patch files */
} Manifest;

/* Parse `text` (not necessarily NUL-terminated). Returns 0, or the 1-based failing line. */
int manifest_parse(Manifest *m, const char *text, size_t len);
void manifest_free(Manifest *m);

/* Blob index for a sha, or -1. */
int manifest_find_blob(const Manifest *m, const uint8_t sha[32]);

#endif
