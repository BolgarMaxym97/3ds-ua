/*
 * Host test of installer/source/sysfont: the C build of the font must be byte for byte the
 * one tools/sysfont_glyphs.py wrote, and the safeguards must refuse what they should.
 *
 *     sysfont_test <stock cbf_std.bcfnt.lz> <upturn.bin> <expected cbf_std.bcfnt.lz>
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "../source/sysfont/lz11.h"
#include "../source/sysfont/sha256.h"
#include "../source/sysfont/sysfont.h"

static uint8_t *slurp(const char *path, size_t *len)
{
    FILE *f = fopen(path, "rb");
    if (!f) {
        fprintf(stderr, "cannot open %s\n", path);
        exit(2);
    }
    fseek(f, 0, SEEK_END);
    *len = (size_t)ftell(f);
    fseek(f, 0, SEEK_SET);
    uint8_t *data = malloc(*len);
    if (!data || fread(data, 1, *len, f) != *len) {
        fprintf(stderr, "cannot read %s\n", path);
        exit(2);
    }
    fclose(f);
    return data;
}

static int failures;

static void expect(int ok, const char *what)
{
    printf("%s  %s\n", ok ? "ok  " : "FAIL", what);
    failures += !ok;
}

static void expect_status(SysfontStatus got, SysfontStatus want, const char *what)
{
    char line[200];
    snprintf(line, sizeof(line), "%s -> %s", what, sysfont_error(got));
    expect(got == want, line);
}

int main(int argc, char **argv)
{
    if (argc != 4) {
        fprintf(stderr, "usage: %s <stock.lz> <upturn.bin> <expected.lz>\n", argv[0]);
        return 2;
    }
    size_t stock_len, upturn_len, expected_len;
    uint8_t *stock = slurp(argv[1], &stock_len);
    uint8_t *upturn = slurp(argv[2], &upturn_len);
    uint8_t *expected = slurp(argv[3], &expected_len);

    /* sha256 against a known vector */
    uint8_t digest[32];
    sha256("abc", 3, digest);
    expect(digest[0] == 0xba && digest[1] == 0x78 && digest[31] == 0xad, "sha256(\"abc\") = ba78...15ad");

    /* LZ11 round trip of the stock font through our decoder and packer */
    size_t plain_len = lz11_size(stock, stock_len);
    uint8_t *plain = malloc(plain_len);
    expect(plain && lz11_decompress(stock, stock_len, plain, plain_len) == 0, "stock font inflates");
    uint8_t *packed = malloc(lz11_bound(plain_len));
    size_t packed_len = lz11_compress(plain, plain_len, packed, lz11_bound(plain_len));
    uint8_t *again = malloc(plain_len);
    expect(packed_len && lz11_decompress(packed, packed_len, again, plain_len) == 0 && !memcmp(again, plain, plain_len),
           "our LZ11 packer round-trips the stock font");

    /* the real thing */
    uint8_t *out = NULL;
    size_t out_len = 0;
    clock_t start = clock();
    SysfontStatus status = sysfont_build(stock, stock_len, upturn, upturn_len, &out, &out_len);
    double seconds = (double)(clock() - start) / CLOCKS_PER_SEC;
    expect_status(status, SYSFONT_OK, "build the patched font");
    char line[200];
    snprintf(line, sizeof(line), "identical to the Python build (%zu bytes, %.2f s on this host)", out_len, seconds);
    expect(status == SYSFONT_OK && out_len == expected_len && !memcmp(out, expected, out_len), line);
    if (status == SYSFONT_OK && (out_len != expected_len || memcmp(out, expected, out_len))) {
        size_t i = 0;
        while (i < out_len && i < expected_len && out[i] == expected[i])
            i++;
        printf("      first difference at byte 0x%zx (sizes %zu vs %zu)\n", i, out_len, expected_len);
    }
    snprintf(line, sizeof(line), "inflate slack %ld bytes", status == SYSFONT_OK ? sysfont_inplace_slack(out, out_len) : -1);
    expect(status == SYSFONT_OK && sysfont_inplace_slack(out, out_len) == 220801, line);
    free(out);

    /* safeguards */
    uint8_t *other = malloc(stock_len);
    memcpy(other, stock, stock_len);
    other[stock_len / 2] ^= 1;
    expect_status(sysfont_build(other, stock_len, upturn, upturn_len, &out, &out_len), SYSFONT_E_SOURCE,
                  "a different console font is refused");

    uint8_t *damaged = malloc(upturn_len);
    memcpy(damaged, upturn, upturn_len);
    damaged[0] = 'X';
    expect_status(sysfont_build(stock, stock_len, damaged, upturn_len, &out, &out_len), SYSFONT_E_OVERLAY,
                  "a damaged upturn.bin is refused");
    memcpy(damaged, upturn, upturn_len);
    expect_status(sysfont_build(stock, stock_len, damaged, upturn_len - 1, &out, &out_len), SYSFONT_E_OVERLAY,
                  "a truncated upturn.bin is refused");
    memcpy(damaged, upturn, upturn_len);
    damaged[upturn_len - 1] ^= 1; /* one upturn pixel differs: the result hash must catch it */
    expect_status(sysfont_build(stock, stock_len, damaged, upturn_len, &out, &out_len), SYSFONT_E_RESULT,
                  "a font that is not the release build is refused");

    printf("%s\n", failures ? "FAILED" : "all passed");
    return failures ? 1 : 0;
}
