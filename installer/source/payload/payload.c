#include "payload.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <zlib.h>

#include "../sysfont/sha256.h"

static uint32_t rd32(const uint8_t *p) { return p[0] | p[1] << 8 | p[2] << 16 | (uint32_t)p[3] << 24; }

static int64_t rd64(const uint8_t *p)
{
    uint64_t v = 0;
    for (int i = 7; i >= 0; i--)
        v = v << 8 | p[i];
    return (int64_t)v;
}

int payload_read_file(const char *path, uint8_t **data, size_t *len)
{
    FILE *f = fopen(path, "rb");
    if (!f)
        return -1;
    if (fseek(f, 0, SEEK_END) || ftell(f) < 0) {
        fclose(f);
        return -1;
    }
    long size = ftell(f);
    rewind(f);
    uint8_t *buf = malloc(size ? (size_t)size : 1);
    if (!buf || fread(buf, 1, (size_t)size, f) != (size_t)size) {
        free(buf);
        fclose(f);
        return -1;
    }
    fclose(f);
    *data = buf;
    *len = (size_t)size;
    return 0;
}

static PayloadStatus read_stored(const Manifest *m, const char *root, int blob, uint8_t **data, size_t *len)
{
    char path[256];
    snprintf(path, sizeof(path), "%s/%s", root, m->blobs[blob].name);
    return payload_read_file(path, data, len) ? PAYLOAD_E_READ : PAYLOAD_OK;
}

static PayloadStatus inflate_to(const uint8_t *z, size_t zlen, uint8_t *out, size_t size)
{
    uLongf got = (uLongf)size;
    if (uncompress(out, &got, z, (uLong)zlen) != Z_OK || got != size)
        return PAYLOAD_E_DATA;
    return PAYLOAD_OK;
}

static PayloadStatus restore_whole(const Manifest *m, const char *root, int blob, uint8_t **out)
{
    uint8_t *z;
    size_t zlen;
    PayloadStatus status = read_stored(m, root, blob, &z, &zlen);
    if (status != PAYLOAD_OK)
        return status;
    size_t size = m->blobs[blob].size;
    uint8_t *data = malloc(size ? size : 1);
    if (!data) {
        free(z);
        return PAYLOAD_E_MEMORY;
    }
    status = size ? inflate_to(z, zlen, data, size) : PAYLOAD_OK;
    free(z);
    if (status != PAYLOAD_OK) {
        free(data);
        return status;
    }
    *out = data;
    return PAYLOAD_OK;
}

/* bsdiff's loop, kept step for step with apply_delta() in tools/installer_manifest.py. */
static PayloadStatus apply_delta(const uint8_t *old, size_t old_len, const uint8_t *d, size_t dlen, uint8_t *out, size_t size)
{
    if (dlen < 24 || memcmp(d, "UAD1", 4))
        return PAYLOAD_E_DATA;
    uint32_t new_size = rd32(d + 4), count = rd32(d + 8);
    size_t lc = rd32(d + 12), ld = rd32(d + 16), le = rd32(d + 20);
    if (new_size != size || 24 + lc + ld + le != dlen || count > 0x1000000)
        return PAYLOAD_E_DATA;

    PayloadStatus status = PAYLOAD_E_MEMORY;
    size_t ctrl_len = (size_t)count * 24;
    uint8_t *ctrl = malloc(ctrl_len ? ctrl_len : 1);
    uint8_t *diff = malloc(size ? size : 1);  /* never longer than the file */
    uint8_t *extra = malloc(size ? size : 1);
    if (!ctrl || !diff || !extra)
        goto done;

    status = PAYLOAD_E_DATA;
    uLongf got = (uLongf)ctrl_len;
    if (uncompress(ctrl, &got, d + 24, (uLong)lc) != Z_OK || got != ctrl_len)
        goto done;
    uLongf diff_len = (uLongf)size, extra_len = (uLongf)size;
    if (uncompress(diff, &diff_len, d + 24 + lc, (uLong)ld) != Z_OK)
        goto done;
    if (uncompress(extra, &extra_len, d + 24 + lc + ld, (uLong)le) != Z_OK)
        goto done;

    int64_t newpos = 0, oldpos = 0, di = 0, ei = 0;
    for (uint32_t i = 0; i < count; i++) {
        int64_t x = rd64(ctrl + 24 * i), y = rd64(ctrl + 24 * i + 8), z = rd64(ctrl + 24 * i + 16);
        if (x < 0 || y < 0 || newpos + x > (int64_t)size || di + x > (int64_t)diff_len)
            goto done;
        for (int64_t k = 0; k < x; k++) {
            int64_t o = oldpos + k;
            uint8_t base = o >= 0 && o < (int64_t)old_len ? old[o] : 0;
            out[newpos + k] = (uint8_t)(diff[di + k] + base);
        }
        newpos += x;
        oldpos += x;
        di += x;
        if (newpos + y > (int64_t)size || ei + y > (int64_t)extra_len)
            goto done;
        memcpy(out + newpos, extra + ei, (size_t)y);
        newpos += y;
        ei += y;
        oldpos += z;
    }
    if (newpos == (int64_t)size)
        status = PAYLOAD_OK;
done:
    free(ctrl);
    free(diff);
    free(extra);
    return status;
}

PayloadStatus payload_restore(const Manifest *m, const char *root, int blob, uint8_t **out)
{
    if (blob < 0 || (size_t)blob >= m->blob_count)
        return PAYLOAD_E_DATA;
    const Blob *b = &m->blobs[blob];
    uint8_t *data = NULL;
    PayloadStatus status;

    if (b->base < 0) {
        status = restore_whole(m, root, blob, &data);
    } else {
        uint8_t *old = NULL, *delta = NULL;
        size_t delta_len;
        status = restore_whole(m, root, b->base, &old);
        if (status == PAYLOAD_OK)
            status = read_stored(m, root, blob, &delta, &delta_len);
        if (status == PAYLOAD_OK) {
            data = malloc(b->size ? b->size : 1);
            status = data ? apply_delta(old, m->blobs[b->base].size, delta, delta_len, data, b->size) : PAYLOAD_E_MEMORY;
        }
        free(old);
        free(delta);
    }
    if (status != PAYLOAD_OK) {
        free(data);
        return status;
    }

    uint8_t digest[32];
    sha256(data, b->size, digest);
    if (memcmp(digest, b->sha, 32)) {
        free(data);
        return PAYLOAD_E_HASH;
    }
    *out = data;
    return PAYLOAD_OK;
}

const char *payload_error(PayloadStatus status)
{
    switch (status) {
    case PAYLOAD_OK: return "ok";
    case PAYLOAD_E_READ: return "a file of the app is missing";
    case PAYLOAD_E_DATA: return "a file of the app is damaged";
    case PAYLOAD_E_HASH: return "a restored file does not match the manifest";
    case PAYLOAD_E_MEMORY: return "out of memory";
    }
    return "unknown error";
}
