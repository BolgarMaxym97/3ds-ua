// The report the app sends - the one place its shape is written down on this side.
// installer/source/stats.c builds it; keep the two in step.

export const MAX_BODY = 4096;

// Crockford base32 without the dash the Help screen shows: no I, L, O, U.
const INSTALL_ID = /^[0-9A-HJKMNP-TV-Z]{8}$/;
const EVENTS = ["install", "update", "reinstall", "remove", "error"] as const;

export interface StatsEvent {
  install_id: string;
  event: (typeof EVENTS)[number];
  app_version: string;
  prev_version: string | null;
  model: string | null;
  system_version: string | null;
  luma_version: string | null;
  region: string | null;
  slot: string | null;
  glyphs: string | null;
  font: string | null;
  duration_ms: number | null;
  error_stage: string | null;
  error_code: number | null;
  error_detail: string | null;
  log: string | null;
}

type Result = { ok: true; event: StatsEvent } | { ok: false; error: string };

// Optional short text: absent or null -> null; anything else must be a string within `max`.
function text(body: Record<string, unknown>, key: string, max: number): string | null | undefined {
  const value = body[key];
  if (value === undefined || value === null) return null;
  if (typeof value !== "string" || value.length > max) return undefined;
  return value;
}

function integer(body: Record<string, unknown>, key: string): number | null | undefined {
  const value = body[key];
  if (value === undefined || value === null) return null;
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < -(2 ** 31) || value > 2 ** 31) return undefined;
  return value;
}

export function parseEvent(raw: unknown): Result {
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) return { ok: false, error: "not an object" };
  const body = raw as Record<string, unknown>;

  if (body.v !== 1) return { ok: false, error: "unknown version" };
  if (typeof body.id !== "string" || !INSTALL_ID.test(body.id)) return { ok: false, error: "bad id" };
  if (typeof body.event !== "string" || !(EVENTS as readonly string[]).includes(body.event)) {
    return { ok: false, error: "bad event" };
  }
  const app = text(body, "app", 16);
  if (!app) return { ok: false, error: "bad app" };

  const fields = {
    prev_version: text(body, "prev", 16),
    model: text(body, "model", 32),
    system_version: text(body, "system", 32),
    luma_version: text(body, "luma", 16),
    region: text(body, "region", 8),
    slot: text(body, "slot", 8),
    glyphs: text(body, "glyphs", 16),
    font: text(body, "font", 32),
    duration_ms: integer(body, "ms"),
    error_stage: text(body, "stage", 32),
    error_code: integer(body, "code"),
    error_detail: text(body, "detail", 256),
    log: text(body, "log", 2048),
  };
  for (const [key, value] of Object.entries(fields)) {
    if (value === undefined) return { ok: false, error: `bad ${key}` };
  }

  return {
    ok: true,
    event: { install_id: body.id, event: body.event as StatsEvent["event"], app_version: app, ...fields } as StatsEvent,
  };
}
