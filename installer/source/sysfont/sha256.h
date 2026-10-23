/* SHA-256 (FIPS 180-4). Small and dependency-free, for checking the fonts the installer reads and builds. */
#ifndef SYSFONT_SHA256_H
#define SYSFONT_SHA256_H

#include <stddef.h>
#include <stdint.h>

typedef struct {
    uint32_t state[8];
    uint64_t bits;
    uint8_t block[64];
    size_t fill;
} Sha256;

void sha256_init(Sha256 *s);
void sha256_update(Sha256 *s, const void *data, size_t len);
void sha256_final(Sha256 *s, uint8_t digest[32]);
void sha256(const void *data, size_t len, uint8_t digest[32]);

#endif
