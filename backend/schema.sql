-- tringgg database schema (SQLite)
-- All timestamps are stored as UTC text like 2026-11-23T12:00:00Z
CREATE TABLE IF NOT EXISTS gate_locations (gate_id TEXT PRIMARY KEY, lat REAL NOT NULL, lng REAL NOT NULL);
CREATE TABLE IF NOT EXISTS collector_locations (collector_id INTEGER PRIMARY KEY REFERENCES collectors(id), lat REAL NOT NULL, lng REAL NOT NULL, source TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS collector_credentials (collector_id INTEGER PRIMARY KEY REFERENCES collectors(id), pin_hash TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS households (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  gate_id    TEXT    NOT NULL UNIQUE,          -- printed on the QR at the gate, e.g. KTM-W10-0042
  phone      TEXT    NOT NULL UNIQUE,          -- 10-digit local number, e.g. 9841234567
  name       TEXT,
  ward       INTEGER,
  address    TEXT,
  created_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS collectors (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  name       TEXT    NOT NULL,
  phone      TEXT    UNIQUE,
  vehicle_no TEXT,
  created_at TEXT    NOT NULL
);

-- A "ticket" = one pickup request from one household
CREATE TABLE IF NOT EXISTS pickup_requests (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  household_id INTEGER NOT NULL REFERENCES households(id),
  waste_type   TEXT    NOT NULL CHECK (waste_type IN ('green', 'red', 'both')),
  source       TEXT    NOT NULL CHECK (source IN ('missed_call', 'app')),
  status       TEXT    NOT NULL DEFAULT 'requested'
               CHECK (status IN ('requested', 'assigned', 'completed', 'cancelled', 'expired')),
  collector_id INTEGER REFERENCES collectors(id),
  created_at   TEXT    NOT NULL,
  updated_at   TEXT    NOT NULL,
  assigned_at  TEXT,
  closed_at    TEXT
);

-- ACTIVE TICKET LOCK: the database itself refuses a second open ticket for the same
-- household, so spam calls / double taps can never create duplicates (even under load).
CREATE UNIQUE INDEX IF NOT EXISTS one_active_ticket_per_household
  ON pickup_requests (household_id)
  WHERE status IN ('requested', 'assigned');

CREATE INDEX IF NOT EXISTS idx_requests_status ON pickup_requests (status);

-- One row per completed pickup (the proof of collection)
CREATE TABLE IF NOT EXISTS collection_events (
  id                    INTEGER PRIMARY KEY AUTOINCREMENT,
  ticket_id             INTEGER NOT NULL UNIQUE REFERENCES pickup_requests(id),
  household_id          INTEGER NOT NULL REFERENCES households(id),
  collector_id          INTEGER NOT NULL REFERENCES collectors(id),
  scanned_gate_id       TEXT    NOT NULL,       -- what the collector's QR scan returned
  segregation_verified  INTEGER NOT NULL CHECK (segregation_verified IN (0, 1)),
  points_awarded        INTEGER NOT NULL DEFAULT 0,
  notes                 TEXT,
  collected_at          TEXT    NOT NULL
);

-- Green Points ledger: balance = SUM(points). Never edit rows, only add new ones.
CREATE TABLE IF NOT EXISTS green_points_ledger (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  household_id INTEGER NOT NULL REFERENCES households(id),
  event_id     INTEGER REFERENCES collection_events(id),
  points       INTEGER NOT NULL,
  reason       TEXT    NOT NULL,
  created_at   TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ledger_household ON green_points_ledger (household_id);

-- Every missed call that hits the webhook, useful for spotting spam
CREATE TABLE IF NOT EXISTS missed_calls (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  caller_phone TEXT    NOT NULL,
  household_id INTEGER REFERENCES households(id),
  outcome      TEXT    NOT NULL CHECK (outcome IN ('created', 'duplicate', 'unregistered')),
  ticket_id    INTEGER REFERENCES pickup_requests(id),
  received_at  TEXT    NOT NULL
);
