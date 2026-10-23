/*
 * The few file operations the install engine needs, on plain stdio + POSIX directory calls:
 * libctru's sdmc: device provides them on the console, the host has them natively, so the
 * engine runs (and is tested) on both. Paths are full: "sdmc:/luma/..." or "/tmp/sd/luma/...".
 *
 * Every call that changes the card spends one unit of `fs_budget` when it is >= 0 and fails
 * once it is spent: the host tests cut the power at every step that way.
 */
#ifndef ENGINE_FSUTIL_H
#define ENGINE_FSUTIL_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

extern long fs_budget;

bool fs_exists(const char *path);
bool fs_is_dir(const char *path);
/* Size of a file, or -1. */
long fs_size(const char *path);

/* mkdir -p of the directory part of `path` (everything before the last '/'). */
int fs_make_parents(const char *path);
/* Write `data` to `path` (parents made), flushed to the card. */
int fs_write(const char *path, const void *data, size_t len);
/* sha256 of a file's contents; 0 or -1. */
int fs_sha256(const char *path, uint8_t digest[32]);
/* Write, read back, check the sha256. */
int fs_write_verified(const char *path, const void *data, size_t len, const uint8_t sha[32]);
/* Write next to `path` as <path>.3dsua-tmp, check, rename that to <path>.3dsua-ok, then
 * replace `path` with it. A cut leaves the old file, or a whole new one as .3dsua-ok for
 * fs_finish_replace(); a .3dsua-tmp is never more than a part and can go. */
#define FS_TMP_SUFFIX ".3dsua-tmp"
#define FS_OK_SUFFIX ".3dsua-ok"
int fs_replace_verified(const char *path, const void *data, size_t len, const uint8_t sha[32]);
int fs_finish_replace(const char *path);
int fs_copy(const char *from, const char *to);

/* The sdmc: device cannot rename onto an existing name; neither does this. */
int fs_rename(const char *from, const char *to);
int fs_remove(const char *path);
/* rm -rf; 0 when `path` is gone afterwards (or never was). */
int fs_remove_tree(const char *path);
/* Remove `dir` and its parents up to (not including) `stop` while they are empty. */
void fs_prune_empty(const char *dir, const char *stop);

/* Calls `fn` for every regular file under `dir`, with its path relative to `dir`. */
typedef int (*FsWalkFn)(const char *rel, void *ctx);
int fs_walk(const char *dir, FsWalkFn fn, void *ctx);

/* Calls `fn` for every entry name directly in `dir`. */
typedef void (*FsListFn)(const char *name, void *ctx);
int fs_list(const char *dir, FsListFn fn, void *ctx);

#endif
