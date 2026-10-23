import { SELF } from "cloudflare:test";
import { env } from "cloudflare:workers";
import { beforeEach, describe, expect, it } from "vitest";

const URL = "https://stats.example/v1/event";

// What installer/source/stats.c sends after a successful update.
const update = {
  v: 1,
  id: "K7QM29XD",
  event: "update",
  app: "2.0.0",
  prev: "1.12.0",
  model: "New 3DS XL",
  system: "11.17.0-50E",
  luma: "13.4",
  region: "EUR",
  slot: "ru",
  glyphs: "real",
  font: "ok",
  ms: 66900,
  log: "check 0.4s backup 0.1s files 63.9s font 2.1s luma 0.2s finish 0.2s; moved 152 written 121",
};

function post(body: unknown, headers: Record<string, string> = {}) {
  return SELF.fetch(URL, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: typeof body === "string" ? body : JSON.stringify(body),
  });
}

async function rows() {
  const { results } = await env.DB.prepare("SELECT * FROM events ORDER BY id").all();
  return results;
}

describe("POST /v1/event", () => {
  beforeEach(async () => {
    await env.DB.exec("DELETE FROM events");
  });

  it("stores an update with every field and a server timestamp", async () => {
    const response = await post(update);

    expect(response.status).toBe(204);
    const [row] = await rows();
    expect(row).toMatchObject({
      install_id: "K7QM29XD",
      event: "update",
      app_version: "2.0.0",
      prev_version: "1.12.0",
      model: "New 3DS XL",
      system_version: "11.17.0-50E",
      luma_version: "13.4",
      region: "EUR",
      slot: "ru",
      glyphs: "real",
      font: "ok",
      duration_ms: 66900,
      error_stage: null,
      log: update.log,
    });
    expect(row.received_at).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/);
  });

  it("stores an error with its stage, code and detail", async () => {
    const response = await post({
      v: 1, id: "K7QM29XD", event: "error", app: "2.0.0",
      stage: "files", code: 4, detail: "write failed: luma/titles/0004003000009802/code.ips",
    });

    expect(response.status).toBe(204);
    expect(await rows()).toMatchObject([{ event: "error", error_stage: "files", error_code: 4, prev_version: null }]);
  });

  it("keeps no trace of the sender's address", async () => {
    await post(update, { "CF-Connecting-IP": "203.0.113.7" });

    expect(JSON.stringify(await rows())).not.toContain("203.0.113.7");
  });

  it.each([
    ["not JSON", "{oops"],
    ["an array", [update]],
    ["an unknown version", { ...update, v: 2 }],
    ["a malformed id", { ...update, id: "k7qm-29xd" }],
    ["an id with I/L/O/U", { ...update, id: "K7QM29XO" }],
    ["an unknown event", { ...update, event: "slot" }],
    ["no app version", { ...update, app: undefined }],
    ["a number where text belongs", { ...update, model: 3 }],
    ["a fractional duration", { ...update, ms: 1.5 }],
    ["an oversized log", { ...update, log: "x".repeat(2049) }],
  ])("refuses %s and stores nothing", async (_, body) => {
    const response = await post(body);

    expect(response.status).toBe(400);
    expect(await rows()).toHaveLength(0);
  });

  it("refuses a body over 4 KB", async () => {
    const response = await post({ ...update, detail: "x".repeat(5000) });

    expect(response.status).toBe(413);
    expect(await rows()).toHaveLength(0);
  });

  it("answers only POST", async () => {
    expect((await SELF.fetch(URL)).status).toBe(405);
  });
});

describe("other paths", () => {
  it("GET /v1/health says ok", async () => {
    const response = await SELF.fetch("https://stats.example/v1/health");

    expect(response.status).toBe(200);
    expect(await response.text()).toBe("ok");
  });

  it("anything else is 404", async () => {
    expect((await SELF.fetch("https://stats.example/")).status).toBe(404);
  });
});
