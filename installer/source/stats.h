/*
 * Anonymous install statistics (stats/README.md): one report after a finished install,
 * update, removal or error, sent only when the user left the Help-screen box ticked and
 * the console is on Wi-Fi. Sent from a thread; the answer is never read.
 */
#ifndef STATS_H
#define STATS_H

#include <3ds.h>
#include <stdbool.h>

#include "stats/report.h"

/* Plain HTTP: the console's TLS does not get through to workers.dev (net test, 2026-10-23),
 * and the report holds nothing secret. */
#define STATS_URL "http://3ds-ua-stats.bolgar-maxym.workers.dev/v1/event"
/* The app's own settings - outside 3ds/3ds-ua/, which a removal clears. */
#define STATS_INI "sdmc:/3ds/3ds-ua-installer.ini"
/* How long a reboot or exit waits for a report still on its way. */
#define STATS_WAIT_MS 3000

typedef struct {
    char id[REPORT_ID_LEN + 1];
    bool enabled;
    Thread thread;
    volatile bool busy;
    char system[32];    /* "11.17.0-50E", read once at start */
    char body[REPORT_MAX + 1] __attribute__((aligned(4))); /* httpcAddPostDataRaw takes words */
} Stats;

void stats_init(Stats *s);
void stats_set_enabled(Stats *s, bool enabled);
/* Sends `r` (its id is filled in here) unless the box is unticked or there is no Wi-Fi.
 * Returns what happened, for the log: "sent", "off", "no wifi", "busy", "failed". */
const char *stats_send(Stats *s, Report *r);
/* True once nothing is on its way, or `deadline` (osGetTime()) has passed. */
bool stats_settled(const Stats *s, u64 deadline);
/* Before the app exits: wait up to STATS_WAIT_MS, then let the thread go. */
void stats_exit(Stats *s);

#endif
