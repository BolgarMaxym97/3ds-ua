/*
 * Host test of installer/source/engine over the real payload: install, update, slot change,
 * the text variant switch, a title of another build, foreign files, the Luma config edit,
 * removal - and the power cut at every n-th change of the card, after which recovery plus
 * the repeated operation must give the same card as an uninterrupted run.
 *
 *     engine_test <dist_installer/romfs/data> <config.ini> <scratch dir> [cut spacing]
 *
 * The cut spacing multiplies the gap between cuts (default 4; 1 cuts at ~1 in 5 changes and
 * takes a few minutes; 0 cuts at every single change).
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "../source/engine/engine.h"
#include "../source/engine/fsutil.h"
#include "../source/engine/lumacfg.h"
#include "../source/payload/payload.h"
#include "../source/sysfont/sha256.h"

static int failures;
static const char *data_root, *config_src;
static char sd_root[256];
static Manifest m;
static uint64_t unmet_folder; /* a folder whose title is "another build", 0 for none */
static bool font_fails;       /* build_font() gives up, as on a console with another font */
static int font_builds;       /* how often build_font() ran */

static void expect(int ok, const char *what)
{
    printf("%s  %s\n", ok ? "ok  " : "FAIL", what);
    failures += !ok;
}

static bool need_met(const Need *n, void *ctx)
{
    (void)ctx;
    return n->folder != unmet_folder;
}

static uint8_t *build_font(void *ctx, size_t *len)
{
    (void)ctx;
    font_builds++;
    if (font_fails)
        return NULL;
    *len = 70000;
    uint8_t *font = malloc(*len);
    for (size_t i = 0; i < *len; i++)
        font[i] = (uint8_t)(i * 7 + 3);
    return font;
}

static void path(char *out, const char *rel) { snprintf(out, 256, "%s/%s", sd_root, rel); }

static void put(const char *rel, const char *text)
{
    char full[256];
    path(full, rel);
    fs_write(full, text, strlen(text));
}

static bool has(const char *rel)
{
    char full[256];
    path(full, rel);
    return fs_exists(full);
}

static char *slurp(const char *rel, size_t *len)
{
    char full[256];
    path(full, rel);
    uint8_t *data;
    if (payload_read_file(full, &data, len))
        return NULL;
    return (char *)data;
}

static void fresh_card(bool game, bool external)
{
    fs_budget = -1;
    fs_remove_tree(sd_root);
    uint8_t *cfg;
    size_t len;
    if (payload_read_file(config_src, &cfg, &len)) {
        fprintf(stderr, "cannot read %s\n", config_src);
        exit(2);
    }
    LumaConfig c;
    if (lumacfg_parse(&c, (char *)cfg, len)) {
        fprintf(stderr, "the sample config does not parse\n");
        exit(2);
    }
    *c.game = game ? '1' : '0';
    *c.external = external ? '1' : '0';
    char full[256];
    path(full, "luma/config.ini");
    fs_write(full, cfg, len);
    free(cfg);
}

static Job job_for(Op op, Slot slot, Glyphs glyphs, bool want_font)
{
    Job j = {0};
    j.m = &m;
    j.data_root = data_root;
    j.sd_root = sd_root;
    j.op = op;
    j.slot = slot;
    j.model = MODEL_OLD3DS;
    j.glyphs = glyphs;
    j.want_font = want_font;
    j.need_met = need_met;
    j.build_font = build_font;
    return j;
}

static EngineStatus run(Op op, Slot slot, Glyphs glyphs, bool want_font, Job *out)
{
    Job j = job_for(op, slot, glyphs, want_font);
    EngineStatus status = engine_run(&j);
    if (status)
        printf("      engine: %s\n", j.error);
    if (out)
        *out = j;
    return status;
}

/* Every file of a set (and the font, if any) is on the card with its sha256. */
static bool card_matches(Slot slot, Glyphs glyphs, bool font)
{
    const FileSet *set = &m.sets[slot][MODEL_OLD3DS][glyphs];
    for (size_t i = 0; i < set->count; i++) {
        const Entry *e = &set->entries[i];
        char full[256];
        uint8_t sha[32];
        path(full, e->path);
        if (unmet_folder) {
            char tid[17];
            snprintf(tid, sizeof(tid), "%016llX", (unsigned long long)unmet_folder);
            if (strstr(e->path, tid)) {
                if (fs_exists(full))
                    return false;
                continue;
            }
        }
        if (fs_sha256(full, sha) || memcmp(sha, m.blobs[e->blob].sha, 32)) {
            printf("      differs: %s\n", e->path);
            return false;
        }
    }
    for (size_t i = 0; i < m.font_set.count; i++)
        if (has(m.font_set.entries[i].path) != font)
            return false;
    return has(m.font_path + 1) == font;
}

/* A fingerprint of the whole card: every file's path and sha256. */
typedef struct {
    Sha256 s;
} Print;

static int print_file(const char *rel, void *ctx)
{
    Print *p = ctx;
    char full[256];
    uint8_t sha[32];
    path(full, rel);
    fs_sha256(full, sha);
    sha256_update(&p->s, rel, strlen(rel) + 1);
    sha256_update(&p->s, sha, 32);
    return 0;
}

static void card_print(uint8_t out[32])
{
    Print p;
    sha256_init(&p.s);
    fs_walk(sd_root, print_file, &p);
    sha256_final(&p.s, out);
}

static int config_flags(char *game, char *external)
{
    size_t len;
    char *cfg = slurp("luma/config.ini", &len);
    LumaConfig c;
    int status = !cfg || lumacfg_parse(&c, cfg, len);
    if (!status) {
        *game = *c.game;
        *external = *c.external;
    }
    free(cfg);
    return status;
}

/* ---------------------------------------------------------------- scenarios */

static void test_lumacfg(void)
{
    char good[] = "[meta]\nconfig_version_major = 3\nconfig_version_minor = 13\n[boot]\nenable_game_patching = 0\n"
                  "enable_external_firm_and_modules=1\n";
    LumaConfig c;
    expect(lumacfg_parse(&c, good, strlen(good)) == 0 && *c.game == '0' && *c.external == '1', "config: parses");
    char newer[] = "[meta]\nconfig_version_major = 3\nconfig_version_minor = 14\n[boot]\nenable_game_patching = 0\n"
                   "enable_external_firm_and_modules = 1\n";
    expect(lumacfg_parse(&c, newer, strlen(newer)) != 0, "config: an unchecked format version is refused");
    char twice[] = "[meta]\nconfig_version_major = 3\nconfig_version_minor = 13\n[boot]\nenable_game_patching = 0\n"
                   "enable_game_patching = 1\nenable_external_firm_and_modules = 1\n";
    expect(lumacfg_parse(&c, twice, strlen(twice)) != 0, "config: a repeated key is refused");
    char wide[] = "[meta]\nconfig_version_major = 3\nconfig_version_minor = 13\n[boot]\nenable_game_patching = 01\n"
                  "enable_external_firm_and_modules = 1\n";
    expect(lumacfg_parse(&c, wide, strlen(wide)) != 0, "config: a value that is not 0/1 is refused");
}

static void test_state(void)
{
    Installed s = {0};
    strcpy(s.version, "1.2.3");
    s.slot = SLOT_EN;
    s.glyphs = GLYPHS_REAL;
    s.font = true;
    s.luma_external = true;
    s.skipped = 2;
    uint8_t sha[32] = {1, 2, 3};
    installed_add(&s, sha, 42, "luma/titles/0004003000009802/code.ips");
    size_t len;
    char *text = installed_format(&s, &len);
    Installed t;
    int status = installed_parse(&t, text, len);
    expect(!status && t.slot == SLOT_EN && t.glyphs == GLYPHS_REAL && t.font && !t.luma_game && t.luma_external &&
               t.skipped == 2 && t.count == 1 && t.files[0].size == 42 && !memcmp(t.files[0].sha, sha, 32) &&
               !strcmp(t.version, "1.2.3"),
           "installed.txt: round trip");
    text[len - 2] = 'x'; /* "end" damaged: a cut-off file */
    expect(installed_parse(&t, text, len) != 0, "installed.txt: a truncated file is refused");
    free(text);
    installed_free(&s);
    if (!status)
        installed_free(&t);
}

static void test_flow(void)
{
    Job j;
    fresh_card(false, false);
    /* a foreign file in one of our folders, another at one of our paths */
    put("luma/titles/0004003000009802/someone-else.bin", "foreign");
    put("luma/titles/0004001000022000/code.ips", "PATCHforeignEOF");
    put("luma/titles/0004001000022000/._code.ips", "Finder metadata");

    clock_t t0 = clock();
    expect(run(OP_INSTALL, SLOT_RU, GLYPHS_DEFAULT, true, &j) == ENGINE_OK, "install ru: runs");
    printf("      %d files, %.2f s\n", j.total, (double)(clock() - t0) / CLOCKS_PER_SEC);
    expect(card_matches(SLOT_RU, GLYPHS_DEFAULT, true), "install ru: every file and the font are on the card");
    expect(!has(PENDING_FILE) && has(INSTALLED_FILE), "install ru: pending gone, installed.txt there");
    expect(!has("luma/titles/0004003000009802/someone-else.bin") && has(BACKUP_DIR "/luma/titles/0004003000009802/someone-else.bin"),
           "install ru: a foreign file is moved to the backup");
    expect(has(BACKUP_DIR "/luma/titles/0004001000022000/code.ips"), "install ru: a foreign file at our path is backed up");
    expect(!has("luma/titles/0004001000022000/._code.ips") && !has(BACKUP_DIR "/luma/titles/0004001000022000/._code.ips"),
           "install ru: Finder's ._ files are dropped, not backed up");
    char game = 0, external = 0;
    expect(!config_flags(&game, &external) && game == '1' && external == '1' && has(CONFIG_BACKUP),
           "install ru: both Luma flags turned on, the old config kept");
    Installed s;
    expect(!engine_load_installed(sd_root, &s) && s.luma_game && s.luma_external && s.font && s.glyphs == GLYPHS_DEFAULT,
           "install ru: installed.txt records the flags and the font");
    installed_free(&s);

    expect(run(OP_INSTALL, SLOT_RU, GLYPHS_DEFAULT, true, &j) == ENGINE_OK && j.total == 0, "repeat: nothing to write");

    expect(run(OP_INSTALL, SLOT_RU, GLYPHS_REAL, true, &j) == ENGINE_OK, "real letters: runs");
    int changed = 0;
    const FileSet *def = &m.sets[SLOT_RU][MODEL_OLD3DS][GLYPHS_DEFAULT], *real = &m.sets[SLOT_RU][MODEL_OLD3DS][GLYPHS_REAL];
    for (size_t i = 0; i < real->count; i++) {
        int same = 0;
        for (size_t k = 0; k < def->count; k++)
            same |= !strcmp(def->entries[k].path, real->entries[i].path) && def->entries[k].blob == real->entries[i].blob;
        changed += !same;
    }
    printf("      %d files in changed folders, %d moved, %d written (%d differ)\n", j.total, j.moved, j.total - j.moved, changed);
    expect(j.total - j.moved == changed, "real letters: only the files that differ are written");
    expect(card_matches(SLOT_RU, GLYPHS_REAL, true), "real letters: the card is the real set");

    expect(run(OP_INSTALL, SLOT_EN, GLYPHS_REAL, true, &j) == ENGINE_OK && card_matches(SLOT_EN, GLYPHS_REAL, true),
           "slot change: the card is the en set");
    size_t len;
    char *locale = slurp("luma/titles/0004003000009802/locale.txt", &len);
    expect(locale && len == 6 && !memcmp(locale, "EUR EN", 6), "slot change: locale.txt follows");
    free(locale);

    expect(run(OP_INSTALL, SLOT_EN, GLYPHS_REAL, false, &j) == ENGINE_OK && j.glyphs_set == GLYPHS_DEFAULT &&
               card_matches(SLOT_EN, GLYPHS_DEFAULT, false),
           "no font: the patch goes and the text falls back to stand-ins");

    unmet_folder = 0x0004001000022000ull;
    expect(run(OP_INSTALL, SLOT_EN, GLYPHS_DEFAULT, false, &j) == ENGINE_OK && j.skipped == 1 &&
               card_matches(SLOT_EN, GLYPHS_DEFAULT, false),
           "another build: that folder is left out and cleared");
    unmet_folder = 0;

    expect(run(OP_REMOVE, SLOT_EN, GLYPHS_DEFAULT, false, &j) == ENGINE_OK, "remove: runs");
    expect(!has("luma/titles/0004003000009802/banner_22800.bin") && !has("3ds/3ds-ua"), "remove: the mod and its state are gone");
    expect(has("luma/titles/0004003000009802/someone-else.bin"), "remove: the foreign file is back");
    char *ips = slurp("luma/titles/0004001000022000/code.ips", &len);
    expect(ips && len == 15 && !memcmp(ips, "PATCHforeignEOF", 15), "remove: the foreign file at our path is back");
    free(ips);
    expect(!config_flags(&game, &external) && game == '1' && external == '0',
           "remove: external modules back off, game patching left on");
}

static void test_one_run(void)
{
    Job j;
    fresh_card(true, true);
    expect(run(OP_INSTALL, SLOT_RU, GLYPHS_REAL, true, &j) == ENGINE_OK && j.font && j.glyphs_set == GLYPHS_REAL &&
               card_matches(SLOT_RU, GLYPHS_REAL, true),
           "one run: the real letters and the font go on together");
    fresh_card(true, true);
    font_fails = true;
    expect(run(OP_INSTALL, SLOT_RU, GLYPHS_REAL, true, &j) == ENGINE_OK && !j.font && j.glyphs_set == GLYPHS_DEFAULT &&
               card_matches(SLOT_RU, GLYPHS_DEFAULT, false),
           "one run, font fails to build: the text falls back to stand-ins");
    Installed s;
    expect(!engine_load_installed(sd_root, &s) && s.glyphs == GLYPHS_DEFAULT && !s.font &&
               s.count == m.sets[SLOT_RU][MODEL_OLD3DS][GLYPHS_DEFAULT].count,
           "one run, font fails: installed.txt lists the stand-in set only");
    installed_free(&s);
    font_fails = false;
}

static void test_font_kept_by_sha(void)
{
    fresh_card(true, true);
    run(OP_INSTALL, SLOT_RU, GLYPHS_REAL, true, NULL);
    Installed s;
    engine_load_installed(sd_root, &s);
    uint8_t current[32];
    memcpy(current, installed_find(&s, m.font_path + 1)->sha, 32);
    installed_free(&s);

    Job j = job_for(OP_INSTALL, SLOT_RU, GLYPHS_REAL, true);
    memcpy(j.font_sha, current, 32);
    font_builds = 0;
    expect(engine_run(&j) == ENGINE_OK && font_builds == 0, "font: this app's own font is kept");
    j = job_for(OP_INSTALL, SLOT_RU, GLYPHS_REAL, true);
    memset(j.font_sha, 0xAB, 32); /* a newer app builds another font, of the same size */
    font_builds = 0;
    expect(engine_run(&j) == ENGINE_OK && font_builds == 1, "font: one of another build is built again");
}

static void test_changed_file_kept(void)
{
    fresh_card(true, true);
    run(OP_INSTALL, SLOT_RU, GLYPHS_DEFAULT, false, NULL);
    put("luma/titles/0004003000009802/locale.txt", "EUR JPN"); /* one byte longer: changed */
    Job j;
    expect(run(OP_REMOVE, SLOT_RU, GLYPHS_DEFAULT, false, &j) == ENGINE_OK && j.kept == 1 &&
               has("luma/titles/0004003000009802/locale.txt"),
           "remove: a file changed since the install is left");
}

static void test_adopt(void)
{
    /* a copy from the Universal-Updater scripts: files of the set, no installed.txt */
    fresh_card(true, true);
    run(OP_INSTALL, SLOT_RU, GLYPHS_DEFAULT, false, NULL);
    char full[256];
    path(full, INSTALLED_FILE);
    fs_remove(full);
    put("luma/titles/0004003000009802/code.ips", "an older version of ours");
    Job j;
    expect(run(OP_INSTALL, SLOT_RU, GLYPHS_DEFAULT, false, &j) == ENGINE_OK && card_matches(SLOT_RU, GLYPHS_DEFAULT, false) &&
               !has(BACKUP_DIR "/luma/titles/0004003000009802/code.ips"),
           "adopt: an older copy is updated, not backed up as foreign");
}

/* ---------------------------------------------------------------- what a title sees */

/* A folder's contents as one value: the count and the XOR of sha256(name, sha256(file)). */
typedef struct {
    int count;
    uint8_t x[32];
} FolderPrint;

static void mix(FolderPrint *p, const char *rel, const uint8_t sha[32])
{
    Sha256 s;
    uint8_t h[32];
    sha256_init(&s);
    sha256_update(&s, rel, strlen(rel) + 1);
    sha256_update(&s, sha, 32);
    sha256_final(&s, h);
    for (int i = 0; i < 32; i++)
        p->x[i] ^= h[i];
    p->count++;
}

typedef struct {
    FolderPrint p;
    const char *dir;
} CardWalk;

static int mix_card(const char *rel, void *ctx)
{
    CardWalk *w = ctx;
    char full[300];
    uint8_t sha[32];
    snprintf(full, sizeof(full), "%s/%s", w->dir, rel);
    fs_sha256(full, sha);
    mix(&w->p, rel, sha);
    return 0;
}

static void print_set(FolderPrint *p, const FileSet *set, const char *folder)
{
    memset(p, 0, sizeof(*p));
    if (!set)
        return;
    size_t n = strlen(folder);
    for (size_t i = 0; i < set->count; i++)
        if (!strncmp(set->entries[i].path, folder, n) && set->entries[i].path[n] == '/')
            mix(p, set->entries[i].path + n + 1, m.blobs[set->entries[i].blob].sha);
}

static bool same(const FolderPrint *a, const FolderPrint *b)
{
    return a->count == b->count && !memcmp(a->x, b->x, 32);
}

typedef struct {
    const FileSet *before, *after;
    int bad;
} Seen;

static void check_folder(const char *name, void *ctx)
{
    Seen *s = ctx;
    /* staging and aside folders: Luma reads only <16 hex digits>; NS's folder holds one
     * loose file of the font patch, inert alone (the engine orders those three files) */
    if (strlen(name) != 16 || !strcmp(name, "0004013000008002"))
        return;
    char folder[64], dir[300];
    snprintf(folder, sizeof(folder), "luma/titles/%s", name);
    snprintf(dir, sizeof(dir), "%s/%s", sd_root, folder);
    CardWalk w = {.dir = dir};
    fs_walk(dir, mix_card, &w);
    FolderPrint before, after;
    print_set(&before, s->before, folder);
    print_set(&after, s->after, folder);
    if (!same(&w.p, &before) && !same(&w.p, &after)) {
        printf("      %s is neither the old nor the new set (%d files)\n", folder, w.p.count);
        s->bad++;
    }
}

/* Every title folder on the card is a whole set, the old one or the new one (an empty set
 * = no folder: the stock title). */
static bool titles_whole(const FileSet *before, const FileSet *after)
{
    char dir[300];
    snprintf(dir, sizeof(dir), "%s/luma/titles", sd_root);
    Seen s = {before, after, 0};
    fs_list(dir, check_folder, &s);
    return !s.bad;
}

/* Cut the power after every `step`-th change: at that moment every title must see a whole
 * set; then recover, repeat, and the card must be the same as after a clean run. */
static void cut_test(const char *name, Op op, Slot slot, Glyphs glyphs, bool from_installed, int step)
{
    uint8_t want[32], got[32];
    fresh_card(true, false);
    if (from_installed)
        run(OP_INSTALL, SLOT_RU, GLYPHS_DEFAULT, true, NULL);
    long before = 1L << 30;
    fs_budget = before;
    run(op, slot, glyphs, true, NULL);
    long changes = before - fs_budget;
    fs_budget = -1;
    card_print(want);

    const FileSet *set_before = from_installed ? &m.sets[SLOT_RU][MODEL_OLD3DS][GLYPHS_DEFAULT] : NULL;
    const FileSet *set_after = op == OP_REMOVE ? NULL : &m.sets[slot][MODEL_OLD3DS][glyphs];
    int bad = 0, cuts = 0, torn = 0;
    for (long n = 0; n < changes; n += step) {
        fresh_card(true, false);
        if (from_installed)
            run(OP_INSTALL, SLOT_RU, GLYPHS_DEFAULT, true, NULL);
        fs_budget = n;
        Job j = job_for(op, slot, glyphs, true);
        EngineStatus first = engine_run(&j);
        fs_budget = -1;
        cuts++;
        if (first == ENGINE_OK) /* the budget outlasted the run */
            continue;
        if (!titles_whole(set_before, set_after)) {
            printf("      cut %ld: a title would see part of a set\n", n);
            torn++;
        }
        Pending p;
        if (engine_recover(sd_root) || (has(PENDING_FILE) && engine_load_pending(sd_root, &p))) {
            bad++;
            continue;
        }
        /* no pending.txt: the cut came before it was written, the user just starts over */
        Job again = job_for(op, slot, glyphs, true);
        if (engine_run(&again)) {
            printf("      cut %ld: repeat failed: %s\n", n, again.error);
            bad++;
            continue;
        }
        card_print(got);
        if (memcmp(got, want, 32)) {
            printf("      cut %ld: the card differs from a clean run\n", n);
            bad++;
        }
    }
    char what[128];
    snprintf(what, sizeof(what), "power cut, %s: %d cuts over %ld changes, every title whole at the cut", name, cuts, changes);
    expect(!torn, what);
    snprintf(what, sizeof(what), "power cut, %s: all recover to a clean run's card", name);
    expect(!bad, what);
}

int main(int argc, char **argv)
{
    if (argc != 4 && argc != 5) {
        fprintf(stderr, "usage: %s <data dir> <config.ini> <scratch dir> [cut spacing]\n", argv[0]);
        return 2;
    }
    data_root = argv[1];
    config_src = argv[2];
    snprintf(sd_root, sizeof(sd_root), "%s", argv[3]);
    char mpath[512];
    snprintf(mpath, sizeof(mpath), "%s/manifest.txt", data_root);
    uint8_t *text;
    size_t len;
    if (payload_read_file(mpath, &text, &len) || manifest_parse(&m, (const char *)text, len)) {
        fprintf(stderr, "cannot read %s\n", mpath);
        return 2;
    }
    free(text);

    test_lumacfg();
    test_state();
    test_flow();
    test_one_run();
    test_font_kept_by_sha();
    test_changed_file_kept();
    test_adopt();
    int spacing = argc == 5 ? atoi(argv[4]) : 4;
    cut_test("install", OP_INSTALL, SLOT_RU, GLYPHS_DEFAULT, false, spacing > 0 ? 7 * spacing : 1);
    cut_test("update to en + real", OP_INSTALL, SLOT_EN, GLYPHS_REAL, true, spacing > 0 ? 5 * spacing : 1);
    cut_test("remove", OP_REMOVE, SLOT_RU, GLYPHS_DEFAULT, true, spacing > 0 ? 3 * spacing : 1);

    fs_remove_tree(sd_root);
    manifest_free(&m);
    printf("%s\n", failures ? "FAILED" : "all passed");
    return failures ? 1 : 0;
}
