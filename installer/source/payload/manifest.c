#include "manifest.h"

#include <stdlib.h>
#include <string.h>

#define MAX_FIELDS 8

static int hexval(char c)
{
    if (c >= '0' && c <= '9')
        return c - '0';
    if (c >= 'a' && c <= 'f')
        return c - 'a' + 10;
    if (c >= 'A' && c <= 'F')
        return c - 'A' + 10;
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

static int parse_u64(const char *s, size_t len, int base, uint64_t *out)
{
    if (!len || len > 20)
        return -1;
    uint64_t v = 0;
    for (size_t i = 0; i < len; i++) {
        int d = hexval(s[i]);
        if (d < 0 || d >= base)
            return -1;
        v = v * (uint64_t)base + (uint64_t)d;
    }
    *out = v;
    return 0;
}

static int copy_field(char *dst, size_t cap, const char *s, size_t len)
{
    if (len + 1 > cap)
        return -1;
    memcpy(dst, s, len);
    dst[len] = 0;
    return 0;
}

static int field_is(const char *s, size_t len, const char *word)
{
    return strlen(word) == len && !memcmp(s, word, len);
}

/* ---------------------------------------------------------------- sha -> blob index */

typedef struct {
    int *slots;
    size_t mask;
} Index;

static uint32_t sha_key(const uint8_t *sha) { return (uint32_t)sha[0] | sha[1] << 8 | sha[2] << 16 | (uint32_t)sha[3] << 24; }

static int index_build(Index *ix, const Manifest *m)
{
    size_t size = 16;
    while (size < m->blob_count * 2)
        size <<= 1;
    ix->slots = malloc(size * sizeof(int));
    if (!ix->slots)
        return -1;
    memset(ix->slots, 0xFF, size * sizeof(int));
    ix->mask = size - 1;
    for (size_t i = 0; i < m->blob_count; i++) {
        size_t at = sha_key(m->blobs[i].sha) & ix->mask;
        while (ix->slots[at] >= 0)
            at = (at + 1) & ix->mask;
        ix->slots[at] = (int)i;
    }
    return 0;
}

static int index_find(const Index *ix, const Manifest *m, const uint8_t *sha)
{
    for (size_t at = sha_key(sha) & ix->mask; ix->slots[at] >= 0; at = (at + 1) & ix->mask)
        if (!memcmp(m->blobs[ix->slots[at]].sha, sha, 32))
            return ix->slots[at];
    return -1;
}

int manifest_find_blob(const Manifest *m, const uint8_t sha[32])
{
    for (size_t i = 0; i < m->blob_count; i++)
        if (!memcmp(m->blobs[i].sha, sha, 32))
            return (int)i;
    return -1;
}

/* ---------------------------------------------------------------- parse */

void manifest_free(Manifest *m)
{
    free(m->blobs);
    free(m->needs);
    for (int s = 0; s < SLOT_COUNT; s++)
        for (int d = 0; d < MODEL_COUNT; d++)
            for (int g = 0; g < GLYPHS_COUNT; g++)
                free(m->sets[s][d][g].entries);
    free(m->font_set.entries);
    memset(m, 0, sizeof(*m));
}

int manifest_parse(Manifest *m, const char *text, size_t len)
{
    memset(m, 0, sizeof(*m));
    size_t blob_cap = 0, need_cap = 0;
    uint8_t (*base_sha)[32] = NULL;
    FileSet *current = NULL;
    size_t remaining = 0;
    int line_no = 0, ended = 0;
    /* file lines hold a sha until every blob is known */
    typedef struct {
        uint8_t sha[32];
    } Pending;
    Pending **pending = NULL;
    size_t set_count = 0;
    FileSet *set_list[SLOT_COUNT * MODEL_COUNT * GLYPHS_COUNT + 1];

    size_t at = 0;
    while (at < len && !ended) {
        size_t end = at;
        while (end < len && text[end] != '\n')
            end++;
        line_no++;
        const char *f[MAX_FIELDS];
        size_t fl[MAX_FIELDS];
        int n = 0;
        for (size_t i = at; i < end && n < MAX_FIELDS;) {
            size_t j = i;
            while (j < end && text[j] != ' ')
                j++;
            f[n] = text + i;
            fl[n++] = j - i;
            i = j + 1;
        }
        at = end + 1;
        if (!n)
            goto fail;

        if (remaining) {
            if (n != 3 || !field_is(f[0], fl[0], "file"))
                goto fail;
            Entry *e = &current->entries[current->count];
            Pending *p = &pending[set_count - 1][current->count];
            if (parse_sha(f[1], fl[1], p->sha) || copy_field(e->path, sizeof(e->path), f[2], fl[2]))
                goto fail;
            current->count++;
            remaining--;
            continue;
        }

        if (line_no == 1) {
            if (n != 2 || !field_is(f[0], fl[0], "3DSUA-MANIFEST") || !field_is(f[1], fl[1], "1"))
                goto fail;
        } else if (field_is(f[0], fl[0], "version") && n == 2) {
            if (copy_field(m->version, sizeof(m->version), f[1], fl[1]))
                goto fail;
        } else if (field_is(f[0], fl[0], "blob") && (n == 5 || n == 6)) {
            if (m->blob_count == blob_cap) {
                blob_cap = blob_cap ? blob_cap * 2 : 512;
                Blob *b = realloc(m->blobs, blob_cap * sizeof(Blob));
                if (!b)
                    goto fail;
                m->blobs = b;
                uint8_t (*s)[32] = realloc(base_sha, blob_cap * 32);
                if (!s)
                    goto fail;
                base_sha = s;
            }
            Blob *b = &m->blobs[m->blob_count];
            uint64_t size;
            int whole = field_is(f[3], fl[3], "z");
            if (parse_sha(f[1], fl[1], b->sha) || parse_u64(f[2], fl[2], 10, &size) || size > 0xFFFFFFFFu ||
                copy_field(b->name, sizeof(b->name), f[4], fl[4]) || (whole ? n != 5 : !field_is(f[3], fl[3], "d") || n != 6))
                goto fail;
            b->size = (uint32_t)size;
            b->base = -1;
            if (!whole && parse_sha(f[5], fl[5], base_sha[m->blob_count]))
                goto fail;
            if (whole)
                memset(base_sha[m->blob_count], 0, 32);
            m->blob_count++;
        } else if (field_is(f[0], fl[0], "need") && n == 5) {
            if (m->need_count == need_cap) {
                need_cap = need_cap ? need_cap * 2 : 64;
                Need *nn = realloc(m->needs, need_cap * sizeof(Need));
                if (!nn)
                    goto fail;
                m->needs = nn;
            }
            Need *nd = &m->needs[m->need_count];
            uint64_t remaster;
            if (field_is(f[1], fl[1], "old3ds"))
                nd->model = MODEL_OLD3DS;
            else if (field_is(f[1], fl[1], "new3ds"))
                nd->model = MODEL_NEW3DS;
            else
                goto fail;
            if (fl[2] != 16 || fl[3] != 16 || parse_u64(f[2], 16, 16, &nd->folder) || parse_u64(f[3], 16, 16, &nd->title) ||
                parse_u64(f[4], fl[4], 10, &remaster) || remaster > 0xFFFF)
                goto fail;
            nd->remaster = (uint16_t)remaster;
            m->need_count++;
        } else if (field_is(f[0], fl[0], "ns") && n == 3) {
            uint64_t remaster;
            if (parse_u64(f[1], fl[1], 10, &remaster) || remaster > 0xFFFF || parse_sha(f[2], fl[2], m->ns_code_sha))
                goto fail;
            m->ns_remaster = (uint16_t)remaster;
        } else if (field_is(f[0], fl[0], "fontpath") && n == 2) {
            if (copy_field(m->font_path, sizeof(m->font_path), f[1], fl[1]))
                goto fail;
        } else if (field_is(f[0], fl[0], "upturn") && n == 2) {
            if (copy_field(m->upturn, sizeof(m->upturn), f[1], fl[1]))
                goto fail;
        } else if (field_is(f[0], fl[0], "set") && n == 5) {
            uint64_t count;
            if (parse_u64(f[4], fl[4], 10, &count) || !count || count > 4096 ||
                set_count == sizeof(set_list) / sizeof(set_list[0]))
                goto fail;
            if (field_is(f[1], fl[1], "font")) {
                current = &m->font_set;
            } else {
                int slot = field_is(f[1], fl[1], "ru") ? SLOT_RU : field_is(f[1], fl[1], "en") ? SLOT_EN : -1;
                int model = field_is(f[2], fl[2], "old3ds") ? MODEL_OLD3DS : field_is(f[2], fl[2], "new3ds") ? MODEL_NEW3DS : -1;
                int glyphs = field_is(f[3], fl[3], "default") ? GLYPHS_DEFAULT : field_is(f[3], fl[3], "real") ? GLYPHS_REAL : -1;
                if (slot < 0 || model < 0 || glyphs < 0)
                    goto fail;
                current = &m->sets[slot][model][glyphs];
            }
            if (current->entries)
                goto fail; /* a set listed twice */
            current->entries = calloc(count, sizeof(Entry));
            Pending **grown = realloc(pending, (set_count + 1) * sizeof(Pending *));
            if (!current->entries || !grown)
                goto fail;
            pending = grown;
            pending[set_count] = calloc(count, sizeof(Pending));
            if (!pending[set_count])
                goto fail;
            set_list[set_count++] = current;
            current->count = 0;
            remaining = (size_t)count;
        } else if (field_is(f[0], fl[0], "end") && n == 1) {
            ended = 1;
        } else {
            goto fail;
        }
    }
    if (!ended || remaining || !m->version[0] || !m->font_path[0] || !m->upturn[0] || !m->blob_count)
        goto fail;
    for (int s = 0; s < SLOT_COUNT; s++)
        for (int d = 0; d < MODEL_COUNT; d++)
            for (int g = 0; g < GLYPHS_COUNT; g++)
                if (!m->sets[s][d][g].entries)
                    goto fail;

    /* Resolve every sha now that all blobs are known. */
    Index ix;
    if (index_build(&ix, m))
        goto fail;
    static const uint8_t zero[32];
    int bad = 0;
    for (size_t i = 0; i < m->blob_count && !bad; i++)
        if (memcmp(base_sha[i], zero, 32)) {
            m->blobs[i].base = index_find(&ix, m, base_sha[i]);
            bad = m->blobs[i].base < 0 || m->blobs[m->blobs[i].base].base >= 0; /* no chains */
        }
    for (size_t k = 0; k < set_count && !bad; k++)
        for (size_t i = 0; i < set_list[k]->count && !bad; i++) {
            set_list[k]->entries[i].blob = index_find(&ix, m, pending[k][i].sha);
            bad = set_list[k]->entries[i].blob < 0;
        }
    free(ix.slots);
    if (bad)
        goto fail;

    for (size_t k = 0; k < set_count; k++)
        free(pending[k]);
    free(pending);
    free(base_sha);
    return 0;

fail:
    for (size_t k = 0; k < set_count; k++)
        free(pending[k]);
    free(pending);
    free(base_sha);
    manifest_free(m);
    return line_no ? line_no : 1;
}
