#include "report.h"

#include <stdio.h>
#include <string.h>

static const char ALPHABET[] = "0123456789ABCDEFGHJKMNPQRSTVWXYZ";

void report_id_encode(const uint8_t bytes[5], char out[REPORT_ID_LEN + 1])
{
    uint64_t v = 0;
    for (int i = 0; i < 5; i++)
        v = v << 8 | bytes[i];
    for (int i = REPORT_ID_LEN - 1; i >= 0; i--, v >>= 5)
        out[i] = ALPHABET[v & 31];
    out[REPORT_ID_LEN] = 0;
}

int report_id_valid(const char *id)
{
    if (!id || strlen(id) != REPORT_ID_LEN)
        return 0;
    for (int i = 0; i < REPORT_ID_LEN; i++)
        if (!id[i] || !strchr(ALPHABET, id[i]))
            return 0;
    return 1;
}

void report_id_display(const char *id, char out[REPORT_ID_LEN + 2])
{
    memcpy(out, id, 4);
    out[4] = '-';
    memcpy(out + 5, id + 4, 4);
    out[9] = 0;
}

typedef struct {
    char *out;
    size_t cap, len;
    int full;
} Buf;

static void put(Buf *b, const char *s, size_t n)
{
    if (b->full || b->len + n >= b->cap) {
        b->full = 1;
        return;
    }
    memcpy(b->out + b->len, s, n);
    b->len += n;
    b->out[b->len] = 0;
}

static void puts_(Buf *b, const char *s) { put(b, s, strlen(s)); }

/* At most `max` characters as the server counts them (UTF-16 units - the same as code
 * points for everything the app writes), never cutting a UTF-8 sequence. With `room`, the
 * string also stops while that many bytes are still free in the buffer. */
static void string(Buf *b, const char *s, size_t max, size_t room)
{
    put(b, "\"", 1);
    size_t limit = b->cap > room + b->len ? b->cap - room : 0;
    size_t count = 0;
    for (const unsigned char *p = (const unsigned char *)s; *p && count < max; count++) {
        size_t n = *p < 0x80 ? 1 : *p >= 0xF0 ? 4 : *p >= 0xE0 ? 3 : *p >= 0xC0 ? 2 : 1;
        for (size_t k = 1; k < n; k++)
            if ((p[k] & 0xC0) != 0x80)
                n = 1; /* a broken sequence: pass the byte on, the server takes it as is */
        if (n == 4 && count + 2 > max)
            break;
        if (room && b->len + 6 + n > limit)
            break; /* the longest escape plus this character no longer fits */
        char esc[8];
        if (*p == '"' || *p == '\\') {
            esc[0] = '\\';
            esc[1] = (char)*p;
            put(b, esc, 2);
        } else if (*p == '\n') {
            put(b, "\\n", 2);
        } else if (*p < 0x20) {
            snprintf(esc, sizeof(esc), "\\u%04x", *p);
            put(b, esc, 6);
        } else {
            put(b, (const char *)p, n);
        }
        count += n == 4; /* outside the BMP: two UTF-16 units */
        p += n;
    }
    put(b, "\"", 1);
}

static void field(Buf *b, const char *key, const char *value, size_t max, size_t room)
{
    if (!value)
        return;
    put(b, ",\"", 2);
    puts_(b, key);
    put(b, "\":", 2);
    string(b, value, max, room);
}

static void number(Buf *b, const char *key, long long value)
{
    if (value < 0)
        return;
    char text[48];
    put(b, text, (size_t)snprintf(text, sizeof(text), ",\"%s\":%lld", key, value));
}

size_t report_json(const Report *r, char *out, size_t cap)
{
    if (cap > REPORT_MAX + 1)
        cap = REPORT_MAX + 1;
    Buf b = {out, cap, 0, 0};
    if (!cap)
        return 0;
    out[0] = 0;
    puts_(&b, "{\"v\":1");
    field(&b, "id", r->id, REPORT_ID_LEN, 0);
    field(&b, "event", r->event, 16, 0);
    field(&b, "app", r->app, 16, 0);
    field(&b, "prev", r->prev, 16, 0);
    field(&b, "model", r->model, 32, 0);
    field(&b, "system", r->system, 32, 0);
    field(&b, "luma", r->luma, 16, 0);
    field(&b, "region", r->region, 8, 0);
    field(&b, "slot", r->slot, 8, 0);
    field(&b, "glyphs", r->glyphs, 16, 0);
    field(&b, "font", r->font, 32, 0);
    number(&b, "ms", r->ms);
    field(&b, "stage", r->stage, 32, 0);
    number(&b, "code", r->code);
    field(&b, "detail", r->detail, 256, 0);
    /* last, and cut to what is left: a Ukrainian log is two bytes a letter */
    field(&b, "log", r->log, REPORT_LOG_MAX, 3);
    put(&b, "}", 1);
    return b.full ? 0 : b.len;
}
