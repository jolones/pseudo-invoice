"""
DB access functions. Raw sqlite3 — no ORM.
Each function takes a connection and returns dicts or raises.
"""

import json
import os
import sqlite3
from datetime import datetime


# ── Users ─────────────────────────────────────────────────────────────────────

def get_user_by_email(conn: sqlite3.Connection, email: str) -> dict | None:
    row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    return dict(row) if row else None


def get_user_by_id(conn: sqlite3.Connection, user_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


# ── Sessions ──────────────────────────────────────────────────────────────────

def create_session(conn: sqlite3.Connection, user_id: int, token: str, expires_at: datetime):
    conn.execute(
        "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
        (token, user_id, expires_at.isoformat()),
    )


def delete_session(conn: sqlite3.Connection, token: str):
    conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


# ── Invoice numbering ─────────────────────────────────────────────────────────

def next_invoice_number(conn: sqlite3.Connection) -> str:
    prefix = os.getenv("INVOICE_NUMBER_PREFIX", "INT")
    year = datetime.now().year
    row = conn.execute(
        "SELECT COUNT(*) FROM interim_invoices WHERE invoice_number LIKE ?",
        (f"{prefix}-{year}-%",),
    ).fetchone()
    seq = (row[0] if row else 0) + 1
    return f"{prefix}-{year}-{seq:04d}"


# ── Invoices ──────────────────────────────────────────────────────────────────

def get_invoice(conn: sqlite3.Connection, invoice_id: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM interim_invoices WHERE id = ?", (invoice_id,)
    ).fetchone()
    return dict(row) if row else None


def list_invoices(conn: sqlite3.Connection, statuses: list[str] | None = None) -> list[dict]:
    if statuses:
        placeholders = ",".join("?" * len(statuses))
        rows = conn.execute(
            f"SELECT * FROM interim_invoices WHERE status IN ({placeholders}) ORDER BY created_at DESC",
            statuses,
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM interim_invoices ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def create_invoice(
    conn: sqlite3.Connection,
    data: dict,
    lines: list[dict],
    user_id: int,
) -> int:
    invoice_number = next_invoice_number(conn)
    cursor = conn.execute(
        """
        INSERT INTO interim_invoices
            (invoice_number, status, customer_name, customer_email,
             billing_address, abn, notes, customer_notes, created_by)
        VALUES (?, 'draft', ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            invoice_number,
            data["customer_name"],
            data.get("customer_email") or None,
            data.get("billing_address") or None,
            data.get("abn") or None,
            data.get("notes") or None,
            data.get("customer_notes") or None,
            user_id,
        ),
    )
    invoice_id = cursor.lastrowid

    for i, line in enumerate(lines):
        qty = float(line["quantity"])
        unit_ex = float(line["unit_price_ex_gst"])
        gst = round(qty * unit_ex * 0.10, 2)
        total = round(qty * unit_ex + gst, 2)
        conn.execute(
            """
            INSERT INTO interim_invoice_lines
                (invoice_id, description, syrinx_product_id,
                 quantity, unit_price_ex_gst, gst_amount, line_total_inc_gst, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                invoice_id,
                line["description"],
                line.get("syrinx_product_id") or None,
                qty,
                unit_ex,
                gst,
                total,
                i,
            ),
        )

    log_event(conn, invoice_id, user_id, "created")
    return invoice_id


def update_invoice_status(
    conn: sqlite3.Connection,
    invoice_id: int,
    status: str,
    **extra_fields,
):
    set_pairs = ["status = ?", "updated_at = CURRENT_TIMESTAMP"]
    values = [status]
    for col, val in extra_fields.items():
        set_pairs.append(f"{col} = ?")
        values.append(val)
    values.append(invoice_id)
    conn.execute(
        f"UPDATE interim_invoices SET {', '.join(set_pairs)} WHERE id = ?",
        values,
    )


def get_invoice_lines(conn: sqlite3.Connection, invoice_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM interim_invoice_lines WHERE invoice_id = ? ORDER BY sort_order",
        (invoice_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def invoice_totals(lines: list[dict]) -> dict:
    subtotal = sum(float(l["unit_price_ex_gst"]) * float(l["quantity"]) for l in lines)
    gst = sum(float(l["gst_amount"]) for l in lines)
    total = sum(float(l["line_total_inc_gst"]) for l in lines)
    return {"subtotal": round(subtotal, 2), "gst": round(gst, 2), "total": round(total, 2)}


# ── Events ────────────────────────────────────────────────────────────────────

def get_invoice_events(conn: sqlite3.Connection, invoice_id: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT e.*, u.name AS actor_name
        FROM invoice_events e
        LEFT JOIN users u ON u.id = e.actor_user_id
        WHERE e.invoice_id = ?
        ORDER BY e.created_at
        """,
        (invoice_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def log_event(
    conn: sqlite3.Connection,
    invoice_id: int,
    actor_user_id: int | None,
    action: str,
    details: dict | None = None,
):
    conn.execute(
        "INSERT INTO invoice_events (invoice_id, actor_user_id, action, details_json) VALUES (?, ?, ?, ?)",
        (invoice_id, actor_user_id, action, json.dumps(details) if details else None),
    )


# ── Syrinx promotion (stub) ───────────────────────────────────────────────────

def promote_via_api(invoice: dict, lines: list[dict]) -> str:
    raise NotImplementedError(
        "Syrinx API write capability not yet confirmed. "
        "Use the manual promotion screen instead."
    )
