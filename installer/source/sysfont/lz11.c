#include "lz11.h"

#include <stdlib.h>
#include <string.h>

#define WINDOW 4096
#define MAX_MATCH 0x10110
#define HASH_BITS 16

size_t lz11_size(const uint8_t *in, size_t in_len)
{
    if (in_len < 4 || in[0] != 0x11)
        return 0;
    size_t size = in[1] | (in[2] << 8) | ((size_t)in[3] << 16);
    if (size == 0 && in_len >= 8)
        size = in[4] | (in[5] << 8) | ((size_t)in[6] << 16) | ((size_t)in[7] << 24);
    return size;
}

int lz11_decompress(const uint8_t *in, size_t in_len, uint8_t *out, size_t out_len)
{
    size_t size = lz11_size(in, in_len);
    if (size == 0 || size != out_len)
        return -1;
    size_t pos = (in[1] | in[2] | in[3]) ? 4 : 8;
    size_t at = 0;

    while (at < size) {
        if (pos >= in_len)
            return -1;
        uint8_t flags = in[pos++];
        for (int bit = 7; bit >= 0 && at < size; bit--) {
            if (!((flags >> bit) & 1)) {
                if (pos >= in_len)
                    return -1;
                out[at++] = in[pos++];
                continue;
            }
            if (pos + 1 >= in_len)
                return -1;
            uint8_t b1 = in[pos];
            size_t length, disp;
            switch (b1 >> 4) {
            case 0:
                if (pos + 2 >= in_len)
                    return -1;
                length = (((b1 & 0xF) << 4) | (in[pos + 1] >> 4)) + 0x11;
                disp = (((in[pos + 1] & 0xF) << 8) | in[pos + 2]) + 1;
                pos += 3;
                break;
            case 1:
                if (pos + 3 >= in_len)
                    return -1;
                length = (((size_t)(b1 & 0xF) << 12) | (in[pos + 1] << 4) | (in[pos + 2] >> 4)) + 0x111;
                disp = (((in[pos + 2] & 0xF) << 8) | in[pos + 3]) + 1;
                pos += 4;
                break;
            default:
                length = (b1 >> 4) + 1;
                disp = (((b1 & 0xF) << 8) | in[pos + 1]) + 1;
                pos += 2;
                break;
            }
            if (disp > at)
                return -1;
            /* The Python decoder copies the whole reference and truncates at the end. */
            for (size_t i = 0; i < length && at < size; i++, at++)
                out[at] = out[at - disp];
        }
    }
    return 0;
}

size_t lz11_bound(size_t len)
{
    return 8 + len + len / 8 + 1;
}

static uint32_t hash3(const uint8_t *p)
{
    return ((p[0] << 8) ^ (p[1] << 4) ^ p[2]) & ((1u << HASH_BITS) - 1);
}

/* Every position before the one being matched is in its hash chain, newest first, so the
 * walk visits candidates in exactly the descending order rfind() does in tools/lz11.py. */
typedef struct {
    const uint8_t *data;
    size_t len;
    int32_t *head;
    int32_t prev[WINDOW];
} Chains;

static void insert(Chains *c, size_t pos)
{
    if (pos + 2 >= c->len)
        return;
    uint32_t h = hash3(c->data + pos);
    c->prev[pos & (WINDOW - 1)] = c->head[h];
    c->head[h] = (int32_t)pos;
}

static size_t find_match(const Chains *c, size_t pos, size_t *disp)
{
    const uint8_t *d = c->data;
    size_t max_len = c->len - pos < MAX_MATCH ? c->len - pos : MAX_MATCH;
    if (max_len < 3)
        return 0;
    int32_t window_start = pos > WINDOW ? (int32_t)(pos - WINDOW) : 0;
    size_t best = 0;

    for (int32_t s = c->head[hash3(d + pos)]; s >= window_start; s = c->prev[s & (WINDOW - 1)]) {
        /* a candidate that differs at the current best length cannot beat it (and a tie
         * keeps the earlier, nearer one): skipping it leaves the output byte for byte */
        if ((best && d[s + best] != d[pos + best]) || d[s] != d[pos] || d[s + 1] != d[pos + 1] || d[s + 2] != d[pos + 2])
            continue;
        size_t length = 3;
        while (length < max_len && d[s + length] == d[pos + length])
            length++;
        if (length > best) {
            best = length;
            *disp = pos - (size_t)s;
            if (length == max_len)
                break;
        }
    }
    return best;
}

static size_t encode_ref(uint8_t *out, size_t length, size_t disp)
{
    size_t d = disp - 1;
    if (length <= 0x10) {
        out[0] = (uint8_t)(((length - 1) << 4) | (d >> 8));
        out[1] = (uint8_t)d;
        return 2;
    }
    if (length <= 0x110) {
        size_t n = length - 0x11;
        out[0] = (uint8_t)(n >> 4);
        out[1] = (uint8_t)(((n & 0xF) << 4) | (d >> 8));
        out[2] = (uint8_t)d;
        return 3;
    }
    size_t n = length - 0x111;
    out[0] = (uint8_t)(0x10 | (n >> 12));
    out[1] = (uint8_t)(n >> 4);
    out[2] = (uint8_t)(((n & 0xF) << 4) | (d >> 8));
    out[3] = (uint8_t)d;
    return 4;
}

size_t lz11_compress(const uint8_t *in, size_t len, uint8_t *out, size_t out_cap)
{
    if (out_cap < lz11_bound(len) || len > 0xFFFFFFFFu)
        return 0;
    Chains *c = malloc(sizeof(Chains));
    int32_t *head = malloc(sizeof(int32_t) << HASH_BITS);
    if (!c || !head) {
        free(c);
        free(head);
        return 0;
    }
    memset(head, 0xFF, sizeof(int32_t) << HASH_BITS);
    c->data = in;
    c->len = len;
    c->head = head;

    size_t at = 0;
    out[at++] = 0x11;
    if (len <= 0xFFFFFF) {
        out[at++] = (uint8_t)len;
        out[at++] = (uint8_t)(len >> 8);
        out[at++] = (uint8_t)(len >> 16);
    } else {
        out[at++] = 0;
        out[at++] = 0;
        out[at++] = 0;
        for (int i = 0; i < 4; i++)
            out[at++] = (uint8_t)(len >> (8 * i));
    }

    size_t pos = 0;
    while (pos < len) {
        size_t flag_at = at++;
        uint8_t flags = 0;
        for (int bit = 7; bit >= 0 && pos < len; bit--) {
            size_t disp = 0;
            size_t length = find_match(c, pos, &disp);
            if (length >= 3) {
                flags |= (uint8_t)(1 << bit);
                at += encode_ref(out + at, length, disp);
                for (size_t i = 0; i < length; i++)
                    insert(c, pos + i);
                pos += length;
            } else {
                out[at++] = in[pos];
                insert(c, pos);
                pos++;
            }
        }
        out[flag_at] = flags;
    }

    free(head);
    free(c);
    return at;
}
