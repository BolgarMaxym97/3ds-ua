# Install statistics

A Cloudflare Worker with a D1 database that collects one anonymous report per finished
install, update, removal or error from the «Українізатор 3DS» app. The app sends it only when
the user left «Ділитися анонімною статистикою» on and the console is on Wi-Fi, and it never
reads the answer.

- `POST /v1/event` — one report, JSON, at most 4 KB. `204` on success, `400` for a malformed
  report, `413` for an oversized one.
- `GET /v1/health` — `ok`, for checking that a console can reach the Worker at all.

What a report holds is defined in `src/event.ts`; `installer/source/stats.c` builds it. No IP,
no country: the Worker never reads them, and Workers Logs is off in `wrangler.jsonc` so that
Cloudflare keeps no request log either. The install ID is random, made on the console, and
shown in small print on the app's Help screen — ask a user for a photo of that screen and look
the ID up below.

## Develop

```bash
npm install
npm test                 # Vitest inside the Workers runtime, local D1
npm run typecheck
npm run dev              # local Worker on :8787 with a local D1
npx wrangler d1 migrations apply 3ds-ua-stats --local   # once, before `npm run dev`
```

## Deploy (by hand)

```bash
npx wrangler login
npx wrangler d1 create 3ds-ua-stats
```

It prints a `database_id` — it is already in `wrangler.jsonc`; answer "no" when Wrangler offers to add the database itself (it would add a second binding). Then:

```bash
npx wrangler d1 migrations apply 3ds-ua-stats --remote   # expect 0001_events.sql ✅
npx wrangler deploy                                      # prints https://3ds-ua-stats.<account>.workers.dev
curl https://3ds-ua-stats.<account>.workers.dev/v1/health  # expect: ok
```

The address goes into the app (`STATS_URL` in `installer/source/stats.h`); changing it later
takes a new release.

## Queries

`npx wrangler d1 execute 3ds-ua-stats --remote --command "<SQL>"`, or the D1 console in the
Cloudflare dashboard.

Everything about one user (the ID from their Help screen, without the dash):

```sql
SELECT received_at, event, app_version, prev_version, model, slot, glyphs, font,
       error_stage, error_code, error_detail, log
FROM events WHERE install_id = 'K7QM29XD' ORDER BY received_at;
```

Installs and updates per day:

```sql
SELECT substr(received_at, 1, 10) AS day, event, count(*) AS n
FROM events WHERE event IN ('install', 'update', 'reinstall')
GROUP BY day, event ORDER BY day DESC;
```

Consoles with the mod right now (last event of each ID is not a removal):

```sql
SELECT count(*) FROM (
  SELECT install_id, event FROM events e
  WHERE id = (SELECT max(id) FROM events WHERE install_id = e.install_id)
) WHERE event <> 'remove';
```

By model, by slot, by app version:

```sql
SELECT model, count(DISTINCT install_id) AS consoles FROM events GROUP BY model ORDER BY consoles DESC;
SELECT slot, count(DISTINCT install_id) AS consoles FROM events WHERE slot IS NOT NULL GROUP BY slot;
SELECT app_version, count(*) AS reports FROM events GROUP BY app_version ORDER BY app_version DESC;
```

Why the real letters were not installed:

```sql
SELECT font, count(DISTINCT install_id) AS consoles FROM events
WHERE event IN ('install', 'update', 'reinstall') GROUP BY font;
```

Errors, newest first:

```sql
SELECT received_at, install_id, app_version, model, error_stage, error_code, error_detail
FROM events WHERE event = 'error' ORDER BY received_at DESC LIMIT 50;
```
