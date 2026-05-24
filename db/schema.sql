-- Pseudo-invoice tool — SQLite schema
-- Applied on startup if tables don't exist (via executescript).

CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY,
    email       TEXT UNIQUE NOT NULL,
    name        TEXT NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS interim_invoices (
    id                       INTEGER PRIMARY KEY,
    invoice_number           TEXT UNIQUE NOT NULL,
    advice_note_code         TEXT,
    status                   TEXT NOT NULL DEFAULT 'draft',
    customer_name            TEXT NOT NULL,
    customer_email           TEXT,
    billing_address          TEXT,
    abn                      TEXT,
    notes                    TEXT,
    customer_notes           TEXT,
    issued_at                TIMESTAMP,
    paid_at                  TIMESTAMP,
    promoted_at              TIMESTAMP,
    promoted_syrinx_order_id TEXT,
    voided_at                TIMESTAMP,
    voided_reason            TEXT,
    created_by               INTEGER REFERENCES users(id),
    created_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS interim_invoice_lines (
    id                  INTEGER PRIMARY KEY,
    invoice_id          INTEGER NOT NULL REFERENCES interim_invoices(id) ON DELETE CASCADE,
    description         TEXT NOT NULL,
    syrinx_product_id   TEXT,
    quantity            DECIMAL(10, 2) NOT NULL,
    unit_price_ex_gst   DECIMAL(10, 2) NOT NULL,
    gst_amount          DECIMAL(10, 2) NOT NULL,
    line_total_inc_gst  DECIMAL(10, 2) NOT NULL,
    sort_order          INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS invoice_events (
    id             INTEGER PRIMARY KEY,
    invoice_id     INTEGER NOT NULL REFERENCES interim_invoices(id) ON DELETE CASCADE,
    actor_user_id  INTEGER REFERENCES users(id),
    action         TEXT NOT NULL,
    details_json   TEXT,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sessions (
    token       TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    expires_at  TIMESTAMP NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Dev seed: insert a test user if none exist.
-- Remove or replace for production.
INSERT OR IGNORE INTO users (email, name) VALUES ('olliejones88@gmail.com', 'Ollie Jones');
INSERT OR IGNORE INTO users (email, name) VALUES ('alastair@bosshardmedical.com.au', 'Alastair Peattie');
