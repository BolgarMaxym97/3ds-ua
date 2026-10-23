-- One row per report from the app. No IP, no country: the Worker never reads them.
CREATE TABLE events (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  received_at   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  install_id    TEXT    NOT NULL,  -- random, made on the console; shown on the Help screen
  event         TEXT    NOT NULL,  -- install | update | reinstall | remove | error
  app_version   TEXT    NOT NULL,
  prev_version  TEXT,              -- what the update replaced
  model         TEXT,              -- "New 3DS XL", ...
  system_version TEXT,             -- "11.17.0-50E"
  luma_version  TEXT,
  region        TEXT,
  slot          TEXT,              -- ru | en
  glyphs        TEXT,              -- real | default
  font          TEXT,              -- why the font is or is not there
  duration_ms   INTEGER,
  error_stage   TEXT,
  error_code    INTEGER,
  error_detail  TEXT,
  log           TEXT
);

CREATE INDEX events_install ON events (install_id, received_at);
CREATE INDEX events_received ON events (received_at);
