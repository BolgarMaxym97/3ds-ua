#include "fsutil.h"

#include <dirent.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#include "../sysfont/sha256.h"

#ifdef __3DS__
#include <3ds.h>
#endif

#define CHUNK 0x10000
#define NAMES_MAX 256 /* the largest folder of the mod has 68 entries */

long fs_budget = -1;

static bool spend(void)
{
    if (fs_budget < 0)
        return true;
    if (fs_budget == 0)
        return false;
    fs_budget--;
    return true;
}

bool fs_exists(const char *path)
{
    struct stat st;
    return stat(path, &st) == 0;
}

bool fs_is_dir(const char *path)
{
    struct stat st;
    return stat(path, &st) == 0 && S_ISDIR(st.st_mode);
}

long fs_size(const char *path)
{
    struct stat st;
    if (stat(path, &st) || !S_ISREG(st.st_mode))
        return -1;
    return (long)st.st_size;
}

/* The directory fs_make_parents() last saw exist: files come folder by folder, so most
 * calls skip the stat. fs_remove_tree() forgets it. */
static char known_dir[256];

int fs_make_parents(const char *path)
{
    char buf[256];
    size_t len = strlen(path);
    if (len >= sizeof(buf))
        return -1;
    memcpy(buf, path, len + 1);
    char *slash = strrchr(buf, '/');
    if (!slash)
        return 0;
    *slash = 0;
    if (!*buf || !strcmp(buf, known_dir))
        return 0;
    if (fs_is_dir(buf)) {
        strcpy(known_dir, buf);
        return 0;
    }
    if (fs_make_parents(buf))
        return -1;
    /* "sdmc:" itself is not a directory one can make */
    if (buf[strlen(buf) - 1] == ':')
        return 0;
    if (!spend())
        return -1;
    if (mkdir(buf, 0777) && errno != EEXIST)
        return -1;
    strcpy(known_dir, buf);
    return 0;
}

#ifdef __3DS__
/*
 * On the console a file is created at its full size first, so the card's FAT chain is laid
 * out once instead of growing with the write; then one write, unflushed (the close commits
 * it). On an Old 3DS the files stage was spent mostly writing (81 of 150 s, 2026-10-22).
 * 1 = not an sdmc: path, fall back to stdio.
 */
static FS_Archive sd_archive;
static bool sd_archive_open;

static bool ctr_archive(const char *path)
{
    if (strncmp(path, "sdmc:/", 6))
        return false;
    if (!sd_archive_open && R_SUCCEEDED(FSUSER_OpenArchive(&sd_archive, ARCHIVE_SDMC, fsMakePath(PATH_EMPTY, ""))))
        sd_archive_open = true;
    return sd_archive_open;
}

/* Every FS call costs about 20 ms on an Old 3DS whatever it does: a file of the mod took
 * 110 ms to write regardless of size (trace, 2026-10-22), so each call saved counts. */
static int ctr_write(const char *path, const void *data, size_t len)
{
    if (!ctr_archive(path))
        return 1;
    FS_Path at = fsMakePath(PATH_ASCII, path + 5);
    /* staged files are new: delete only when the name turns out to be taken ("wb" truncates) */
    if (R_FAILED(FSUSER_CreateFile(sd_archive, at, 0, len)) &&
        (R_FAILED(FSUSER_DeleteFile(sd_archive, at)) || R_FAILED(FSUSER_CreateFile(sd_archive, at, 0, len))))
        return -1;
    Handle file;
    if (R_FAILED(FSUSER_OpenFile(&file, sd_archive, at, FS_OPEN_WRITE, 0)))
        return -1;
    u32 written = 0;
    Result rc = len ? FSFILE_Write(file, &written, 0, data, len, 0) : 0;
    rc |= FSFILE_Close(file);
    return R_SUCCEEDED(rc) && written == len ? 0 : -1;
}
#endif

int fs_write(const char *path, const void *data, size_t len)
{
    if (fs_make_parents(path) || !spend())
        return -1;
#ifdef __3DS__
    int fast = ctr_write(path, data, len);
    if (fast <= 0)
        return fast;
#endif
    FILE *f = fopen(path, "wb");
    if (!f)
        return -1;
    setvbuf(f, NULL, _IONBF, 0); /* one write straight to the FS, no copy through stdio */
    int ok = fwrite(data, 1, len, f) == len && fflush(f) == 0;
    fsync(fileno(f)); /* FSFILE_Flush on the console; best effort */
    ok &= fclose(f) == 0;
    return ok ? 0 : -1;
}

int fs_sha256(const char *path, uint8_t digest[32])
{
    FILE *f = fopen(path, "rb");
    if (!f)
        return -1;
    setvbuf(f, NULL, _IONBF, 0);
    uint8_t *buf = malloc(CHUNK);
    if (!buf) {
        fclose(f);
        return -1;
    }
    Sha256 s;
    sha256_init(&s);
    size_t got;
    while ((got = fread(buf, 1, CHUNK, f)) > 0)
        sha256_update(&s, buf, got);
    int ok = !ferror(f);
    fclose(f);
    free(buf);
    sha256_final(&s, digest);
    return ok ? 0 : -1;
}

int fs_write_verified(const char *path, const void *data, size_t len, const uint8_t sha[32])
{
    uint8_t got[32];
    if (fs_write(path, data, len) || fs_sha256(path, got) || memcmp(got, sha, 32))
        return -1;
    return 0;
}

int fs_replace_verified(const char *path, const void *data, size_t len, const uint8_t sha[32])
{
    char tmp[256], ok[256];
    if (snprintf(tmp, sizeof(tmp), "%s" FS_TMP_SUFFIX, path) >= (int)sizeof(tmp) ||
        snprintf(ok, sizeof(ok), "%s" FS_OK_SUFFIX, path) >= (int)sizeof(ok))
        return -1;
    if ((fs_exists(tmp) && fs_remove(tmp)) || (fs_exists(ok) && fs_remove(ok)))
        return -1;
    /* .3dsua-ok marks a copy that is whole and checked: fs_finish_replace() can complete it */
    if (fs_write_verified(tmp, data, len, sha) || fs_rename(tmp, ok))
        return -1;
    return fs_finish_replace(path);
}

int fs_finish_replace(const char *path)
{
    char ok[256];
    if (snprintf(ok, sizeof(ok), "%s" FS_OK_SUFFIX, path) >= (int)sizeof(ok))
        return -1;
    if (fs_exists(path) && fs_remove(path))
        return -1;
    return fs_rename(ok, path);
}

int fs_copy(const char *from, const char *to)
{
    FILE *in = fopen(from, "rb");
    if (!in)
        return -1;
    int status = -1;
    FILE *out = NULL;
    uint8_t *buf = malloc(CHUNK);
    if (!buf || fs_make_parents(to) || !spend() || !(out = fopen(to, "wb")))
        goto done;
    size_t got;
    while ((got = fread(buf, 1, CHUNK, in)) > 0)
        if (fwrite(buf, 1, got, out) != got)
            goto done;
    if (!ferror(in) && fflush(out) == 0)
        status = 0;
    fsync(fileno(out));
done:
    if (out && fclose(out))
        status = -1;
    fclose(in);
    free(buf);
    return status;
}

int fs_rename(const char *from, const char *to)
{
    known_dir[0] = 0;
    if (fs_exists(to) || !spend())
        return -1;
    return rename(from, to) ? -1 : 0;
}

int fs_remove(const char *path)
{
    if (!spend())
        return -1;
    return remove(path) ? -1 : 0;
}

typedef struct {
    char names[NAMES_MAX][64];
    signed char is_dir[NAMES_MAX]; /* from readdir's d_type: 1, 0, or -1 when it does not say */
    int count;
    bool overflow;
} Names;

/* Every stat() is a round trip to the FS module on the console; readdir already knows. */
static int list_names(const char *dir, Names *n)
{
    DIR *d = opendir(dir);
    if (!d)
        return -1;
    struct dirent *e;
    while ((e = readdir(d)) != NULL) {
        if (!strcmp(e->d_name, ".") || !strcmp(e->d_name, ".."))
            continue;
        if (n->count == NAMES_MAX || strlen(e->d_name) >= 64) {
            n->overflow = true;
            continue;
        }
        n->is_dir[n->count] = e->d_type == DT_DIR ? 1 : e->d_type == DT_REG ? 0 : -1;
        strcpy(n->names[n->count++], e->d_name);
    }
    closedir(d);
    return 0;
}

int fs_remove_tree(const char *path)
{
    known_dir[0] = 0;
    if (!fs_exists(path))
        return 0;
    if (!fs_is_dir(path))
        return fs_remove(path);
#ifdef __3DS__
    /* one call for the whole tree instead of one per file */
    if (ctr_archive(path) && spend() &&
        R_SUCCEEDED(FSUSER_DeleteDirectoryRecursively(sd_archive, fsMakePath(PATH_ASCII, path + 5))))
        return 0;
#endif
    /* in rounds of up to NAMES_MAX entries: no directory handle stays open while deleting */
    for (;;) {
        Names *n = calloc(1, sizeof(Names));
        if (!n || list_names(path, n)) {
            free(n);
            return -1;
        }
        int count = n->count;
        for (int i = 0; i < count; i++) {
            char child[256];
            if (snprintf(child, sizeof(child), "%s/%s", path, n->names[i]) >= (int)sizeof(child) ||
                fs_remove_tree(child)) {
                free(n);
                return -1;
            }
        }
        bool more = n->overflow;
        free(n);
        if (!more)
            break;
        if (!count)
            return -1;
    }
    if (!spend())
        return -1;
    return rmdir(path) ? -1 : 0;
}

static void count_entry(const char *name, void *ctx)
{
    (void)name;
    (*(int *)ctx)++;
}

void fs_prune_empty(const char *dir, const char *stop)
{
    known_dir[0] = 0;
    char buf[256];
    size_t stop_len = strlen(stop);
    if (strlen(dir) >= sizeof(buf))
        return;
    strcpy(buf, dir);
    while (strlen(buf) > stop_len && !strncmp(buf, stop, stop_len)) {
        int entries = 0;
        if (fs_list(buf, count_entry, &entries) || entries || !spend() || rmdir(buf))
            return;
        char *slash = strrchr(buf, '/');
        if (!slash)
            return;
        *slash = 0;
    }
}

int fs_list(const char *dir, FsListFn fn, void *ctx)
{
    DIR *d = opendir(dir);
    if (!d)
        return -1;
    struct dirent *e;
    while ((e = readdir(d)) != NULL) {
        if (!strcmp(e->d_name, ".") || !strcmp(e->d_name, ".."))
            continue;
        fn(e->d_name, ctx);
    }
    closedir(d);
    return 0;
}

static int walk(const char *root, const char *rel, FsWalkFn fn, void *ctx, int depth)
{
    char dir[256];
    if (snprintf(dir, sizeof(dir), "%s%s%s", root, *rel ? "/" : "", rel) >= (int)sizeof(dir) || depth > 8)
        return -1;
    Names *n = calloc(1, sizeof(Names));
    if (!n || list_names(dir, n) || n->overflow) {
        /* refuse rather than skip part of a folder */
        free(n);
        return -1;
    }
    int status = 0;
    for (int i = 0; i < n->count && !status; i++) {
        char child_rel[256], child[256];
        if (snprintf(child_rel, sizeof(child_rel), "%s%s%s", rel, *rel ? "/" : "", n->names[i]) >= (int)sizeof(child_rel) ||
            snprintf(child, sizeof(child), "%s/%s", root, child_rel) >= (int)sizeof(child)) {
            status = -1;
            break;
        }
        if (n->is_dir[i] == 1 || (n->is_dir[i] < 0 && fs_is_dir(child)))
            status = walk(root, child_rel, fn, ctx, depth + 1);
        else
            status = fn(child_rel, ctx);
    }
    free(n);
    return status;
}

int fs_walk(const char *dir, FsWalkFn fn, void *ctx)
{
    return walk(dir, "", fn, ctx, 0);
}
