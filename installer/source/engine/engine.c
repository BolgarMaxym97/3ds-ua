#include "engine.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "../payload/payload.h"
#include "../sysfont/sha256.h"
#include "fsutil.h"
#include "lumacfg.h"

#define TITLES "luma/titles/"
#define FOLDER_LEN 28 /* "luma/titles/" + 16 hex digits */
#define HOME_MENU_FOLDER TITLES "0004003000009802"
/* A file only this mod puts there, in every build: a copy installed before the app (by the
 * Universal-Updater scripts or by hand) has it but no installed.txt. */
#define MOD_MARK HOME_MENU_FOLDER "/banner_22800.bin"
#define CONFIG_FILE "luma/config.ini"
#define NEW_SUFFIX ".3dsua-new"
#define OLD_SUFFIX ".3dsua-old"
#define DEL_SUFFIX ".3dsua-del"
#define FULL_SUFFIX ".3dsua-full"
#define FOLDERS_MAX 96
#define PATH_CAP 256

typedef struct {
    char path[FOLDER_LEN + 1];
    bool excluded;  /* in the chosen set, but the title is another build */
    bool unchanged; /* already exactly the chosen set */
} Folder;

typedef struct {
    Job *job;
    const Manifest *m;
    const FileSet *set;
    Installed prev;
    bool has_prev;
    bool old_mod;
    Installed next;
    Folder folders[FOLDERS_MAX];
    int nfolders;
    char font_path[96];
    /* luma/config.ini as read, and where its two flags are */
    bool font_planned;  /* the font should go on: the text is staged with the real letters */
    char *config;
    size_t config_len;
    LumaConfig flags;
    bool config_ok;
} Ctx;

static EngineStatus fail(Ctx *c, EngineStatus status, const char *what, const char *path)
{
    snprintf(c->job->error, sizeof(c->job->error), "%s%s%s", what, path ? ": " : "", path ? path : "");
    return status;
}

/* Paths are bounded by the manifest's 96-byte field, far below PATH_CAP; were one ever
 * longer, it becomes "" and every operation on it fails rather than hitting a cut-off name. */
static void sd(const Ctx *c, const char *rel, char *out)
{
    if (snprintf(out, PATH_CAP, "%s/%s", c->job->sd_root, rel) >= PATH_CAP)
        out[0] = 0;
}

static bool in_folder(const char *path, const char *folder)
{
    return !strncmp(path, folder, FOLDER_LEN) && path[FOLDER_LEN] == '/';
}

/* "luma/titles/<TID>" of a path, or false. */
static bool folder_of(const char *path, char out[FOLDER_LEN + 1])
{
    if (strncmp(path, TITLES, strlen(TITLES)) || strlen(path) <= FOLDER_LEN || path[FOLDER_LEN] != '/')
        return false;
    memcpy(out, path, FOLDER_LEN);
    out[FOLDER_LEN] = 0;
    return true;
}

static bool is_font_file(const Ctx *c, const char *path)
{
    if (!strcmp(path, c->font_path))
        return true;
    for (size_t i = 0; i < c->m->font_set.count; i++)
        if (!strcmp(c->m->font_set.entries[i].path, path))
            return true;
    return false;
}

/* The path is a file of some build in this app. */
static bool in_manifest(const Ctx *c, const char *path)
{
    for (int s = 0; s < SLOT_COUNT; s++)
        for (int mo = 0; mo < MODEL_COUNT; mo++)
            for (int g = 0; g < GLYPHS_COUNT; g++) {
                const FileSet *set = &c->m->sets[s][mo][g];
                for (size_t i = 0; i < set->count; i++)
                    if (!strcmp(set->entries[i].path, path))
                        return true;
            }
    return is_font_file(c, path);
}

/* A file on the card that the mod put there - this install, an earlier one, or an older
 * copy installed without the app. `path` is where it belongs, `full` where it is now. */
static bool is_ours_at(const Ctx *c, const char *path, const char *full)
{
    const StateFile *sf = c->has_prev ? installed_find(&c->prev, path) : NULL;
    if (sf && fs_size(full) == (long)sf->size)
        return true;
    if (c->old_mod && in_manifest(c, path))
        return true;
    uint8_t sha[32];
    if (fs_sha256(full, sha))
        return false;
    return manifest_find_blob(c->m, sha) >= 0 || (sf && !memcmp(sha, sf->sha, 32));
}

static bool is_ours(const Ctx *c, const char *path)
{
    char full[PATH_CAP];
    sd(c, path, full);
    return is_ours_at(c, path, full);
}

static void add_folder(Ctx *c, const char *path)
{
    char folder[FOLDER_LEN + 1];
    if (!folder_of(path, folder) || is_font_file(c, path))
        return;
    for (int i = 0; i < c->nfolders; i++)
        if (!strcmp(c->folders[i].path, folder))
            return;
    if (c->nfolders < FOLDERS_MAX)
        strcpy(c->folders[c->nfolders++].path, folder);
}

/* Every folder any build of the mod uses, or the last install wrote; the HOME Menu's last. */
static void collect_folders(Ctx *c)
{
    for (int s = 0; s < SLOT_COUNT; s++)
        for (int mo = 0; mo < MODEL_COUNT; mo++)
            for (int g = 0; g < GLYPHS_COUNT; g++) {
                const FileSet *set = &c->m->sets[s][mo][g];
                for (size_t i = 0; i < set->count; i++)
                    add_folder(c, set->entries[i].path);
            }
    for (size_t i = 0; c->has_prev && i < c->prev.count; i++)
        add_folder(c, c->prev.files[i].path);
    for (int i = 0; i < c->nfolders - 1; i++)
        if (!strcmp(c->folders[i].path, HOME_MENU_FOLDER)) {
            Folder home = c->folders[i];
            memmove(&c->folders[i], &c->folders[i + 1], (size_t)(c->nfolders - 1 - i) * sizeof(Folder));
            c->folders[c->nfolders - 1] = home;
            break;
        }
}

static bool excluded(const Ctx *c, const char *folder)
{
    uint64_t tid = strtoull(folder + strlen(TITLES), NULL, 16);
    for (size_t i = 0; i < c->m->need_count; i++) {
        const Need *n = &c->m->needs[i];
        if (n->model == c->job->model && n->folder == tid)
            return !c->job->need_met(n, c->job->ctx);
    }
    return false;
}

static int write_text_file(const Ctx *c, const char *rel, const char *text, size_t len)
{
    char full[PATH_CAP];
    uint8_t sha[32];
    sd(c, rel, full);
    sha256(text, len, sha);
    return fs_replace_verified(full, text, len, sha);
}

static void load_config(Ctx *c)
{
    char full[PATH_CAP];
    sd(c, CONFIG_FILE, full);
    uint8_t *text;
    if (payload_read_file(full, &text, &c->config_len))
        return;
    c->config = (char *)text;
    c->config_ok = lumacfg_parse(&c->flags, c->config, c->config_len) == 0;
}

static int load_state(Ctx *c)
{
    c->has_prev = engine_load_installed(c->job->sd_root, &c->prev) == 0;
    char full[PATH_CAP];
    sd(c, MOD_MARK, full);
    c->old_mod = !c->has_prev && fs_exists(full);
    const char *fp = c->m->font_path;
    snprintf(c->font_path, sizeof(c->font_path), "%s", *fp == '/' ? fp + 1 : fp);
    collect_folders(c);
    load_config(c);
    return 0;
}

static int write_pending(Ctx *c)
{
    Pending p = {c->job->op, c->job->slot, c->job->glyphs};
    char text[128];
    size_t len = pending_format(&p, text, sizeof(text));
    return write_text_file(c, PENDING_FILE, text, len);
}

/* ---------------------------------------------------------------- walking a folder */

typedef struct {
    Ctx *c;
    const char *base;   /* card-relative folder the walk started in */
    int files;
    int kept;
    int status;
} Walk;

static void join(char *out, const char *base, const char *rel)
{
    if (snprintf(out, PATH_CAP, "%s/%s", base, rel) >= PATH_CAP)
        out[0] = 0;
}

static void suffixed(char *out, const char *path, const char *suffix)
{
    if (snprintf(out, PATH_CAP, "%s%s", path, suffix) >= PATH_CAP)
        out[0] = 0;
}

/* Finder's ._* and .DS_Store: nobody's data, dropped wherever they turn up. */
static bool is_junk(const char *rel)
{
    const char *name = strrchr(rel, '/');
    return (name ? name + 1 : rel)[0] == '.';
}

static int backup_foreign(const char *rel, void *ctx)
{
    Walk *w = ctx;
    char path[PATH_CAP], from[PATH_CAP], bpath[PATH_CAP], to[PATH_CAP];
    join(path, w->base, rel);
    if (is_junk(rel) || is_ours(w->c, path))
        return 0;
    sd(w->c, path, from);
    join(bpath, BACKUP_DIR, path);
    sd(w->c, bpath, to);
    if (fs_exists(to)) /* the first copy is the original */
        return 0;
    return fs_copy(from, to);
}

static int count_file(const char *rel, void *ctx)
{
    ((Walk *)ctx)->files += !is_junk(rel);
    return 0;
}

/* What clearing a folder leaves: for an install, whatever is not the mod's; for a removal,
 * whatever the last install did not write, or changed size since (and, with no
 * installed.txt - a copy installed without the app - whatever is not at a path of the mod). */
static bool keep(Walk *w, const char *path, const char *full)
{
    Ctx *c = w->c;
    if (is_junk(path))
        return false;
    if (c->job->op == OP_INSTALL)
        return !is_ours_at(c, path, full);
    if (!c->has_prev)
        return !in_manifest(c, path);
    const StateFile *sf = installed_find(&c->prev, path);
    if (!sf)
        return true;
    /* as an install trusts it (is_ours): the recorded size. Reading every file back for its
     * sha made a removal 29 MB of reads on a card where each call costs ~20 ms. */
    if (fs_size(full) != (long)sf->size) {
        w->kept++;
        return true;
    }
    return false;
}

typedef struct {
    Walk w;
    const char *from;   /* the full path of the folder moved aside */
    const char *to;     /* the full path of the folder */
} Keepers;

static int move_keeper(const char *rel, void *ctx)
{
    Keepers *k = ctx;
    char path[PATH_CAP], from[PATH_CAP], to[PATH_CAP];
    join(path, k->w.base, rel);
    join(from, k->from, rel);
    join(to, k->to, rel);
    if (!keep(&k->w, path, from))
        return 0;
    return fs_make_parents(to) || fs_rename(from, to);
}

/*
 * Take the mod's files out of a folder without a title ever seeing part of them: the folder
 * is renamed aside in one step (the title is stock from then on), what has to stay is moved
 * back, the rest deleted. An interrupted clear leaves <TID>.3dsua-del, which the repeated
 * operation finishes first.
 */
static EngineStatus clear_folder(Ctx *c, const char *folder, int *kept)
{
    char full[PATH_CAP], aside[PATH_CAP], stop[PATH_CAP];
    sd(c, folder, full);
    suffixed(aside, full, DEL_SUFFIX);
    if (!fs_is_dir(aside)) {
        if (!fs_is_dir(full))
            return ENGINE_OK;
        if (fs_rename(full, aside))
            return fail(c, ENGINE_E_WRITE, "cannot clear", folder);
    }
    Keepers k = {.w = {.c = c, .base = folder}, .from = aside, .to = full};
    if (fs_walk(aside, move_keeper, &k) || fs_remove_tree(aside))
        return fail(c, ENGINE_E_WRITE, "cannot clear", folder);
    if (kept)
        *kept += k.w.kept;
    sd(c, "luma/titles", stop);
    fs_prune_empty(full, stop);
    return ENGINE_OK;
}

/* ---------------------------------------------------------------- install */

static int set_count_in(const FileSet *set, const char *folder)
{
    int n = 0;
    for (size_t i = 0; i < set->count; i++)
        n += in_folder(set->entries[i].path, folder);
    return n;
}

static bool folder_unchanged(Ctx *c, const char *folder, int wanted)
{
    if (!c->has_prev)
        return false;
    for (size_t i = 0; i < c->set->count; i++) {
        const Entry *e = &c->set->entries[i];
        if (!in_folder(e->path, folder))
            continue;
        const Blob *b = &c->m->blobs[e->blob];
        const StateFile *sf = installed_find(&c->prev, e->path);
        char full[PATH_CAP];
        sd(c, e->path, full);
        if (!sf || memcmp(sf->sha, b->sha, 32) || fs_size(full) != (long)b->size)
            return false;
    }
    char full[PATH_CAP];
    sd(c, folder, full);
    Walk w = {.c = c, .base = folder};
    return fs_walk(full, count_file, &w) == 0 && w.files == wanted;
}

static EngineStatus record(Ctx *c, const uint8_t sha[32], uint32_t size, const char *path)
{
    return installed_add(&c->next, sha, size, path) ? fail(c, ENGINE_E_MEMORY, "out of memory", NULL) : ENGINE_OK;
}

/* `replace`: swap in over an existing file, read back and checked. Otherwise the file goes
 * into a staging folder: payload_restore() has already checked the bytes, and the folder
 * only counts once the swap renames it in, so the read-back is skipped (it doubled the
 * time of the files stage on the console). */
static uint64_t now(const Ctx *c)
{
    return c->job->clock_ms ? c->job->clock_ms() : 0;
}

static EngineStatus restore_to(Ctx *c, const Entry *e, const char *full, bool replace)
{
    uint8_t *data;
    uint64_t t0 = now(c);
    PayloadStatus ps = payload_restore(c->m, c->job->data_root, e->blob, &data);
    uint64_t t1 = now(c);
    c->job->restore_ms += t1 - t0;
    if (ps != PAYLOAD_OK)
        return fail(c, ps == PAYLOAD_E_MEMORY ? ENGINE_E_MEMORY : ENGINE_E_PAYLOAD, payload_error(ps), e->path);
    const Blob *b = &c->m->blobs[e->blob];
    int status = replace ? fs_replace_verified(full, data, b->size, b->sha) : fs_write(full, data, b->size);
    free(data);
    uint64_t t2 = now(c);
    c->job->write_ms += t2 - t1;
    if (c->job->trace)
        c->job->trace(c->job->ctx, e->path, b->size, t1 - t0, t2 - t1);
    return status ? fail(c, ENGINE_E_WRITE, "write failed", e->path) : ENGINE_OK;
}

static EngineStatus backup_all(Ctx *c)
{
    char full[PATH_CAP];
    for (int i = 0; i < c->nfolders; i++) {
        sd(c, c->folders[i].path, full);
        if (!fs_is_dir(full))
            continue;
        Walk w = {.c = c, .base = c->folders[i].path};
        if (fs_walk(full, backup_foreign, &w))
            return fail(c, ENGINE_E_WRITE, "backup failed", c->folders[i].path);
    }
    for (size_t i = 0; i < c->m->font_set.count; i++) {
        const char *path = c->m->font_set.entries[i].path;
        char dir[PATH_CAP];
        snprintf(dir, sizeof(dir), "%s", path);
        char *slash = strrchr(dir, '/');
        *slash = 0;
        sd(c, path, full);
        Walk w = {.c = c, .base = dir};
        if (fs_exists(full) && backup_foreign(slash + 1, &w))
            return fail(c, ENGINE_E_WRITE, "backup failed", path);
    }
    return ENGINE_OK;
}

/* The NS patch files go after the font, the patch itself (luma/sysmodules) last: each of
 * the three is inert without the next. */
static int font_set_order(const Ctx *c, int k)
{
    const FileSet *fs = &c->m->font_set;
    int n = 0;
    for (size_t i = 0; i < fs->count; i++)
        if (!strstr(fs->entries[i].path, "sysmodules") && n++ == k)
            return (int)i;
    for (size_t i = 0; i < fs->count; i++)
        if (strstr(fs->entries[i].path, "sysmodules") && n++ == k)
            return (int)i;
    return -1;
}

static void remove_font(Ctx *c)
{
    char full[PATH_CAP];
    for (int k = (int)c->m->font_set.count - 1; k >= 0; k--) {
        const char *path = c->m->font_set.entries[font_set_order(c, k)].path;
        sd(c, path, full);
        if (fs_exists(full) && is_ours(c, path))
            fs_remove(full);
    }
    sd(c, c->font_path, full);
    if (fs_exists(full) && c->has_prev && installed_find(&c->prev, c->font_path))
        fs_remove(full);
    char dir[PATH_CAP], stop[PATH_CAP];
    sd(c, TITLES "0004013000008002", dir);
    sd(c, "luma/titles", stop);
    fs_prune_empty(dir, stop);
    sd(c, c->font_path, dir);
    *strrchr(dir, '/') = 0;
    sd(c, STATE_DIR, stop);
    fs_prune_empty(dir, stop);
}

/* Both Luma flags will be on after this run: the font may go on. */
static bool flags_will_be_on(const Ctx *c)
{
    return c->config_ok || (c->job->luma_game_on && c->job->luma_external_on);
}

static EngineStatus install_font(Ctx *c)
{
    Job *job = c->job;
    job->font = false;
    if (!job->want_font || !flags_will_be_on(c)) {
        remove_font(c);
        return ENGINE_OK;
    }

    char full[PATH_CAP];
    sd(c, c->font_path, full);
    /* the font already on the card stays only if it is the one this app builds: a fix to
     * a glyph can keep the file's size exactly (є, 2026-10-22) */
    static const uint8_t ANY[32];
    const StateFile *sf = c->has_prev && c->prev.font ? installed_find(&c->prev, c->font_path) : NULL;
    bool expected = !memcmp(job->font_sha, ANY, 32) || (sf && !memcmp(sf->sha, job->font_sha, 32));
    if (sf && expected && fs_size(full) == (long)sf->size) {
        if (record(c, sf->sha, sf->size, c->font_path))
            return ENGINE_E_MEMORY;
    } else {
        size_t len = 0;
        uint8_t *font = job->build_font(job->ctx, &len);
        if (!font) {
            remove_font(c);
            return ENGINE_OK;
        }
        uint8_t sha[32];
        sha256(font, len, sha);
        int status = fs_replace_verified(full, font, len, sha);
        free(font);
        if (status)
            return fail(c, ENGINE_E_WRITE, "write failed", c->font_path);
        if (record(c, sha, (uint32_t)len, c->font_path))
            return ENGINE_E_MEMORY;
    }

    for (size_t k = 0; k < c->m->font_set.count; k++) {
        const Entry *e = &c->m->font_set.entries[font_set_order(c, (int)k)];
        const Blob *b = &c->m->blobs[e->blob];
        const StateFile *prev = c->has_prev ? installed_find(&c->prev, e->path) : NULL;
        sd(c, e->path, full);
        if (!prev || memcmp(prev->sha, b->sha, 32) || fs_size(full) != (long)b->size) {
            EngineStatus status = restore_to(c, e, full, true);
            if (status)
                return status;
        }
        if (record(c, b->sha, b->size, e->path))
            return ENGINE_E_MEMORY;
    }
    job->font = true;
    return ENGINE_OK;
}

static EngineStatus plan_files(Ctx *c)
{
    Job *job = c->job;
    job->glyphs_set = c->font_planned ? job->glyphs : GLYPHS_DEFAULT;
    c->set = &c->m->sets[job->slot][job->model][job->glyphs_set];
    job->skipped = 0;
    int total = 0;
    for (int i = 0; i < c->nfolders; i++) {
        Folder *f = &c->folders[i];
        int wanted = set_count_in(c->set, f->path);
        f->excluded = wanted && excluded(c, f->path);
        job->skipped += f->excluded;
        f->unchanged = wanted && !f->excluded && folder_unchanged(c, f->path, wanted);
        if (wanted && !f->excluded && !f->unchanged)
            total += wanted;
    }
    job->done = 0;
    job->moved = 0;
    job->total = total;
    return ENGINE_OK;
}

/* The last install wrote this file and it is still that file, under `dir` (the folder or
 * the folder moved aside); size and the recorded sha, as folder_unchanged() trusts them. */
static bool reusable(const Ctx *c, const Entry *e, const char *dir)
{
    if (!c->has_prev)
        return false;
    const StateFile *sf = installed_find(&c->prev, e->path);
    const Blob *b = &c->m->blobs[e->blob];
    char at[PATH_CAP];
    join(at, dir, e->path + FOLDER_LEN + 1);
    return sf && !memcmp(sf->sha, b->sha, 32) && fs_size(at) == (long)b->size;
}

static EngineStatus install_folder(Ctx *c, const Folder *f)
{
    char full[PATH_CAP], staging[PATH_CAP], old[PATH_CAP], aside[PATH_CAP];
    sd(c, f->path, full);
    int wanted = f->excluded ? 0 : set_count_in(c->set, f->path);

    if (!wanted)
        return clear_folder(c, f->path, NULL);

    if (!f->unchanged) {
        char ready[PATH_CAP];
        suffixed(staging, full, NEW_SUFFIX);
        suffixed(ready, full, FULL_SUFFIX);
        suffixed(old, full, OLD_SUFFIX);
        suffixed(aside, full, DEL_SUFFIX);
        if (fs_remove_tree(staging) || fs_remove_tree(ready) || fs_remove_tree(old) || fs_remove_tree(aside))
            return fail(c, ENGINE_E_WRITE, "cannot clear", f->path);

        /* Files the last install wrote and that are still as it wrote them are moved into
         * the staging, not written again (an update rewrites only what changed). Moving them
         * takes them out of the live folder, so then the whole folder goes aside first: the
         * title runs stock until the swap, never on a part of either set. */
        bool reuse = false;
        for (size_t i = 0; i < c->set->count && !reuse; i++)
            reuse = in_folder(c->set->entries[i].path, f->path) && reusable(c, &c->set->entries[i], full);
        if (reuse && fs_rename(full, old))
            return fail(c, ENGINE_E_WRITE, "cannot swap", f->path);

        for (size_t i = 0; i < c->set->count; i++) {
            const Entry *e = &c->set->entries[i];
            if (!in_folder(e->path, f->path))
                continue;
            char dest[PATH_CAP], from[PATH_CAP];
            join(dest, staging, e->path + FOLDER_LEN + 1);
            join(from, old, e->path + FOLDER_LEN + 1);
            if (reuse && reusable(c, e, old)) {
                if (fs_make_parents(dest) || fs_rename(from, dest))
                    return fail(c, ENGINE_E_WRITE, "cannot move", e->path);
                c->job->moved++;
            } else {
                EngineStatus status = restore_to(c, e, dest, false);
                if (status)
                    return status;
            }
            c->job->done++;
        }
        /* staging whole: from here a cut is finished forwards (engine_recover) */
        if (fs_rename(staging, ready) || (fs_is_dir(full) && fs_rename(full, old)) || fs_rename(ready, full) ||
            fs_remove_tree(old))
            return fail(c, ENGINE_E_WRITE, "cannot swap", f->path);
    }
    for (size_t i = 0; i < c->set->count; i++) {
        const Entry *e = &c->set->entries[i];
        if (in_folder(e->path, f->path) && record(c, c->m->blobs[e->blob].sha, c->m->blobs[e->blob].size, e->path))
            return ENGINE_E_MEMORY;
    }
    return ENGINE_OK;
}

static EngineStatus write_config(Ctx *c)
{
    char full[PATH_CAP], bak[PATH_CAP];
    sd(c, CONFIG_FILE, full);
    sd(c, CONFIG_BACKUP, bak);
    if (!fs_exists(bak) && fs_copy(full, bak))
        return fail(c, ENGINE_E_WRITE, "backup failed", CONFIG_FILE);
    if (write_text_file(c, CONFIG_FILE, c->config, c->config_len))
        return fail(c, ENGINE_E_WRITE, "write failed", CONFIG_FILE);
    return ENGINE_OK;
}

static EngineStatus install_luma(Ctx *c)
{
    Job *job = c->job;
    c->next.luma_game = c->has_prev && c->prev.luma_game;
    c->next.luma_external = c->has_prev && c->prev.luma_external;
    /* The backup is made only before an edit of ours, so a flag that is off in it was turned
     * on by the installer - also when a cut came between the edit and installed.txt. */
    char bak[PATH_CAP];
    uint8_t *text;
    size_t len;
    sd(c, CONFIG_BACKUP, bak);
    if (!payload_read_file(bak, &text, &len)) {
        LumaConfig was;
        if (!lumacfg_parse(&was, (char *)text, len)) {
            c->next.luma_game |= *was.game == '0';
            c->next.luma_external |= *was.external == '0';
        }
        free(text);
    }
    if (!c->config_ok) {
        job->luma_manual = !job->luma_game_on;
        return ENGINE_OK;
    }
    bool changed = false;
    if (*c->flags.game == '0') {
        *c->flags.game = '1';
        c->next.luma_game = changed = true;
    }
    if (job->font && *c->flags.external == '0') {
        *c->flags.external = '1';
        c->next.luma_external = changed = true;
    }
    return changed ? write_config(c) : ENGINE_OK;
}

static EngineStatus finish_install(Ctx *c)
{
    Job *job = c->job;
    snprintf(c->next.version, sizeof(c->next.version), "%s", c->m->version);
    c->next.slot = job->slot;
    c->next.model = job->model;
    c->next.glyphs = job->glyphs_set;
    c->next.font = job->font;
    c->next.skipped = job->skipped;
    size_t len;
    char *text = installed_format(&c->next, &len);
    if (!text)
        return fail(c, ENGINE_E_MEMORY, "out of memory", NULL);
    int status = write_text_file(c, INSTALLED_FILE, text, len);
    free(text);
    if (status)
        return fail(c, ENGINE_E_WRITE, "write failed", INSTALLED_FILE);
    char full[PATH_CAP];
    sd(c, PENDING_FILE, full);
    return fs_remove(full) ? fail(c, ENGINE_E_WRITE, "write failed", PENDING_FILE) : ENGINE_OK;
}

static EngineStatus install_files(Ctx *c)
{
    EngineStatus status;
    c->job->stage = STAGE_FILES;
    plan_files(c);
    for (int i = 0; i < c->nfolders; i++)
        if ((status = install_folder(c, &c->folders[i])))
            return status;
    return ENGINE_OK;
}

/*
 * The text goes on first, with the real letters when the font is planned, so the app can
 * build the font meanwhile (FontFn waits for it) and everything is done in one run and one
 * reboot. Should the font then fail to build, the text goes back to the stand-ins before
 * anything is recorded.
 */
static EngineStatus run_install(Ctx *c)
{
    Job *job = c->job;
    EngineStatus status;
    c->font_planned = job->want_font && flags_will_be_on(c);
    job->stage = STAGE_BACKUP;
    if ((status = backup_all(c)))
        return status;
    if ((status = install_files(c)))
        return status;
    job->stage = STAGE_FONT;
    if ((status = install_font(c)))
        return status;
    if (!job->font && job->glyphs_set == GLYPHS_REAL) {
        c->font_planned = false;
        c->next.count = 0;
        if ((status = install_files(c)))
            return status;
    }
    job->stage = STAGE_LUMA;
    if ((status = install_luma(c)))
        return status;
    job->stage = STAGE_FINISH;
    return finish_install(c);
}

/* ---------------------------------------------------------------- remove */

static int restore_backup(const char *rel, void *ctx)
{
    Walk *w = ctx;
    char from[PATH_CAP], to[PATH_CAP], bpath[PATH_CAP];
    join(bpath, BACKUP_DIR, rel);
    sd(w->c, bpath, from);
    sd(w->c, rel, to);
    if (is_junk(rel)) /* an older app backed Finder's files up too: let them go */
        return 0;
    if (fs_exists(to)) /* something new took the place since: keep both, the copy stays */
        return 0;
    return fs_make_parents(to) || fs_rename(from, to);
}

static void list_state(const char *name, void *ctx)
{
    Walk *w = ctx;
    if (strcmp(name, "pending.txt")) {
        char rel[PATH_CAP], full[PATH_CAP];
        join(rel, STATE_DIR, name);
        sd(w->c, rel, full);
        w->status |= fs_remove_tree(full);
    }
}

static EngineStatus run_remove(Ctx *c)
{
    Job *job = c->job;
    char full[PATH_CAP], stop[PATH_CAP];
    sd(c, "luma/titles", stop);

    job->stage = STAGE_FILES;
    job->total = c->nfolders;
    job->done = 0;
    for (int i = 0; i < c->nfolders; i++, job->done++) {
        EngineStatus status = clear_folder(c, c->folders[i].path, &job->kept);
        if (status)
            return status;
    }

    job->stage = STAGE_FONT;
    remove_font(c);

    job->stage = STAGE_BACKUP;
    char backup[PATH_CAP];
    sd(c, BACKUP_DIR, backup);
    if (fs_is_dir(backup)) {
        Walk w = {.c = c};
        if (fs_walk(backup, restore_backup, &w))
            return fail(c, ENGINE_E_WRITE, "cannot restore", BACKUP_DIR);
    }

    job->stage = STAGE_LUMA;
    if (c->has_prev && c->prev.luma_external && c->config_ok && *c->flags.external == '1') {
        *c->flags.external = '0';
        EngineStatus status = write_config(c);
        if (status)
            return status;
    }

    job->stage = STAGE_FINISH;
    sd(c, INSTALLED_FILE, full);
    if (fs_exists(full) && fs_remove(full))
        return fail(c, ENGINE_E_WRITE, "cannot remove", INSTALLED_FILE);
    sd(c, STATE_DIR, full);
    Walk w = {.c = c};
    fs_list(full, list_state, &w);
    if (w.status)
        return fail(c, ENGINE_E_WRITE, "cannot remove", STATE_DIR);
    sd(c, PENDING_FILE, full);
    if (fs_remove(full))
        return fail(c, ENGINE_E_WRITE, "cannot remove", PENDING_FILE);
    sd(c, STATE_DIR, full);
    sd(c, "3ds", stop);
    fs_prune_empty(full, stop);
    job->font = false;
    return ENGINE_OK;
}

/* ---------------------------------------------------------------- entry points */

EngineStatus engine_run(Job *job)
{
    Ctx *c = calloc(1, sizeof(Ctx));
    if (!c)
        return ENGINE_E_MEMORY;
    c->job = job;
    c->m = job->m;
    job->stage = STAGE_CHECK;
    job->error[0] = 0;
    job->kept = job->skipped = 0;
    job->luma_manual = false;

    EngineStatus status = ENGINE_OK;
    load_state(c);
    if (write_pending(c))
        status = fail(c, ENGINE_E_WRITE, "write failed", PENDING_FILE);
    else
        status = job->op == OP_REMOVE ? run_remove(c) : run_install(c);

    if (c->has_prev)
        installed_free(&c->prev);
    installed_free(&c->next);
    free(c->config);
    free(c);
    return status;
}

typedef struct {
    const char *dir;
    int status;
} Tidy;

static bool ends_with(const char *s, const char *suffix)
{
    size_t n = strlen(s), k = strlen(suffix);
    return n > k && !strcmp(s + n - k, suffix);
}

/* <TID>.3dsua-full: a whole staging - put it in place, moving whatever is there aside. */
static void tidy_ready(const char *name, void *ctx)
{
    Tidy *t = ctx;
    if (!ends_with(name, FULL_SUFFIX))
        return;
    char base[PATH_CAP], ready[PATH_CAP], old[PATH_CAP];
    if (snprintf(ready, sizeof(ready), "%s/%s", t->dir, name) >= (int)sizeof(ready))
        return;
    snprintf(base, sizeof(base), "%s", ready);
    base[strlen(base) - strlen(FULL_SUFFIX)] = 0;
    snprintf(old, sizeof(old), "%s" OLD_SUFFIX, base);
    if (fs_exists(base))
        t->status |= fs_remove_tree(old) || fs_rename(base, old);
    t->status |= fs_rename(ready, base);
}

/* <TID>.3dsua-new: never known to be whole, and the repeated run writes it again. */
static void tidy_title(const char *name, void *ctx)
{
    Tidy *t = ctx;
    if (!ends_with(name, NEW_SUFFIX))
        return;
    char staging[PATH_CAP];
    if (snprintf(staging, sizeof(staging), "%s/%s", t->dir, name) >= (int)sizeof(staging))
        return;
    t->status |= fs_remove_tree(staging);
}

/* <TID>.3dsua-old: the set being replaced, possibly missing the files already moved out of
 * it - never put back; with no folder in its place the title runs stock until the repeat. */
static void tidy_old(const char *name, void *ctx)
{
    Tidy *t = ctx;
    if (!ends_with(name, OLD_SUFFIX))
        return;
    char old[PATH_CAP];
    if (snprintf(old, sizeof(old), "%s/%s", t->dir, name) >= (int)sizeof(old))
        return;
    t->status |= fs_remove_tree(old);
}

static void tidy_tmp(const char *name, void *ctx)
{
    Tidy *t = ctx;
    char path[PATH_CAP];
    if (snprintf(path, sizeof(path), "%s/%s", t->dir, name) >= (int)sizeof(path))
        return;
    if (ends_with(name, FS_TMP_SUFFIX)) {
        t->status |= fs_remove(path);
    } else if (ends_with(name, FS_OK_SUFFIX)) {
        /* whole and checked: put it in place (luma/config.ini must never stay missing) */
        path[strlen(path) - strlen(FS_OK_SUFFIX)] = 0;
        t->status |= fs_finish_replace(path);
    }
}

EngineStatus engine_recover(const char *sd_root)
{
    static const char *const tmp_dirs[] = {"luma", "luma/sysmodules", TITLES "0004013000008002", STATE_DIR, STATE_DIR "/font"};
    char dir[PATH_CAP];
    snprintf(dir, sizeof(dir), "%s/luma/titles", sd_root);
    Tidy t = {dir, 0};
    fs_list(dir, tidy_ready, &t);
    fs_list(dir, tidy_title, &t);
    fs_list(dir, tidy_old, &t);
    for (size_t i = 0; i < sizeof(tmp_dirs) / sizeof(*tmp_dirs); i++) {
        char d[PATH_CAP];
        snprintf(d, sizeof(d), "%s/%s", sd_root, tmp_dirs[i]);
        t.dir = d;
        fs_list(d, tidy_tmp, &t);
    }
    return t.status ? ENGINE_E_WRITE : ENGINE_OK;
}

static int load_text(const char *sd_root, const char *rel, uint8_t **text, size_t *len)
{
    char full[PATH_CAP];
    snprintf(full, sizeof(full), "%s/%s", sd_root, rel);
    return payload_read_file(full, text, len);
}

int engine_load_installed(const char *sd_root, Installed *s)
{
    uint8_t *text;
    size_t len;
    if (load_text(sd_root, INSTALLED_FILE, &text, &len))
        return -1;
    int status = installed_parse(s, (const char *)text, len);
    free(text);
    return status ? -1 : 0;
}

int engine_load_pending(const char *sd_root, Pending *p)
{
    uint8_t *text;
    size_t len;
    if (load_text(sd_root, PENDING_FILE, &text, &len))
        return -1;
    int status = pending_parse(p, (const char *)text, len);
    free(text);
    return status ? -1 : 0;
}
