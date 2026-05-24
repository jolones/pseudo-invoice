# Bosshard Medical — Pseudo-Invoice Tool

See `../design/CLAUDE.md` for the full spec.

## Quick start

```bash
pip install -r requirements.txt

# macOS only: WeasyPrint needs Homebrew's Pango/GLib
brew install pango
DYLD_LIBRARY_PATH=/opt/homebrew/lib python3.12 -m uvicorn app.main:app --reload
```

App runs at http://localhost:8000. DB file is created at `db/invoices.db` on first run.

## Dev login

No SMTP config needed locally. When you submit the login form, the magic link
is printed to the terminal (look for `[DEV] Magic link:`). Copy and open it.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | `dev-secret-change-me` | Signs magic link tokens — **change for production** |
| `SMTP_HOST` | _(absent = dev mode)_ | Set to enable email sending |
| `SMTP_PORT` | `587` | |
| `SMTP_USER` | | |
| `SMTP_PASSWORD` | | |
| `SMTP_FROM` | | |
| `INVOICE_NUMBER_PREFIX` | `INT` | Prefix for invoice numbers (`INT-2025-0001`) |
| `INVOICE_HEADER_LABEL` | `Payment Request` | PDF header text |

## Deploying to Railway

1. Push the repo to GitHub (the `design/pseudo-invoice/` directory is the root).
2. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub repo → select the repo.
3. In the Railway dashboard, go to **Settings → Source** and set the **Root Directory** to `design/pseudo-invoice` if deploying from the monorepo.
4. Add a **Volume**: go to your service → **Volumes** → Add Volume → mount path `/app/db`. This keeps the SQLite DB alive across redeploys.
5. Set environment variables under **Variables**:

| Variable | Value |
|---|---|
| `SECRET_KEY` | Run `openssl rand -hex 32` locally and paste the result |
| `SMTP_HOST` | Your SMTP provider host |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | Your SMTP username |
| `SMTP_PASSWORD` | Your SMTP password |
| `SMTP_FROM` | `noreply@bosshardmedical.com.au` |

Railway auto-detects the `Dockerfile` and builds from it. Once deployed, Railway assigns a public URL (e.g. `https://pseudo-invoice-production.up.railway.app`).

> **Note:** `PORT` is injected automatically by Railway — the `CMD` in the Dockerfile already handles this.

## Deploying to Fly.io

```bash
fly launch
fly deploy
fly secrets set SECRET_KEY=$(openssl rand -hex 32)
fly secrets set SMTP_HOST=... SMTP_USER=... SMTP_PASSWORD=... SMTP_FROM=...
```

The SQLite DB file lives at `/app/db/invoices.db` inside the container. Mount a
persistent volume at `/app/db` before deploying to production.
