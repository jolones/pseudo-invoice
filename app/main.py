import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exception_handlers import http_exception_handler as _default_handler

from . import models

# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(title="Bosshard Pseudo-Invoice Tool", docs_url=None, redoc_url=None)

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR.parent / "db" / "invoices.db"
SCHEMA_PATH = BASE_DIR.parent / "db" / "schema.sql"

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
INVOICE_HEADER_LABEL = os.getenv("INVOICE_HEADER_LABEL", "Payment Request")

serializer = URLSafeTimedSerializer(SECRET_KEY)

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


# ── Database ──────────────────────────────────────────────────────────────────

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db_connection():
    conn = get_db()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    schema = SCHEMA_PATH.read_text()
    with db_connection() as conn:
        conn.executescript(schema)


# ── Auth dependency ───────────────────────────────────────────────────────────

def current_user(request: Request):
    token = request.cookies.get("session")
    if not token:
        raise HTTPException(status_code=302, headers={"Location": "/login"})

    with db_connection() as conn:
        row = conn.execute(
            """
            SELECT u.id, u.email, u.name
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token = ?
              AND s.expires_at > CURRENT_TIMESTAMP
            """,
            (token,),
        ).fetchone()

    if not row:
        raise HTTPException(status_code=302, headers={"Location": "/login"})

    return dict(row)


@app.exception_handler(StarletteHTTPException)
async def auth_redirect_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 302 and exc.headers and "Location" in exc.headers:
        return RedirectResponse(url=exc.headers["Location"])
    return await _default_handler(request, exc)


# ── Startup ───────────────────────────────────────────────────────────────────

@app.on_event("startup")
def on_startup():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    init_db()


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/healthz")
def healthz():
    return {"status": "ok"}


# ── Auth routes ───────────────────────────────────────────────────────────────

@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request, sent: str = "", error: str = ""):
    return templates.TemplateResponse(
        request, "login.html", {"sent": sent, "error": error}
    )


@app.post("/login")
async def login_submit(request: Request, email: str = Form(...)):
    with db_connection() as conn:
        user = models.get_user_by_email(conn, email.strip().lower())

    if user:
        token = serializer.dumps(user["id"], salt="magic-link")
        base_url = str(request.base_url).rstrip("/")
        link = f"{base_url}/auth/{token}"
        await _send_magic_link(user["email"], link)

    # Don't reveal whether the email exists — always show the same message
    return RedirectResponse(url="/login?sent=1", status_code=303)


@app.get("/auth/{token}")
def auth_consume(token: str, request: Request):
    try:
        user_id = serializer.loads(token, salt="magic-link", max_age=900)
    except SignatureExpired:
        return RedirectResponse(url="/login?error=expired")
    except BadSignature:
        return RedirectResponse(url="/login?error=invalid")

    session_token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(days=7)

    with db_connection() as conn:
        models.create_session(conn, user_id, session_token, expires_at)

    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        "session",
        session_token,
        httponly=True,
        samesite="lax",
        max_age=7 * 24 * 3600,
    )
    return response


@app.post("/logout")
def logout(request: Request, user=Depends(current_user)):
    token = request.cookies.get("session", "")
    with db_connection() as conn:
        models.delete_session(conn, token)
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("session")
    return response


async def _send_magic_link(to_email: str, link: str):
    smtp_host = os.getenv("SMTP_HOST")
    if not smtp_host:
        print(f"\n[DEV] Magic link for {to_email}:\n  {link}\n", flush=True)
        return

    import aiosmtplib
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["From"] = os.getenv("SMTP_FROM", "noreply@bosshardmedical.com.au")
    msg["To"] = to_email
    msg["Subject"] = "Your Bosshard Medical login link"
    msg.set_content(f"Click to log in (expires in 15 minutes):\n\n{link}\n")

    await aiosmtplib.send(
        msg,
        hostname=smtp_host,
        port=int(os.getenv("SMTP_PORT", "587")),
        username=os.getenv("SMTP_USER"),
        password=os.getenv("SMTP_PASSWORD"),
        start_tls=True,
    )


# ── Invoice fragment for HTMX ─────────────────────────────────────────────────

@app.get("/invoice/fragment/line-row", response_class=HTMLResponse)
def line_row_fragment(request: Request, user=Depends(current_user)):
    return templates.TemplateResponse(request, "_line_row.html", {})


# ── List view ─────────────────────────────────────────────────────────────────

TAB_STATUSES: dict[str, list[str] | None] = {
    "open":     ["draft", "issued", "paid"],
    "all":      None,
    "paid":     ["paid"],
    "promoted": ["promoted"],
    "voided":   ["voided"],
}


@app.get("/", response_class=HTMLResponse)
def invoice_list(request: Request, tab: str = "open", user=Depends(current_user)):
    statuses = TAB_STATUSES.get(tab, TAB_STATUSES["open"])
    with db_connection() as conn:
        invoices = models.list_invoices(conn, statuses)
        for inv in invoices:
            lines = models.get_invoice_lines(conn, inv["id"])
            inv["totals"] = models.invoice_totals(lines)
    return templates.TemplateResponse(
        request, "invoice_list.html",
        {"invoices": invoices, "tab": tab, "user": user},
    )


# ── Create invoice ────────────────────────────────────────────────────────────

@app.get("/invoice/new", response_class=HTMLResponse)
def invoice_new_form(request: Request, user=Depends(current_user)):
    return templates.TemplateResponse(request, "invoice_new.html", {"user": user})


@app.post("/invoice")
async def invoice_create(request: Request, user=Depends(current_user)):
    form = await request.form()

    data = {
        "customer_name":    form.get("customer_name", "").strip(),
        "customer_email":   form.get("customer_email", "").strip(),
        "billing_address":  form.get("billing_address", "").strip(),
        "abn":              form.get("abn", "").strip(),
        "notes":            form.get("notes", "").strip(),
        "customer_notes":   form.get("customer_notes", "").strip(),
    }

    if not data["customer_name"]:
        raise HTTPException(400, "Customer name is required")

    descriptions  = form.getlist("description[]")
    quantities    = form.getlist("quantity[]")
    unit_prices   = form.getlist("unit_price_ex_gst[]")
    syrinx_ids    = form.getlist("syrinx_product_id[]")

    lines = []
    for i, desc in enumerate(descriptions):
        desc = desc.strip()
        if not desc:
            continue
        try:
            qty   = float(quantities[i])
            price = float(unit_prices[i])
        except (ValueError, IndexError):
            continue
        lines.append({
            "description":      desc,
            "quantity":         qty,
            "unit_price_ex_gst": price,
            "syrinx_product_id": syrinx_ids[i] if i < len(syrinx_ids) else "",
        })

    if not lines:
        raise HTTPException(400, "At least one line item is required")

    with db_connection() as conn:
        invoice_id = models.create_invoice(conn, data, lines, user["id"])

    return RedirectResponse(url=f"/invoice/{invoice_id}", status_code=303)


# ── Invoice detail ────────────────────────────────────────────────────────────

@app.get("/invoice/{invoice_id}", response_class=HTMLResponse)
def invoice_detail(invoice_id: int, request: Request, user=Depends(current_user)):
    with db_connection() as conn:
        invoice = models.get_invoice(conn, invoice_id)
        if not invoice:
            raise HTTPException(404, "Invoice not found")
        lines  = models.get_invoice_lines(conn, invoice_id)
        events = models.get_invoice_events(conn, invoice_id)
    totals = models.invoice_totals(lines)
    return templates.TemplateResponse(
        request, "invoice_detail.html",
        {"invoice": invoice, "lines": lines, "events": events, "totals": totals, "user": user},
    )


# ── Status transitions ────────────────────────────────────────────────────────

VALID_TRANSITIONS: dict[str, list[str]] = {
    "draft":  ["issued"],
    "issued": ["paid", "voided"],
    "paid":   ["promoted", "voided"],
}


def _assert_transition(invoice: dict, target: str):
    allowed = VALID_TRANSITIONS.get(invoice["status"], [])
    if target not in allowed:
        raise HTTPException(
            400,
            f"Cannot move invoice from '{invoice['status']}' to '{target}'",
        )


@app.post("/invoice/{invoice_id}/issue")
def invoice_issue(invoice_id: int, request: Request, user=Depends(current_user)):
    with db_connection() as conn:
        invoice = models.get_invoice(conn, invoice_id)
        if not invoice:
            raise HTTPException(404)
        _assert_transition(invoice, "issued")
        models.update_invoice_status(
            conn, invoice_id, "issued",
            issued_at=datetime.utcnow().isoformat(),
        )
        models.log_event(conn, invoice_id, user["id"], "issued")
    return RedirectResponse(url=f"/invoice/{invoice_id}", status_code=303)


@app.get("/invoice/{invoice_id}/pdf")
def invoice_pdf(invoice_id: int, request: Request, user=Depends(current_user)):
    with db_connection() as conn:
        invoice = models.get_invoice(conn, invoice_id)
        if not invoice:
            raise HTTPException(404)
        if invoice["status"] == "draft":
            raise HTTPException(400, "Issue the invoice before downloading the PDF")
        lines = models.get_invoice_lines(conn, invoice_id)
    totals = models.invoice_totals(lines)

    html = templates.TemplateResponse(
        request, "invoice_pdf.html",
        {"invoice": invoice, "lines": lines, "totals": totals, "header_label": INVOICE_HEADER_LABEL},
    ).body.decode()

    from weasyprint import HTML as WP
    pdf_bytes = WP(string=html, base_url=str(BASE_DIR / "static")).write_pdf()

    filename = f"{invoice['invoice_number']}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/invoice/{invoice_id}/mark-paid")
def invoice_mark_paid(invoice_id: int, request: Request, user=Depends(current_user)):
    with db_connection() as conn:
        invoice = models.get_invoice(conn, invoice_id)
        if not invoice:
            raise HTTPException(404)
        _assert_transition(invoice, "paid")
        models.update_invoice_status(
            conn, invoice_id, "paid",
            paid_at=datetime.utcnow().isoformat(),
        )
        models.log_event(conn, invoice_id, user["id"], "marked_paid")
    return RedirectResponse(url=f"/invoice/{invoice_id}", status_code=303)


@app.post("/invoice/{invoice_id}/promote")
def invoice_promote(invoice_id: int, request: Request, user=Depends(current_user)):
    with db_connection() as conn:
        invoice = models.get_invoice(conn, invoice_id)
        if not invoice:
            raise HTTPException(404)
        _assert_transition(invoice, "promoted")
        lines = models.get_invoice_lines(conn, invoice_id)
    return templates.TemplateResponse(
        request, "invoice_promote.html",
        {"invoice": invoice, "lines": lines, "user": user},
    )


@app.post("/invoice/{invoice_id}/promote-confirm")
async def invoice_promote_confirm(invoice_id: int, request: Request, user=Depends(current_user)):
    form = await request.form()
    syrinx_order_id = form.get("syrinx_order_id", "").strip()
    if not syrinx_order_id:
        raise HTTPException(400, "Syrinx order ID is required")

    with db_connection() as conn:
        invoice = models.get_invoice(conn, invoice_id)
        if not invoice:
            raise HTTPException(404)
        _assert_transition(invoice, "promoted")
        models.update_invoice_status(
            conn, invoice_id, "promoted",
            promoted_at=datetime.utcnow().isoformat(),
            promoted_syrinx_order_id=syrinx_order_id,
        )
        models.log_event(
            conn, invoice_id, user["id"], "promoted",
            {"syrinx_order_id": syrinx_order_id},
        )
    return RedirectResponse(url=f"/invoice/{invoice_id}", status_code=303)


@app.post("/invoice/{invoice_id}/void")
async def invoice_void(invoice_id: int, request: Request, user=Depends(current_user)):
    form = await request.form()
    reason = form.get("reason", "").strip()
    if not reason:
        raise HTTPException(400, "A reason is required to void an invoice")

    with db_connection() as conn:
        invoice = models.get_invoice(conn, invoice_id)
        if not invoice:
            raise HTTPException(404)
        _assert_transition(invoice, "voided")
        models.update_invoice_status(
            conn, invoice_id, "voided",
            voided_at=datetime.utcnow().isoformat(),
            voided_reason=reason,
        )
        models.log_event(conn, invoice_id, user["id"], "voided", {"reason": reason})
    return RedirectResponse(url=f"/invoice/{invoice_id}", status_code=303)


@app.get("/invoice/{invoice_id}/events", response_class=HTMLResponse)
def invoice_events_view(invoice_id: int, request: Request, user=Depends(current_user)):
    with db_connection() as conn:
        invoice = models.get_invoice(conn, invoice_id)
        if not invoice:
            raise HTTPException(404)
        events = models.get_invoice_events(conn, invoice_id)
    return templates.TemplateResponse(
        request, "invoice_events.html",
        {"invoice": invoice, "events": events, "user": user},
    )
