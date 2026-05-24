# Pseudo-Invoice Tool

A small internal web app for issuing interim invoices and tracking them through to payment.

## Running locally

```bash
pip install -r requirements.txt

# macOS only: WeasyPrint needs Homebrew's Pango/GLib
brew install pango
DYLD_LIBRARY_PATH=/opt/homebrew/lib python3.12 -m uvicorn app.main:app --reload
```

Open http://localhost:8000. The database is created automatically on first run.

**First time:** you'll be prompted to set a shared team password. After that, anyone logs in with their name and that password.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `APP_NAME` | `Interim Invoice Tool` | Display name shown throughout the UI |
| `INVOICE_NUMBER_PREFIX` | `INT` | Prefix for invoice numbers (`INT-2025-0001`) |
| `INVOICE_HEADER_LABEL` | `Payment Request` | Header text on the PDF |

## Deploying to Railway

1. Push this repo to GitHub.
2. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub repo.
3. Add a **Volume** → mount path `/app/db`. This keeps the database alive across redeploys.
4. Set environment variables under **Variables**:

| Variable | Value |
|---|---|
| `APP_NAME` | Your product or company name |

Once deployed, open the Railway URL and you'll be walked through first-time setup.
