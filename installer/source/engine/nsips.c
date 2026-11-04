#include "nsips.h"

#include <stdlib.h>
#include <string.h>

#include "../sysfont/sha256.h"

#define RECORDS_MAX 256

static uint32_t be(const uint8_t *p, int n)
{
    uint32_t v = 0;
    for (int i = 0; i < n; i++)
        v = v << 8 | p[i];
    return v;
}

int ips_parse(const uint8_t *ips, size_t len, IpsRecord *out, size_t cap, size_t *count)
{
    *count = 0;
    if (len < 8 || memcmp(ips, "PATCH", 5))
        return -1;
    size_t at = 5;
    for (;;) {
        if (len - at < 3)
            return -1;
        if (!memcmp(ips + at, "EOF", 3))
            return at + 3 == len ? 0 : -1;
        if (len - at < 5 || *count == cap)
            return -1;
        IpsRecord *r = &out[*count];
        r->at = at;
        r->off = be(ips + at, 3);
        uint32_t size = be(ips + at + 3, 2);
        at += 5;
        if (size) {
            if (len - at < size)
                return -1;
            r->len = size, r->rle = false, r->data = ips + at;
            at += size;
        } else {
            if (len - at < 3)
                return -1;
            r->len = be(ips + at, 2), r->rle = true, r->data = ips + at + 2;
            at += 3;
        }
        r->end = at;
        (*count)++;
    }
}

bool ips_touches(const IpsRecord *r, size_t n, const IpsRange *ranges, size_t nr)
{
    for (size_t i = 0; i < n; i++)
        for (size_t k = 0; k < nr; k++)
            if ((uint64_t)r[i].off < (uint64_t)ranges[k].off + ranges[k].len &&
                (uint64_t)ranges[k].off < (uint64_t)r[i].off + r[i].len)
                return true;
    return false;
}

void ips_mark(const IpsRecord *r, IpsMark *out)
{
    out->off = r->off;
    out->len = r->len;
    if (!r->rle) {
        sha256(r->data, r->len, out->sha);
        return;
    }
    Sha256 s;
    sha256_init(&s);
    for (uint32_t i = 0; i < r->len; i++)
        sha256_update(&s, r->data, 1);
    sha256_final(&s, out->sha);
}

static bool is_ours(const IpsRecord *r, const IpsMark *ours, size_t n)
{
    IpsMark m;
    for (size_t i = 0; i < n; i++)
        if (ours[i].off == r->off && ours[i].len == r->len) {
            ips_mark(r, &m);
            if (!memcmp(m.sha, ours[i].sha, 32))
                return true;
        }
    return false;
}

static IpsRecord *parse_all(const uint8_t *ips, size_t len, size_t *count)
{
    IpsRecord *r = malloc(RECORDS_MAX * sizeof(IpsRecord));
    if (r && ips_parse(ips, len, r, RECORDS_MAX, count)) {
        free(r);
        r = NULL;
    }
    return r;
}

int ips_strip(const uint8_t *ips, size_t len, const IpsMark *ours, size_t n, uint8_t **out, size_t *out_len,
              size_t *removed)
{
    *out = NULL;
    *removed = 0;
    size_t count;
    IpsRecord *r = parse_all(ips, len, &count);
    uint8_t *buf = r ? malloc(len) : NULL;
    if (!buf) {
        free(r);
        return -1;
    }
    memcpy(buf, ips, 5);
    size_t at = 5;
    for (size_t i = 0; i < count; i++) {
        if (is_ours(&r[i], ours, n)) {
            (*removed)++;
            continue;
        }
        memcpy(buf + at, ips + r[i].at, r[i].end - r[i].at);
        at += r[i].end - r[i].at;
    }
    memcpy(buf + at, "EOF", 3);
    *out_len = at + 3;
    *out = buf;
    free(r);
    return 0;
}

int ips_append(const uint8_t *base, size_t base_len, const uint8_t *ours, size_t ours_len, uint8_t **out,
               size_t *out_len)
{
    *out = NULL;
    size_t count;
    IpsRecord *r = parse_all(base, base_len, &count);
    if (!r)
        return -1;
    free(r);
    r = parse_all(ours, ours_len, &count);
    if (!r)
        return -1;
    free(r);
    size_t head = base_len - 3, body = ours_len - 5 - 3;
    uint8_t *buf = malloc(head + body + 3);
    if (!buf)
        return -1;
    memcpy(buf, base, head);
    memcpy(buf + head, ours + 5, body);
    memcpy(buf + head + body, "EOF", 3);
    *out = buf;
    *out_len = head + body + 3;
    return 0;
}

bool ips_empty(const uint8_t *ips, size_t len)
{
    return len == 8 && !memcmp(ips, "PATCHEOF", 8);
}
