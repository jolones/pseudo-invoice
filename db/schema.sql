-- Pseudo-invoice tool — SQLite schema
-- Applied on startup if tables don't exist (via executescript).

-- Stores the hashed shared password (key='password_hash')
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
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
    created_by_name          TEXT,
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
    id          INTEGER PRIMARY KEY,
    invoice_id  INTEGER NOT NULL REFERENCES interim_invoices(id) ON DELETE CASCADE,
    actor_name  TEXT,
    action      TEXT NOT NULL,
    details_json TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sessions (
    token       TEXT PRIMARY KEY,
    actor_name  TEXT NOT NULL,
    expires_at  TIMESTAMP NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
