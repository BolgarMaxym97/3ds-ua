/*
 * Host test of installer/source/engine/nsips: reading, merging and un-merging the IPS patches
 * Luma applies to NS. The foreign patch is shaped like NetPass's (patches/ns/main.s, patches
 * version 10: 0xB0 bytes at 0x1078, 3 at 0x7794); ours like tools/ns_font.py's (the hook at
 * 0x2170, the stub at 0x1FA40).
 *
 *     ips_test
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "../source/engine/nsips.h"

static int failures;

static void expect(int ok, const char *what)
{
    printf("%s  %s\n", ok ? "ok  " : "FAIL", what);
    failures += !ok;
}

typedef struct {
    uint8_t bytes[2048];
    size_t len;
} Buf;

static void ips_begin(Buf *b)
{
    memcpy(b->bytes, "PATCH", 5);
    b->len = 5;
}

static void ips_record(Buf *b, uint32_t off, uint32_t len, uint8_t seed)
{
    uint8_t *p = b->bytes + b->len;
    p[0] = (uint8_t)(off >> 16), p[1] = (uint8_t)(off >> 8), p[2] = (uint8_t)off;
    p[3] = (uint8_t)(len >> 8), p[4] = (uint8_t)len;
    for (uint32_t i = 0; i < len; i++)
        p[5 + i] = (uint8_t)(seed + i * 13);
    b->len += 5 + len;
}

static void ips_rle(Buf *b, uint32_t off, uint32_t count, uint8_t fill)
{
    uint8_t *p = b->bytes + b->len;
    p[0] = (uint8_t)(off >> 16), p[1] = (uint8_t)(off >> 8), p[2] = (uint8_t)off;
    p[3] = p[4] = 0;
    p[5] = (uint8_t)(count >> 8), p[6] = (uint8_t)count, p[7] = fill;
    b->len += 8;
}

static void ips_end(Buf *b)
{
    memcpy(b->bytes + b->len, "EOF", 3);
    b->len += 3;
}

static void netpass(Buf *b)
{
    ips_begin(b);
    ips_record(b, 0x1078, 0xB0, 0x11);
    ips_record(b, 0x7794, 0x3, 0x39);
    ips_end(b);
}

static void ours(Buf *b)
{
    ips_begin(b);
    ips_record(b, 0x2170, 4, 0xEB);
    ips_record(b, 0x1FA40, 0x174, 0x70);
    ips_end(b);
}

static size_t marks_of(const Buf *b, IpsMark *marks)
{
    IpsRecord r[8];
    size_t n = 0;
    if (ips_parse(b->bytes, b->len, r, 8, &n))
        return 0;
    for (size_t i = 0; i < n; i++)
        ips_mark(&r[i], &marks[i]);
    return n;
}

static void test_parse(void)
{
    Buf b;
    netpass(&b);
    IpsRecord r[8];
    size_t n = 0;
    expect(!ips_parse(b.bytes, b.len, r, 8, &n) && n == 2 && r[0].off == 0x1078 && r[0].len == 0xB0 && !r[0].rle &&
               r[1].off == 0x7794 && r[1].len == 3 && r[1].data == b.bytes + 5 + 5 + 0xB0 + 5,
           "a NetPass-shaped patch: two records, where they are");

    ips_begin(&b);
    ips_rle(&b, 0x400, 0x20, 0xAA);
    ips_end(&b);
    expect(!ips_parse(b.bytes, b.len, r, 8, &n) && n == 1 && r[0].rle && r[0].len == 0x20 && r[0].data[0] == 0xAA,
           "an RLE record: its count is the length, data is the fill byte");

    ips_begin(&b);
    ips_end(&b);
    expect(!ips_parse(b.bytes, b.len, r, 8, &n) && n == 0 && ips_empty(b.bytes, b.len), "PATCHEOF: no records");

    static const char *names[] = {"no PATCH header", "a record past the end", "no EOF", "bytes after EOF",
                                  "the string engine_test used as a foreign patch", "more records than room for"};
    for (int k = 0; k < 6; k++) {
        netpass(&b);
        if (k == 0)
            b.bytes[0] = 'X';
        else if (k == 1)
            b.len -= 3 + 2; /* the last record's data runs into the end */
        else if (k == 2)
            b.len -= 3;
        else if (k == 3)
            memcpy(b.bytes + b.len, "\x01\x02\x03", 3), b.len += 3;
        else if (k == 4)
            b.len = (size_t)sprintf((char *)b.bytes, "PATCHsomeone else's NS patchEOF");
        size_t cap = k == 5 ? 1 : 8;
        char msg[96];
        snprintf(msg, sizeof(msg), "refused: %s", names[k]);
        expect(ips_parse(b.bytes, b.len, r, cap, &n) == -1, msg);
    }
}

static void test_touches(void)
{
    Buf b;
    netpass(&b);
    IpsRecord r[8];
    size_t n = 0;
    ips_parse(b.bytes, b.len, r, 8, &n);
    const IpsRange mine[] = {{0x2170, 4}, {0x1FA40, 0x174}};
    const IpsRange inside[] = {{0x1100, 4}};
    const IpsRange edge_after[] = {{0x1078 + 0xB0, 4}};
    const IpsRange edge_last[] = {{0x1078 + 0xAF, 1}};
    expect(!ips_touches(r, n, mine, 2), "NetPass's records stay clear of ours");
    expect(ips_touches(r, n, inside, 1), "a range inside a record is touched");
    expect(!ips_touches(r, n, edge_after, 1), "the byte right after a record is not");
    expect(ips_touches(r, n, edge_last, 1), "a record's last byte is");
}

static void test_merge_and_strip(void)
{
    Buf foreign, mine;
    netpass(&foreign);
    ours(&mine);
    IpsMark marks[8];
    size_t nm = marks_of(&mine, marks);

    uint8_t *merged = NULL, *back = NULL, *again = NULL;
    size_t merged_len = 0, back_len = 0, again_len = 0, removed = 0;
    expect(!ips_append(foreign.bytes, foreign.len, mine.bytes, mine.len, &merged, &merged_len) &&
               merged_len == foreign.len + mine.len - 5 - 3 && !memcmp(merged, foreign.bytes, foreign.len - 3) &&
               !memcmp(merged + foreign.len - 3, mine.bytes + 5, mine.len - 5),
           "append: the foreign bytes up to EOF, then our records and EOF");

    expect(!ips_strip(merged, merged_len, marks, nm, &back, &back_len, &removed) && removed == 2 &&
               back_len == foreign.len && !memcmp(back, foreign.bytes, foreign.len),
           "strip of the merged file gives the foreign file back byte for byte");

    free(back);
    back = NULL;
    expect(!ips_strip(merged, merged_len, marks, nm, &back, &back_len, &removed) &&
               !ips_append(back, back_len, mine.bytes, mine.len, &again, &again_len) && again_len == merged_len &&
               !memcmp(again, merged, merged_len),
           "strip then append again is the same merge: no doubled records");
    free(back);
    free(again);
    back = again = NULL;

    expect(!ips_strip(foreign.bytes, foreign.len, marks, nm, &back, &back_len, &removed) && removed == 0 &&
               back_len == foreign.len && !memcmp(back, foreign.bytes, foreign.len),
           "strip of a file without our records changes nothing");
    free(back);
    back = NULL;

    expect(!ips_strip(mine.bytes, mine.len, marks, nm, &back, &back_len, &removed) && removed == 2 &&
               ips_empty(back, back_len),
           "strip of our own patch leaves an empty one");
    free(back);
    back = NULL;

    /* a record of ours with other bytes (another build of the stub) is not ours to strip */
    merged[merged_len - 3 - 1] ^= 0xFF;
    expect(!ips_strip(merged, merged_len, marks, nm, &back, &back_len, &removed) && removed == 1,
           "a record at our offset with other bytes stays");
    free(back);
    free(merged);

    uint8_t *out = NULL;
    size_t out_len = 0;
    Buf bad;
    bad.len = (size_t)sprintf((char *)bad.bytes, "PATCHsomeone else's NS patchEOF");
    expect(ips_append(bad.bytes, bad.len, mine.bytes, mine.len, &out, &out_len) == -1 && !out,
           "append refuses a foreign file that does not parse");
    expect(ips_strip(bad.bytes, bad.len, marks, nm, &out, &out_len, &removed) == -1 && !out,
           "strip refuses one too");
}

int main(void)
{
    test_parse();
    test_touches();
    test_merge_and_strip();
    printf(failures ? "FAILED\n" : "all passed\n");
    return failures ? 1 : 0;
}
