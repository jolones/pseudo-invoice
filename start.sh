#!/usr/bin/env bash
set -e

# ── Find Python 3.12 ──────────────────────────────────────────────────────────
PYTHON=""
for candidate in python3.12 python3.11 python3.10 python3; do
  if command -v "$candidate" &>/dev/null; then
    version=$("$candidate" -c "import sys; print(sys.version_info >= (3,10))" 2>/dev/null)
    if [ "$version" = "True" ]; then
      PYTHON="$candidate"
      break
    fi
  fi
done

if [ -z "$PYTHON" ]; then
  echo "Error: Python 3.10+ not found. Install it from https://python.org and try again."
  exit 1
fi

# ── Install Python dependencies ───────────────────────────────────────────────
echo "Checking dependencies..."
$PYTHON -m pip install -q -r requirements.txt

# ── macOS: ensure WeasyPrint system libraries are available ───────────────────
if [[ "$OSTYPE" == "darwin"* ]]; then
  if ! command -v brew &>/dev/null; then
    echo "Error: Homebrew is required on macOS. Install it from https://brew.sh and try again."
    exit 1
  fi
  if ! brew list pango &>/dev/null 2>&1; then
    echo "Installing pango (required for PDF generation)..."
    brew install pango
  fi
  export DYLD_LIBRARY_PATH="/opt/homebrew/lib:${DYLD_LIBRARY_PATH:-}"
fi

# ── Open browser after a short delay ─────────────────────────────────────────
(sleep 2 && open "http://localhost:8000" 2>/dev/null || true) &

# ── Start the server ──────────────────────────────────────────────────────────
echo ""
echo "Starting server at http://localhost:8000"
echo "Press Ctrl+C to stop."
echo ""
$PYTHON -m uvicorn app.main:app --reload
