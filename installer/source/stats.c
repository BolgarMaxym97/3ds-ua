#include "stats.h"

#include <stdio.h>
#include <string.h>

#include "sysfont/sha256.h"

static void save(const Stats *s)
{
    FILE *f = fopen(STATS_INI, "w");
    if (!f)
        return;
    fprintf(f, "id=%s\nstats=%d\n", s->id, s->enabled);
    fclose(f);
}

/* 40 bits from the console's random source, or - should ps:ps refuse - from timers. */
static void new_id(char out[REPORT_ID_LEN + 1])
{
    uint8_t bytes[32];
    bool ok = R_SUCCEEDED(psInit()) && R_SUCCEEDED(PS_GenerateRandomBytes(bytes, sizeof(bytes)));
    psExit();
    if (!ok) {
        u64 seed[4] = {osGetTime(), svcGetSystemTick(), (u64)(uintptr_t)&seed, svcGetSystemTick()};
        sha256(seed, sizeof(seed), bytes);
    }
    report_id_encode(bytes, out);
}

void stats_init(Stats *s)
{
    memset(s, 0, sizeof(*s));
    s->enabled = true; /* on unless the user turned it off (the README says what is sent) */
    FILE *f = fopen(STATS_INI, "r");
    if (f) {
        char line[64];
        while (fgets(line, sizeof(line), f)) {
            line[strcspn(line, "\r\n")] = 0;
            if (!strncmp(line, "id=", 3) && report_id_valid(line + 3))
                strcpy(s->id, line + 3);
            else if (!strcmp(line, "stats=0"))
                s->enabled = false;
        }
        fclose(f);
    }
    if (!s->id[0]) {
        new_id(s->id);
        save(s);
    }
    if (R_FAILED(osGetSystemVersionDataString(NULL, NULL, s->system, sizeof(s->system))))
        s->system[0] = 0;
}

void stats_set_enabled(Stats *s, bool enabled)
{
    s->enabled = enabled;
    save(s);
}

static void post(void *arg)
{
    Stats *s = arg;
    httpcContext ctx;
    /* POST data travels through httpc's shared memory: with 0 here every POST fails at once
     * (0xD8A0A003, net test 2026-10-23) */
    if (R_SUCCEEDED(httpcInit(0x1000))) {
        if (R_SUCCEEDED(httpcOpenContext(&ctx, HTTPC_METHOD_POST, STATS_URL, 0))) {
            if (R_SUCCEEDED(httpcAddRequestHeaderField(&ctx, "User-Agent", "3ds-ua-installer")) &&
                R_SUCCEEDED(httpcAddRequestHeaderField(&ctx, "Content-Type", "application/json")) &&
                R_SUCCEEDED(httpcAddPostDataRaw(&ctx, (const u32 *)s->body, strlen(s->body))) &&
                R_SUCCEEDED(httpcBeginRequest(&ctx))) {
                u32 status;
                /* the answer itself is not wanted - this only keeps the context open until
                 * the server has the whole body */
                httpcGetResponseStatusCodeTimeout(&ctx, &status, 5ull * 1000 * 1000 * 1000);
            }
            httpcCloseContext(&ctx);
        }
        httpcExit();
    }
    s->busy = false;
}

const char *stats_send(Stats *s, Report *r)
{
    if (!s->enabled)
        return "off";
    if (s->busy)
        return "busy";
    u32 wifi = 0;
    if (R_SUCCEEDED(acInit())) {
        ACU_GetWifiStatus(&wifi);
        acExit();
    }
    if (!wifi)
        return "no wifi";
    r->id = s->id;
    r->system = s->system[0] ? s->system : NULL;
    if (!report_json(r, s->body, sizeof(s->body)))
        return "failed";
    if (s->thread) { /* the previous report's thread has finished: free it */
        threadJoin(s->thread, U64_MAX);
        threadFree(s->thread);
    }
    s->busy = true;
    s32 prio = 0x30;
    svcGetThreadPriority(&prio, CUR_THREAD_HANDLE);
    s->thread = threadCreate(post, s, 16 * 1024, prio + 1, -2, false);
    if (!s->thread) {
        s->busy = false;
        return "failed";
    }
    return "sent";
}

bool stats_settled(const Stats *s, u64 deadline)
{
    return !s->busy || osGetTime() >= deadline;
}

void stats_exit(Stats *s)
{
    u64 deadline = osGetTime() + STATS_WAIT_MS;
    while (!stats_settled(s, deadline))
        svcSleepThread(20 * 1000 * 1000);
    if (s->thread && !s->busy) {
        threadJoin(s->thread, U64_MAX);
        threadFree(s->thread);
    }
    s->thread = NULL;
}
