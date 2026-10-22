#include "sysfont.h"

#include <stdlib.h>
#include <string.h>

#include "lz11.h"
#include "sha256.h"

#define HEADER_SIZE 0x14
#define BLOCK_HEADER 8
#define FORMAT_A4 11
#define MAX_BLOCKS 64
#define NO_GLYPH 0xFFFF

enum { MAP_DIRECT = 0, MAP_TABLE = 1, MAP_SCAN = 2 };

/* The glyphs that are a cell the font already has (tools/sysfont_glyphs.py COPY, MIRROR). */
static const struct {
    uint16_t code, donor;
    uint8_t mirror;
} DERIVED[] = {
    {0x0456, 0x0069, 0}, /* і <- i */
    {0x0406, 0x0049, 0}, /* І <- I */
    {0x0457, 0x00EF, 0}, /* ї <- ï */
    {0x0407, 0x00CF, 0}, /* Ї <- Ï */
    {0x02BC, 0x2019, 0}, /* ʼ <- ’ */
    {0x0454, 0x044D, 1}, /* є <- э, mirrored */
    {0x0404, 0x042D, 1}, /* Є <- Э, mirrored */
};
#define DERIVED_COUNT (sizeof(DERIVED) / sizeof(DERIVED[0]))
#define MAX_NEW 16

static uint16_t rd16(const uint8_t *p) { return (uint16_t)(p[0] | p[1] << 8); }
static uint32_t rd32(const uint8_t *p) { return p[0] | p[1] << 8 | p[2] << 16 | (uint32_t)p[3] << 24; }
static void wr16(uint8_t *p, uint32_t v) { p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); }
static void wr32(uint8_t *p, uint32_t v) { wr16(p, v); wr16(p + 2, v >> 16); }
static size_t pad4(size_t n) { return (n + 3) & ~(size_t)3; }

typedef struct {
    char magic[4];
    const uint8_t *body;
    uint32_t len;
} Block;

typedef struct {
    int8_t left;
    uint8_t ink, advance;
} Width;

typedef struct {
    uint16_t begin, end, method;
} CmapLayout;

typedef struct {
    uint32_t version;
    const uint8_t *finf;
    uint32_t finf_len;
    /* TGLP */
    uint8_t cell_w, cell_h, baseline, max_char_w;
    uint32_t sheet_size;
    uint16_t sheets, columns, rows, width, height;
    const uint8_t *pixels;
    /* CWDH, CMAP */
    Width *widths;
    size_t glyphs;
    uint16_t *map; /* code point -> glyph index, NO_GLYPH where none */
    CmapLayout cmaps[MAX_BLOCKS];
    size_t cmap_count;
    Block extra[MAX_BLOCKS];
    size_t extra_count;
} Font;

typedef struct {
    uint16_t code, donor;
    uint8_t cell[32 * 32]; /* cell_h rows of cell_w alpha values */
    Width width;
} NewGlyph;

/* ---------------------------------------------------------------- A4 sheets */

static uint8_t morton_index[8][8]; /* [y][x] -> byte-pair index inside an 8x8 tile */

static void init_morton(void)
{
    for (int i = 0; i < 64; i++) {
        int x = (i & 1) | ((i >> 1) & 2) | ((i >> 2) & 4);
        int y = ((i >> 1) & 1) | ((i >> 2) & 2) | ((i >> 3) & 4);
        morton_index[y][x] = (uint8_t)i;
    }
}

/* Byte offset of pixel (x, y) inside one sheet, and whether it is the high nibble. */
static size_t pixel_at(const Font *f, int x, int y, int *high)
{
    size_t tile = (size_t)(y / 8) * (f->width / 8) + (size_t)(x / 8);
    int i = morton_index[y % 8][x % 8];
    *high = i & 1;
    return tile * 32 + (size_t)(i / 2);
}

static void cell_origin(const Font *f, size_t index, size_t *sheet, int *x0, int *y0)
{
    size_t per_sheet = (size_t)f->columns * f->rows;
    size_t cell = index % per_sheet;
    *sheet = index / per_sheet;
    *x0 = (int)(cell % f->columns) * (f->cell_w + 1) + 1;
    *y0 = (int)(cell / f->columns) * (f->cell_h + 1) + 1;
}

static void read_cell(const Font *f, size_t index, uint8_t *cell)
{
    size_t sheet;
    int x0, y0, high;
    cell_origin(f, index, &sheet, &x0, &y0);
    const uint8_t *plane = f->pixels + sheet * f->sheet_size;
    for (int y = 0; y < f->cell_h; y++)
        for (int x = 0; x < f->cell_w; x++) {
            uint8_t b = plane[pixel_at(f, x0 + x, y0 + y, &high)];
            cell[y * f->cell_w + x] = high ? b >> 4 : b & 0x0F;
        }
}

static void write_cell(const Font *f, uint8_t *pixels, size_t index, const uint8_t *cell)
{
    size_t sheet;
    int x0, y0, high;
    cell_origin(f, index, &sheet, &x0, &y0);
    uint8_t *plane = pixels + sheet * f->sheet_size;
    for (int y = 0; y < f->cell_h; y++)
        for (int x = 0; x < f->cell_w; x++) {
            uint8_t *b = plane + pixel_at(f, x0 + x, y0 + y, &high);
            uint8_t v = cell[y * f->cell_w + x] & 0x0F;
            *b = high ? (uint8_t)((*b & 0x0F) | v << 4) : (uint8_t)((*b & 0xF0) | v);
        }
}

/* ---------------------------------------------------------------- parse */

static void font_free(Font *f)
{
    free(f->widths);
    free(f->map);
}

static int parse_cmap(Font *f, const uint8_t *body, uint32_t len)
{
    if (len < 14 || f->cmap_count == MAX_BLOCKS)
        return -1;
    uint16_t begin = rd16(body), end = rd16(body + 2), method = rd16(body + 4);
    const uint8_t *data = body + 12;
    size_t room = len - 12;
    if (end < begin)
        return -1;
    f->cmaps[f->cmap_count++] = (CmapLayout){begin, end, method};

    if (method == MAP_DIRECT) {
        uint16_t first = rd16(data);
        if (first != NO_GLYPH)
            for (uint32_t c = begin; c <= end; c++)
                f->map[c] = (uint16_t)(first + (c - begin));
    } else if (method == MAP_TABLE) {
        if (room < 2u * (end - begin + 1u))
            return -1;
        for (uint32_t i = 0; i <= (uint32_t)(end - begin); i++) {
            uint16_t index = rd16(data + 2 * i);
            if (index != NO_GLYPH)
                f->map[begin + i] = index;
        }
    } else if (method == MAP_SCAN) {
        uint16_t count = rd16(data);
        if (room < 2u + 4u * count)
            return -1;
        for (uint32_t i = 0; i < count; i++) {
            uint16_t code = rd16(data + 2 + 4 * i), index = rd16(data + 4 + 4 * i);
            if (index != NO_GLYPH)
                f->map[code] = index;
        }
    } else {
        return -1;
    }
    return 0;
}

static int parse(Font *f, const uint8_t *data, size_t len)
{
    memset(f, 0, sizeof(*f));
    if (len < HEADER_SIZE || memcmp(data, "CFNT", 4) != 0 || rd16(data + 4) != 0xFEFF)
        return -1;
    f->version = rd32(data + 8);
    uint32_t blocks = rd32(data + 0x10);
    f->map = malloc(65536 * sizeof(uint16_t));
    if (!f->map)
        return -1;
    memset(f->map, 0xFF, 65536 * sizeof(uint16_t));

    /* CWDH may come in several blocks; gather them, then demand indices 0..n-1. */
    size_t width_cap = 0;
    size_t offset = rd16(data + 6);
    for (uint32_t b = 0; b < blocks; b++) {
        if (offset + BLOCK_HEADER > len)
            return -1;
        const uint8_t *head = data + offset;
        uint32_t size = rd32(head + 4);
        if (size < BLOCK_HEADER || offset + size > len)
            return -1;
        const uint8_t *body = head + BLOCK_HEADER;
        uint32_t body_len = size - BLOCK_HEADER;

        if (!memcmp(head, "FINF", 4)) {
            if (body_len < 20)
                return -1;
            f->finf = body;
            f->finf_len = body_len;
        } else if (!memcmp(head, "TGLP", 4)) {
            if (body_len < 24)
                return -1;
            f->cell_w = body[0];
            f->cell_h = body[1];
            f->baseline = body[2];
            f->max_char_w = body[3];
            f->sheet_size = rd32(body + 4);
            f->sheets = rd16(body + 8);
            uint16_t format = rd16(body + 10);
            f->columns = rd16(body + 12);
            f->rows = rd16(body + 14);
            f->width = rd16(body + 16);
            f->height = rd16(body + 18);
            uint32_t sheet_offset = rd32(body + 20);
            if (format != FORMAT_A4 || f->sheet_size != (uint32_t)f->width * f->height / 2 || !f->columns || !f->rows ||
                f->width % 8 || f->height % 8 || f->cell_w > 32 || f->cell_h > 32 ||
                (uint64_t)sheet_offset + (uint64_t)f->sheets * f->sheet_size > len)
                return -1;
            f->pixels = data + sheet_offset;
        } else if (!memcmp(head, "CWDH", 4)) {
            if (body_len < 8)
                return -1;
            uint16_t start = rd16(body), end = rd16(body + 2);
            if (end < start || body_len < 8u + 3u * (end - start + 1u))
                return -1;
            if ((size_t)end + 1 > width_cap) {
                Width *grown = realloc(f->widths, ((size_t)end + 1 + MAX_NEW) * sizeof(Width));
                if (!grown)
                    return -1;
                memset(grown + width_cap, 0xFF, ((size_t)end + 1 + MAX_NEW - width_cap) * sizeof(Width));
                f->widths = grown;
                width_cap = (size_t)end + 1;
            }
            for (uint32_t i = 0; i <= (uint32_t)(end - start); i++) {
                const uint8_t *e = body + 8 + 3 * i;
                f->widths[start + i] = (Width){(int8_t)e[0], e[1], e[2]};
            }
            if ((size_t)end + 1 > f->glyphs)
                f->glyphs = (size_t)end + 1;
        } else if (!memcmp(head, "CMAP", 4)) {
            if (parse_cmap(f, body, body_len))
                return -1;
        } else {
            if (f->extra_count == MAX_BLOCKS)
                return -1;
            Block *x = &f->extra[f->extra_count++];
            memcpy(x->magic, head, 4);
            x->body = body;
            x->len = body_len;
        }
        offset += size;
    }
    if (!f->finf || !f->pixels || !f->glyphs || !f->cmap_count)
        return -1;
    for (size_t i = 0; i < f->glyphs; i++)
        if (f->widths[i].ink == 0xFF && f->widths[i].advance == 0xFF && f->widths[i].left == -1)
            return -1; /* a hole in the CWDH range: not contiguous from 0 */
    return 0;
}

/* ---------------------------------------------------------------- glyphs */

static SysfontStatus make_glyphs(const Font *f, const uint8_t *upturn, size_t upturn_len, NewGlyph *out, size_t *count)
{
    size_t n = 0;
    for (size_t i = 0; i < DERIVED_COUNT; i++) {
        uint16_t donor = f->map[DERIVED[i].donor];
        if (donor == NO_GLYPH || donor >= f->glyphs || f->map[DERIVED[i].code] != NO_GLYPH)
            return SYSFONT_E_GLYPHS;
        NewGlyph *g = &out[n++];
        g->code = DERIVED[i].code;
        g->donor = DERIVED[i].donor;
        read_cell(f, donor, g->cell);
        Width w = f->widths[donor];
        if (DERIVED[i].mirror) {
            /* row[:ink][::-1] + row[ink:]; the side bearings swap */
            if (w.ink > f->cell_w)
                return SYSFONT_E_GLYPHS;
            for (int y = 0; y < f->cell_h; y++) {
                uint8_t *row = g->cell + y * f->cell_w;
                for (int a = 0, b = w.ink - 1; a < b; a++, b--) {
                    uint8_t t = row[a];
                    row[a] = row[b];
                    row[b] = t;
                }
            }
            w.left = (int8_t)(w.advance - w.left - w.ink);
        }
        g->width = w;
    }

    /* upturn.bin, past the 70-byte header sysfont_build() already checked */
    size_t at = 70, glyphs = upturn[5];
    for (size_t i = 0; i < glyphs; i++) {
        if (n == MAX_NEW || at + 6 > upturn_len)
            return SYSFONT_E_OVERLAY;
        NewGlyph *g = &out[n++];
        g->code = rd16(upturn + at);
        g->donor = rd16(upturn + at + 2);
        size_t pixels = rd16(upturn + at + 4);
        at += 6;
        uint16_t donor = f->map[g->donor];
        if (donor == NO_GLYPH || donor >= f->glyphs || f->map[g->code] != NO_GLYPH)
            return SYSFONT_E_GLYPHS;
        read_cell(f, donor, g->cell);
        g->width = f->widths[donor];
        if (at + 3 * pixels > upturn_len)
            return SYSFONT_E_OVERLAY;
        for (size_t p = 0; p < pixels; p++, at += 3) {
            uint8_t x = upturn[at], y = upturn[at + 1], v = upturn[at + 2];
            if (x >= f->cell_w || y >= f->cell_h || v > 15)
                return SYSFONT_E_OVERLAY;
            g->cell[y * f->cell_w + x] = v;
        }
    }
    if (at != upturn_len)
        return SYSFONT_E_OVERLAY;

    /* bcfnt.add_glyphs() hands out indices in code point order */
    for (size_t i = 1; i < n; i++)
        for (size_t j = i; j > 0 && out[j - 1].code > out[j].code; j--) {
            NewGlyph t = out[j];
            out[j] = out[j - 1];
            out[j - 1] = t;
        }
    *count = n;
    return SYSFONT_OK;
}

/* ---------------------------------------------------------------- build */

static size_t cmap_body_len(const CmapLayout *c, const uint16_t *map, const uint8_t *placed)
{
    size_t len = 12;
    if (c->method == MAP_DIRECT) {
        len += 2;
    } else if (c->method == MAP_TABLE) {
        len += 2u * (c->end - c->begin + 1u);
    } else {
        size_t taken = 0;
        for (uint32_t code = c->begin; code <= c->end; code++)
            taken += map[code] != NO_GLYPH && !placed[code];
        len += 2 + 4 * taken;
    }
    return pad4(len);
}

/* The bcfnt.build() of the patched font: FINF, TGLP, CWDH, the CMAP chain, the rest. */
static SysfontStatus build(const Font *f, const NewGlyph *glyphs, size_t count, uint8_t **out, size_t *out_len)
{
    size_t total = f->glyphs + count;
    size_t per_sheet = (size_t)f->columns * f->rows;
    size_t sheets = f->sheets;
    while (sheets * per_sheet < total)
        sheets++;

    uint16_t *map = malloc(65536 * sizeof(uint16_t));
    uint8_t *placed = calloc(65536, 1);
    if (!map || !placed) {
        free(map);
        free(placed);
        return SYSFONT_E_MEMORY;
    }
    memcpy(map, f->map, 65536 * sizeof(uint16_t));
    for (size_t i = 0; i < count; i++)
        map[glyphs[i].code] = (uint16_t)(f->glyphs + i);

    /* Lay the blocks out. */
    size_t finf_at = HEADER_SIZE;
    size_t tglp_at = finf_at + BLOCK_HEADER + f->finf_len;
    size_t tglp_body = tglp_at + BLOCK_HEADER;
    size_t data_offset = (tglp_body + 24 + 0x7F) & ~(size_t)0x7F;
    size_t tglp_len = data_offset - tglp_body + sheets * f->sheet_size;
    size_t cwdh_at = tglp_at + BLOCK_HEADER + tglp_len;
    size_t cwdh_len = pad4(8 + 3 * total);
    size_t cmap_at[MAX_BLOCKS], cmap_len[MAX_BLOCKS];
    size_t at = cwdh_at + BLOCK_HEADER + cwdh_len;
    {
        uint8_t *probe = calloc(65536, 1);
        if (!probe) {
            free(map);
            free(placed);
            return SYSFONT_E_MEMORY;
        }
        for (size_t i = 0; i < f->cmap_count; i++) {
            const CmapLayout *c = &f->cmaps[i];
            cmap_at[i] = at;
            cmap_len[i] = cmap_body_len(c, map, probe);
            for (uint32_t code = c->begin; code <= c->end; code++)
                if (map[code] != NO_GLYPH)
                    probe[code] = 1;
            at += BLOCK_HEADER + cmap_len[i];
        }
        free(probe);
    }
    size_t extra_at = at;
    for (size_t i = 0; i < f->extra_count; i++)
        at += BLOCK_HEADER + f->extra[i].len;
    size_t file_size = at;
    if (file_size > SYSFONT_BLOCK_DATA) {
        free(map);
        free(placed);
        return SYSFONT_E_TOO_BIG;
    }

    uint8_t *o = calloc(file_size, 1);
    if (!o) {
        free(map);
        free(placed);
        return SYSFONT_E_MEMORY;
    }

    memcpy(o, "CFNT", 4);
    wr16(o + 4, 0xFEFF);
    wr16(o + 6, HEADER_SIZE);
    wr32(o + 8, f->version);
    wr32(o + 12, (uint32_t)file_size);
    wr32(o + 16, (uint32_t)(3 + f->cmap_count + f->extra_count));

    memcpy(o + finf_at, "FINF", 4);
    wr32(o + finf_at + 4, BLOCK_HEADER + f->finf_len);
    memcpy(o + finf_at + BLOCK_HEADER, f->finf, f->finf_len);
    wr32(o + finf_at + BLOCK_HEADER + 8, (uint32_t)tglp_body);
    wr32(o + finf_at + BLOCK_HEADER + 12, (uint32_t)(cwdh_at + BLOCK_HEADER));
    wr32(o + finf_at + BLOCK_HEADER + 16, (uint32_t)(cmap_at[0] + BLOCK_HEADER));

    uint8_t *t = o + tglp_at;
    memcpy(t, "TGLP", 4);
    wr32(t + 4, (uint32_t)(BLOCK_HEADER + tglp_len));
    t += BLOCK_HEADER;
    t[0] = f->cell_w;
    t[1] = f->cell_h;
    t[2] = f->baseline;
    t[3] = f->max_char_w;
    wr32(t + 4, f->sheet_size);
    wr16(t + 8, (uint32_t)sheets);
    wr16(t + 10, FORMAT_A4);
    wr16(t + 12, f->columns);
    wr16(t + 14, f->rows);
    wr16(t + 16, f->width);
    wr16(t + 18, f->height);
    wr32(t + 20, (uint32_t)data_offset);
    uint8_t *pixels = o + data_offset;
    memcpy(pixels, f->pixels, (size_t)f->sheets * f->sheet_size);
    for (size_t i = 0; i < count; i++)
        write_cell(f, pixels, f->glyphs + i, glyphs[i].cell);

    uint8_t *w = o + cwdh_at;
    memcpy(w, "CWDH", 4);
    wr32(w + 4, (uint32_t)(BLOCK_HEADER + cwdh_len));
    w += BLOCK_HEADER;
    wr16(w, 0);
    wr16(w + 2, (uint32_t)(total - 1));
    wr32(w + 4, 0);
    for (size_t i = 0; i < total; i++) {
        Width e = i < f->glyphs ? f->widths[i] : glyphs[i - f->glyphs].width;
        w[8 + 3 * i] = (uint8_t)e.left;
        w[9 + 3 * i] = e.ink;
        w[10 + 3 * i] = e.advance;
    }

    SysfontStatus status = SYSFONT_OK;
    for (size_t i = 0; i < f->cmap_count && status == SYSFONT_OK; i++) {
        const CmapLayout *c = &f->cmaps[i];
        uint8_t *m = o + cmap_at[i];
        memcpy(m, "CMAP", 4);
        wr32(m + 4, (uint32_t)(BLOCK_HEADER + cmap_len[i]));
        m += BLOCK_HEADER;
        wr16(m, c->begin);
        wr16(m + 2, c->end);
        wr16(m + 4, c->method);
        wr32(m + 8, i + 1 < f->cmap_count ? (uint32_t)(cmap_at[i + 1] + BLOCK_HEADER) : 0);
        uint8_t *d = m + 12;
        if (c->method == MAP_DIRECT) {
            uint16_t first = map[c->begin] != NO_GLYPH && !placed[c->begin] ? map[c->begin] : NO_GLYPH;
            int any = 0;
            for (uint32_t code = c->begin; code <= c->end; code++)
                any |= map[code] != NO_GLYPH && !placed[code];
            if (any)
                for (uint32_t code = c->begin; code <= c->end; code++) {
                    uint16_t want = (uint16_t)(first + (code - c->begin));
                    uint16_t have = map[code] != NO_GLYPH && !placed[code] ? map[code] : NO_GLYPH;
                    if (have != want || first == NO_GLYPH)
                        status = SYSFONT_E_FORMAT; /* no longer a direct run */
                }
            wr16(d, first);
        } else if (c->method == MAP_TABLE) {
            for (uint32_t code = c->begin; code <= c->end; code++)
                wr16(d + 2 * (code - c->begin), map[code] != NO_GLYPH && !placed[code] ? map[code] : NO_GLYPH);
        } else {
            uint16_t taken = 0;
            for (uint32_t code = c->begin; code <= c->end; code++)
                if (map[code] != NO_GLYPH && !placed[code]) {
                    wr16(d + 2 + 4 * taken, code);
                    wr16(d + 4 + 4 * taken, map[code]);
                    taken++;
                }
            wr16(d, taken);
        }
        for (uint32_t code = c->begin; code <= c->end; code++)
            if (map[code] != NO_GLYPH)
                placed[code] = 1;
    }
    for (uint32_t code = 0; code < 65536 && status == SYSFONT_OK; code++)
        if (map[code] != NO_GLYPH && !placed[code])
            status = SYSFONT_E_FORMAT; /* no CMAP block covers it */

    at = extra_at;
    for (size_t i = 0; i < f->extra_count; i++) {
        memcpy(o + at, f->extra[i].magic, 4);
        wr32(o + at + 4, BLOCK_HEADER + f->extra[i].len);
        memcpy(o + at + BLOCK_HEADER, f->extra[i].body, f->extra[i].len);
        at += BLOCK_HEADER + f->extra[i].len;
    }

    free(map);
    free(placed);
    if (status != SYSFONT_OK) {
        free(o);
        return status;
    }
    *out = o;
    *out_len = file_size;
    return SYSFONT_OK;
}

/* ---------------------------------------------------------------- entry points */

long sysfont_inplace_slack(const uint8_t *lz, size_t len)
{
    size_t size = lz11_size(lz, len);
    if (!size)
        return -1;
    size_t p = (lz[1] | lz[2] | lz[3]) ? 4 : 8;
    size_t out = 0;
    long worst = 0;
    while (out < size) {
        if (p >= len)
            return -1;
        uint8_t flags = lz[p++];
        for (int bit = 0; bit < 8 && out < size; bit++) {
            if (flags & (0x80 >> bit)) {
                if (p + 1 >= len)
                    return -1;
                int kind = lz[p] >> 4;
                if (kind == 0) {
                    out += (size_t)(((lz[p] & 0xF) << 4) | (lz[p + 1] >> 4)) + 0x11;
                    p += 3;
                } else if (kind == 1) {
                    if (p + 2 >= len)
                        return -1;
                    out += (((size_t)(lz[p] & 0xF) << 12) | (lz[p + 1] << 4) | (lz[p + 2] >> 4)) + 0x111;
                    p += 4;
                } else {
                    out += (size_t)kind + 1;
                    p += 2;
                }
            } else {
                out++;
                p++;
            }
            if ((long)out - (long)p > worst)
                worst = (long)out - (long)p;
        }
    }
    return (long)(SYSFONT_BLOCK_DATA - pad4(len)) - worst;
}

SysfontStatus sysfont_build(const uint8_t *stock_lz, size_t stock_len, const uint8_t *upturn, size_t upturn_len,
                            uint8_t **out_lz, size_t *out_len)
{
    uint8_t digest[32];
    if (upturn_len < 70 || memcmp(upturn, "UAUP", 4) != 0 || upturn[4] != 1)
        return SYSFONT_E_OVERLAY;
    sha256(stock_lz, stock_len, digest);
    if (memcmp(digest, upturn + 6, 32) != 0)
        return SYSFONT_E_SOURCE;

    size_t plain_len = lz11_size(stock_lz, stock_len);
    uint8_t *plain = plain_len ? malloc(plain_len) : NULL;
    if (!plain)
        return plain_len ? SYSFONT_E_MEMORY : SYSFONT_E_FORMAT;
    if (lz11_decompress(stock_lz, stock_len, plain, plain_len)) {
        free(plain);
        return SYSFONT_E_FORMAT;
    }

    init_morton();
    Font font;
    SysfontStatus status = parse(&font, plain, plain_len) ? SYSFONT_E_FORMAT : SYSFONT_OK;
    NewGlyph *glyphs = NULL;
    size_t count = 0;
    uint8_t *patched = NULL;
    size_t patched_len = 0;
    if (status == SYSFONT_OK) {
        glyphs = malloc(MAX_NEW * sizeof(NewGlyph));
        status = glyphs ? make_glyphs(&font, upturn, upturn_len, glyphs, &count) : SYSFONT_E_MEMORY;
    }
    if (status == SYSFONT_OK)
        status = build(&font, glyphs, count, &patched, &patched_len);
    free(glyphs);
    font_free(&font);
    free(plain);
    if (status != SYSFONT_OK)
        return status;

    size_t cap = lz11_bound(patched_len);
    uint8_t *packed = malloc(cap);
    size_t packed_len = packed ? lz11_compress(patched, patched_len, packed, cap) : 0;
    free(patched);
    if (!packed_len) {
        free(packed);
        return SYSFONT_E_MEMORY;
    }

    sha256(packed, packed_len, digest);
    if (memcmp(digest, upturn + 38, 32) != 0) {
        free(packed);
        return SYSFONT_E_RESULT;
    }
    if (sysfont_inplace_slack(packed, packed_len) <= 0) {
        free(packed);
        return SYSFONT_E_TOO_BIG;
    }
    *out_lz = packed;
    *out_len = packed_len;
    return SYSFONT_OK;
}

const char *sysfont_error(SysfontStatus status)
{
    switch (status) {
    case SYSFONT_OK: return "ok";
    case SYSFONT_E_OVERLAY: return "upturn.bin is damaged";
    case SYSFONT_E_SOURCE: return "the console font is not the one this release was made for";
    case SYSFONT_E_FORMAT: return "the console font does not parse";
    case SYSFONT_E_GLYPHS: return "a donor glyph is missing or a new letter is already there";
    case SYSFONT_E_MEMORY: return "out of memory";
    case SYSFONT_E_TOO_BIG: return "the font does not fit the shared font block";
    case SYSFONT_E_RESULT: return "the built font differs from the release build";
    }
    return "unknown error";
}
