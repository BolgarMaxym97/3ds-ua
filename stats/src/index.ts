import { MAX_BODY, parseEvent, type StatsEvent } from "./event";

// POST /v1/event  - one report from the app; 204, the app does not read the answer
// GET  /v1/health - "ok", for checking a console can reach the Worker at all
export default {
  async fetch(request, env): Promise<Response> {
    const { pathname } = new URL(request.url);

    if (pathname === "/v1/health" && request.method === "GET") return new Response("ok");
    if (pathname !== "/v1/event") return new Response(null, { status: 404 });
    if (request.method !== "POST") return new Response(null, { status: 405, headers: { Allow: "POST" } });

    const declared = Number(request.headers.get("Content-Length") ?? 0);
    if (declared > MAX_BODY) return new Response(null, { status: 413 });
    const body = await request.text();
    if (body.length > MAX_BODY) return new Response(null, { status: 413 });

    let raw: unknown;
    try {
      raw = JSON.parse(body);
    } catch {
      return new Response("bad json", { status: 400 });
    }
    const parsed = parseEvent(raw);
    if (!parsed.ok) return new Response(parsed.error, { status: 400 });

    await insert(env.DB, parsed.event);
    return new Response(null, { status: 204 });
  },
} satisfies ExportedHandler<Env>;

const COLUMNS = [
  "install_id", "event", "app_version", "prev_version", "model", "system_version", "luma_version",
  "region", "slot", "glyphs", "font", "duration_ms", "error_stage", "error_code", "error_detail", "log",
] as const satisfies readonly (keyof StatsEvent)[];

const INSERT = `INSERT INTO events (${COLUMNS.join(", ")}) VALUES (${COLUMNS.map(() => "?").join(", ")})`;

async function insert(db: D1Database, event: StatsEvent): Promise<void> {
  await db.prepare(INSERT).bind(...COLUMNS.map((column) => event[column])).run();
}
