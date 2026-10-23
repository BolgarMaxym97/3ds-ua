/*
 * LZ11 (Nintendo LZ77 type 0x11), the packing of the shared system font.
 *
 * A port of tools/lz11.py. compress() has to produce the Python packer's bytes exactly -
 * the installer checks the font it builds on the console against the sha256 the release
 * build computed - so it makes the same choices in the same order: greedy, longest match,
 * the nearest one on a tie. Only the search is faster (a hash chain instead of rfind).
 *
 * Plain C99, no libctru: the same file builds for the console and for the host tests.
 */
#ifndef SYSFONT_LZ11_H
#define SYSFONT_LZ11_H

#include <stddef.h>
#include <stdint.h>

/* Decompressed size from the header, or 0 if `in` is not LZ11. */
size_t lz11_size(const uint8_t *in, size_t in_len);

/* Inflate `in` into `out` (lz11_size() bytes). Returns 0, or -1 on a malformed stream. */
int lz11_decompress(const uint8_t *in, size_t in_len, uint8_t *out, size_t out_len);

/* Worst-case packed size for `len` input bytes: what compress() may need in `out`. */
size_t lz11_bound(size_t len);

/* Pack `in` into `out` (lz11_bound() bytes). Returns the packed size, or 0 on failure. */
size_t lz11_compress(const uint8_t *in, size_t len, uint8_t *out, size_t out_cap);

#endif
