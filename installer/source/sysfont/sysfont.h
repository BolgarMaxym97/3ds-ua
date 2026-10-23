/*
 * Build the shared system font with і І ї Ї є Є ґ Ґ ʼ from the console's own font.
 *
 * A port of tools/sysfont_glyphs.py + tools/bcfnt.py for the installer app. Nothing of
 * Nintendo's ships with the app: seven of the nine glyphs are copies or mirrors of cells
 * the console's font already has, and the remaining two take only the few pixels of the
 * ґ/Ґ upturn from `upturn.bin` (written by tools/sysfont_glyphs.py). The result must be
 * byte for byte the font the release build made - upturn.bin carries the sha256 of both
 * the font it was made from and of that result, and sysfont_build() checks both.
 *
 * Plain C99, no libctru: the same files build for the console and for the host tests.
 */
#ifndef SYSFONT_H
#define SYSFONT_H

#include <stddef.h>
#include <stdint.h>

typedef enum {
    SYSFONT_OK = 0,
    SYSFONT_E_OVERLAY,   /* upturn.bin is damaged */
    SYSFONT_E_SOURCE,    /* the console's font is not the one upturn.bin was made for */
    SYSFONT_E_FORMAT,    /* the font does not parse as an A4 BCFNT */
    SYSFONT_E_GLYPHS,    /* a donor is missing, or a new code point is already there */
    SYSFONT_E_MEMORY,
    SYSFONT_E_TOO_BIG,   /* does not fit the shared font block, or would overwrite itself */
    SYSFONT_E_RESULT,    /* built, but not the font the release build made */
} SysfontStatus;

/* The block NS loads the font into: 0x332000 bytes, 0x80 of them a header. */
#define SYSFONT_BLOCK_DATA (0x332000 - 0x80)

/*
 * stock_lz: cbf_std.bcfnt.lz as read from 0004009B00014002. On success *out_lz is a
 * malloc()ed patched font file of *out_len bytes, ready for FONT_SD_PATH.
 */
SysfontStatus sysfont_build(const uint8_t *stock_lz, size_t stock_len, const uint8_t *upturn, size_t upturn_len,
                            uint8_t **out_lz, size_t *out_len);

/* Bytes to spare when NS inflates the file in place (tools/ns_font.py inplace_slack()). */
long sysfont_inplace_slack(const uint8_t *lz, size_t len);

const char *sysfont_error(SysfontStatus status);

#endif
