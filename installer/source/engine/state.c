#include "state.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_FIELDS 5

static const char HEX[] = "0123456789abcdef";

const char *slot_name(Slot slot) { return slot == SLOT_EN ? "en" : "ru"; }
const char *model_name(Model model) { return model == MODEL_NEW3DS ? "new3ds" : "old3ds"; }
const char *glyphs_name(Glyphs glyphs) { return glyphs == GLYPHS_REAL ? "real" : "default"; }

/* One line split on single spaces; the last field takes the rest of the line. */
typedef struct {
    const char *f[MAX_FIELDS];
    size_t len[MAX_FIELDS];
    int n;
} Fields;

static void split(Fields *fl, const char *s, size_t len, int max)
{
    fl->n = 0;
    size_t i = 0;
    while (i <= len && fl->n < max) {
        size_t start = i;
        if (fl->n == max - 1) {
            i = len;
        } else {
            while (i < len && s[i] != ' ')
                i++;
        }
        fl->f[fl->n] = s + start;
        fl->len[fl->n] = i - start;
        fl->n++;
        i++;
        if (i > len)
            break;
    }
}

static bool is(const Fields *fl, int k, const char *word)
{
    return k < fl->n && strlen(word) == fl->len[k] && !memcmp(fl->f[k], word, fl->len[k]);
}

static int hexval(char c)
{
    if (c >= '0' && c <= '9')
        return c - '0';
    if (c >= 'a' && c <= 'f')
        return c - 'a' + 10;
    return -1;
}

static int parse_sha(const char *s, size_t len, uint8_t out[32])
{
    if (len != 64)
        return -1;
    for (int i = 0; i < 32; i++) {
        int hi = hexval(s[2 * i]), lo = hexval(s[2 * i + 1]);
        if (hi < 0 || lo < 0)
            return -1;
        out[i] = (uint8_t)(hi << 4 | lo);
    }
    return 0;
}

static int parse_uint(const char *s, size_t len, uint32_t *out)
{
    if (!len || len > 9)
        return -1;
    uint32_t v = 0;
    for (size_t i = 0; i < len; i++) {
        if (s[i] < '0' || s[i] > '9')
            return -1;
        v = v * 10 + (uint32_t)(s[i] - '0');
    }
    *out = v;
    return 0;
}

static int parse_bool(const char *s, size_t len, bool *out)
{
    if (len != 1 || (s[0] != '0' && s[0] != '1'))
        return -1;
    *out = s[0] == '1';
    return 0;
}

static int parse_slot(const Fields *fl, Slot *slot)
{
    if (is(fl, 1, "ru"))
        *slot = SLOT_RU;
    else if (is(fl, 1, "en"))
        *slot = SLOT_EN;
    else
        return -1;
    return 0;
}

static int parse_glyphs(const Fields *fl, Glyphs *glyphs)
{
    if (is(fl, 1, "default"))
        *glyphs = GLYPHS_DEFAULT;
    else if (is(fl, 1, "real"))
        *glyphs = GLYPHS_REAL;
    else
        return -1;
    return 0;
}

/* Calls `line` for each line after the header; stops at "end". */
typedef int (*LineFn)(void *ctx, const Fields *fl);

static int parse_lines(const char *text, size_t len, const char *header, int max, LineFn line, void *ctx)
{
    size_t pos = 0;
    int number = 0;
    bool ended = false;
    while (pos < len && !ended) {
        const char *s = text + pos;
        const char *nl = memchr(s, '\n', len - pos);
        size_t n = nl ? (size_t)(nl - s) : len - pos;
        pos += n + 1;
        number++;
        Fields fl;
        split(&fl, s, n, max);
        if (number == 1) {
            if (strlen(header) != n || memcmp(s, header, n))
                return 1;
        } else if (is(&fl, 0, "end") && fl.n == 1) {
            ended = true;
        } else if (line(ctx, &fl)) {
            return number;
        }
    }
    return ended ? 0 : number + 1;
}

/* ---------------------------------------------------------------- installed.txt */

int installed_add(Installed *s, const uint8_t sha[32], uint32_t size, const char *path)
{
    if (strlen(path) >= sizeof(s->files[0].path))
        return -1;
    if (s->count == s->cap) {
        size_t cap = s->cap ? s->cap * 2 : 256;
        StateFile *files = realloc(s->files, cap * sizeof(StateFile));
        if (!files)
            return -1;
        s->files = files;
        s->cap = cap;
    }
    StateFile *f = &s->files[s->count++];
    memcpy(f->sha, sha, 32);
    f->size = size;
    strcpy(f->path, path);
    return 0;
}

const StateFile *installed_find(const Installed *s, const char *path)
{
    for (size_t i = 0; i < s->count; i++)
        if (!strcmp(s->files[i].path, path))
            return &s->files[i];
    return NULL;
}

void installed_free(Installed *s)
{
    free(s->files);
    memset(s, 0, sizeof(*s));
}

static int installed_line(void *ctx, const Fields *fl)
{
    Installed *s = ctx;
    uint32_t v;
    if (is(fl, 0, "version") && fl->n == 2 && fl->len[1] < sizeof(s->version)) {
        memcpy(s->version, fl->f[1], fl->len[1]);
        s->version[fl->len[1]] = 0;
        return 0;
    }
    if (is(fl, 0, "slot") && fl->n == 2)
        return parse_slot(fl, &s->slot);
    if (is(fl, 0, "model") && fl->n == 2) {
        if (is(fl, 1, "old3ds"))
            s->model = MODEL_OLD3DS;
        else if (is(fl, 1, "new3ds"))
            s->model = MODEL_NEW3DS;
        else
            return -1;
        return 0;
    }
    if (is(fl, 0, "glyphs") && fl->n == 2)
        return parse_glyphs(fl, &s->glyphs);
    if (is(fl, 0, "font") && fl->n == 2)
        return parse_bool(fl->f[1], fl->len[1], &s->font);
    if (is(fl, 0, "luma") && fl->n == 3)
        return parse_bool(fl->f[1], fl->len[1], &s->luma_game) || parse_bool(fl->f[2], fl->len[2], &s->luma_external);
    if (is(fl, 0, "skipped") && fl->n == 2) {
        if (parse_uint(fl->f[1], fl->len[1], &v))
            return -1;
        s->skipped = (int)v;
        return 0;
    }
    if (is(fl, 0, "file") && fl->n == 4) {
        uint8_t sha[32];
        char path[96];
        if (parse_sha(fl->f[1], fl->len[1], sha) || parse_uint(fl->f[2], fl->len[2], &v) || fl->len[3] >= sizeof(path))
            return -1;
        memcpy(path, fl->f[3], fl->len[3]);
        path[fl->len[3]] = 0;
        return installed_add(s, sha, v, path);
    }
    return -1;
}

int installed_parse(Installed *s, const char *text, size_t len)
{
    memset(s, 0, sizeof(*s));
    int status = parse_lines(text, len, "3DSUA-INSTALLED 1", 4, installed_line, s);
    if (status)
        installed_free(s);
    return status;
}

char *installed_format(const Installed *s, size_t *len)
{
    size_t cap = 256 + s->count * (64 + 12 + 96 + 8);
    char *out = malloc(cap);
    if (!out)
        return NULL;
    size_t n = (size_t)snprintf(out, cap,
                                "3DSUA-INSTALLED 1\nversion %s\nslot %s\nmodel %s\nglyphs %s\nfont %d\nluma %d %d\nskipped %d\n",
                                s->version, slot_name(s->slot), model_name(s->model), glyphs_name(s->glyphs), s->font,
                                s->luma_game, s->luma_external, s->skipped);
    for (size_t i = 0; i < s->count; i++) {
        const StateFile *f = &s->files[i];
        char hex[65];
        for (int k = 0; k < 32; k++) {
            hex[2 * k] = HEX[f->sha[k] >> 4];
            hex[2 * k + 1] = HEX[f->sha[k] & 15];
        }
        hex[64] = 0;
        n += (size_t)snprintf(out + n, cap - n, "file %s %lu %s\n", hex, (unsigned long)f->size, f->path);
    }
    n += (size_t)snprintf(out + n, cap - n, "end\n");
    *len = n;
    return out;
}

/* ---------------------------------------------------------------- pending.txt */

static int pending_line(void *ctx, const Fields *fl)
{
    Pending *p = ctx;
    if (is(fl, 0, "op") && fl->n == 2) {
        if (is(fl, 1, "install"))
            p->op = OP_INSTALL;
        else if (is(fl, 1, "remove"))
            p->op = OP_REMOVE;
        else
            return -1;
        return 0;
    }
    if (is(fl, 0, "slot") && fl->n == 2)
        return parse_slot(fl, &p->slot);
    if (is(fl, 0, "glyphs") && fl->n == 2)
        return parse_glyphs(fl, &p->glyphs);
    return -1;
}

int pending_parse(Pending *p, const char *text, size_t len)
{
    memset(p, 0, sizeof(*p));
    return parse_lines(text, len, "3DSUA-PENDING 1", 2, pending_line, p);
}

size_t pending_format(const Pending *p, char *out, size_t cap)
{
    return (size_t)snprintf(out, cap, "3DSUA-PENDING 1\nop %s\nslot %s\nglyphs %s\nend\n",
                            p->op == OP_REMOVE ? "remove" : "install", slot_name(p->slot), glyphs_name(p->glyphs));
}
