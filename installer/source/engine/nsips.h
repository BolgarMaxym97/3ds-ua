/*
 * The IPS patches Luma applies to a system module's code (luma/sysmodules/<TID>.ips), read
 * closely enough to merge ours into someone else's and to take ours out again.
 *
 * Luma reads one file per module, so a second app patching NS (NetPass, 2026-11) replaces the
 * file and ours with it. Two patches that write different bytes can live in one file: theirs
 * as it was up to its "EOF", our records after it, then "EOF". Taking ours out drops exactly
 * the records we appended and leaves every other byte as it was.
 *
 * Format: "PATCH", then records of a 24-bit big-endian offset and a 16-bit size followed by
 * that many bytes - or, for size 0, a 16-bit count and one byte repeated (RLE) - then "EOF".
 * Anything after "EOF" (the truncate extension) is refused: Luma has no use for it and we
 * would not know whether to keep it.
 *
 * Plain C99, no libctru: the same file builds for the console and for the host tests.
 */
#ifndef ENGINE_NSIPS_H
#define ENGINE_NSIPS_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "../payload/manifest.h" /* IpsRange */

typedef struct {
    uint32_t off;
    uint32_t len;          /* bytes written: the size, or an RLE record's count */
    const uint8_t *data;   /* into the parsed buffer; for RLE, the one fill byte */
    bool rle;
    size_t at, end;        /* the record's span in the parsed buffer */
} IpsRecord;

/* A record of ours as the install wrote it: where, how long, and the sha of its bytes. */
typedef struct {
    uint32_t off;
    uint32_t len;
    uint8_t sha[32];
} IpsMark;

/* 0, or -1: no "PATCH", a record running past the end, no "EOF", bytes after "EOF", or more
 * than `cap` records. */
int ips_parse(const uint8_t *ips, size_t len, IpsRecord *out, size_t cap, size_t *count);

/* Does any byte any record writes fall inside any of the ranges? */
bool ips_touches(const IpsRecord *r, size_t n, const IpsRange *ranges, size_t nr);

/* The mark of one record (an RLE record's sha is that of the bytes it expands to). */
void ips_mark(const IpsRecord *r, IpsMark *out);

/* `ips` without the records that equal one of `ours` (offset, length and bytes); every other
 * byte kept as it is. *removed: how many went. 0, or -1 when `ips` does not parse or memory
 * runs out (then *out is NULL). The caller frees *out. */
int ips_strip(const uint8_t *ips, size_t len, const IpsMark *ours, size_t n, uint8_t **out, size_t *out_len,
              size_t *removed);

/* `base` up to its "EOF", the records of `ours`, "EOF". 0, or -1 when either does not parse
 * or memory runs out (then *out is NULL). The caller frees *out. */
int ips_append(const uint8_t *base, size_t base_len, const uint8_t *ours, size_t ours_len, uint8_t **out,
               size_t *out_len);

/* "PATCHEOF": a patch with no records. */
bool ips_empty(const uint8_t *ips, size_t len);

#endif
