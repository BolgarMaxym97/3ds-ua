/*
 * Host test of installer/source/payload: parse data/manifest.txt and restore every blob,
 * whole files and deltas alike, checking each against its sha256 - the work the app does
 * on the console, over the whole payload.
 *
 *     payload_test <dist_installer/romfs/data>
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "../source/payload/manifest.h"
#include "../source/payload/payload.h"

static int failures;

static void expect(int ok, const char *what)
{
    printf("%s  %s\n", ok ? "ok  " : "FAIL", what);
    failures += !ok;
}

int main(int argc, char **argv)
{
    if (argc != 2) {
        fprintf(stderr, "usage: %s <data dir>\n", argv[0]);
        return 2;
    }
    char path[512];
    snprintf(path, sizeof(path), "%s/manifest.txt", argv[1]);
    uint8_t *text;
    size_t len;
    if (payload_read_file(path, &text, &len)) {
        fprintf(stderr, "cannot read %s\n", path);
        return 2;
    }

    Manifest m;
    int line = manifest_parse(&m, (const char *)text, len);
    char msg[256];
    snprintf(msg, sizeof(msg), "manifest parses (failing line %d)", line);
    expect(line == 0, msg);
    if (line)
        return 1;
    size_t deltas = 0;
    for (size_t i = 0; i < m.blob_count; i++)
        deltas += m.blobs[i].base >= 0;
    snprintf(msg, sizeof(msg), "version %s, %zu blobs (%zu deltas), %zu title requirements, NS v%u", m.version,
             m.blob_count, deltas, m.need_count, m.ns_remaster);
    expect(m.blob_count > 0 && m.need_count > 0 && m.ns_remaster == 23, msg);

    static const char *slots[] = {"ru", "en"}, *models[] = {"old3ds", "new3ds"}, *glyphs[] = {"default", "real"};
    for (int s = 0; s < SLOT_COUNT; s++)
        for (int d = 0; d < MODEL_COUNT; d++)
            for (int g = 0; g < GLYPHS_COUNT; g++) {
                const FileSet *set = &m.sets[s][d][g];
                int locales = 0;
                for (size_t i = 0; i < set->count; i++)
                    locales += strstr(set->entries[i].path, "/locale.txt") != NULL;
                snprintf(msg, sizeof(msg), "set %s %s %s: %zu files, %d locale.txt", slots[s], models[d], glyphs[g],
                         set->count, locales);
                expect(set->count > 200 && locales >= 30, msg);
            }

    clock_t start = clock();
    size_t restored = 0, bytes = 0;
    for (size_t i = 0; i < m.blob_count; i++) {
        uint8_t *data;
        PayloadStatus status = payload_restore(&m, argv[1], (int)i, &data);
        if (status != PAYLOAD_OK) {
            printf("      blob %zu (%s): %s\n", i, m.blobs[i].name, payload_error(status));
            continue;
        }
        restored++;
        bytes += m.blobs[i].size;
        free(data);
    }
    snprintf(msg, sizeof(msg), "every blob restores to its sha256 (%zu/%zu, %.1f MB, %.2f s)", restored, m.blob_count,
             bytes / 1e6, (double)(clock() - start) / CLOCKS_PER_SEC);
    expect(restored == m.blob_count, msg);

    /* a delta whose base was tampered with must fail its hash */
    size_t probe = 0;
    while (probe < m.blob_count && m.blobs[probe].base < 0)
        probe++;
    if (probe < m.blob_count) {
        Manifest copy = m;
        Blob *blobs = malloc(m.blob_count * sizeof(Blob));
        memcpy(blobs, m.blobs, m.blob_count * sizeof(Blob));
        copy.blobs = blobs;
        blobs[probe].sha[0] ^= 1;
        uint8_t *data = NULL;
        expect(payload_restore(&copy, argv[1], (int)probe, &data) == PAYLOAD_E_HASH, "a wrong sha is caught");
        free(blobs);
    }

    manifest_free(&m);
    free(text);
    printf("%s\n", failures ? "FAILED" : "all passed");
    return failures ? 1 : 0;
}
