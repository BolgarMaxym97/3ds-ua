/*
 * Restore one file of a build from the romfs: inflate a whole file, or apply a delta to its
 * base (the UAD1 format, see tools/installer_manifest.py), and check the sha256 either way.
 *
 * `root` is the directory holding manifest.txt: "romfs:/data" on the console, the build
 * output on the host. Plain C99 + zlib.
 */
#ifndef PAYLOAD_H
#define PAYLOAD_H

#include "manifest.h"

typedef enum {
    PAYLOAD_OK = 0,
    PAYLOAD_E_READ,     /* the stored file is missing or unreadable */
    PAYLOAD_E_DATA,     /* it does not inflate or the delta is malformed */
    PAYLOAD_E_HASH,     /* restored, but not the file the manifest names */
    PAYLOAD_E_MEMORY,
} PayloadStatus;

/* On success *out is a malloc()ed buffer of m->blobs[blob].size bytes. */
PayloadStatus payload_restore(const Manifest *m, const char *root, int blob, uint8_t **out);

/* Read a whole file into a malloc()ed buffer; returns 0 or -1. */
int payload_read_file(const char *path, uint8_t **data, size_t *len);

const char *payload_error(PayloadStatus status);

#endif
