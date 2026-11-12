#!/bin/sh

set -eu

MIN_MAJOR=3
MIN_MINOR=10
VENV_DIR="${VENV_DIR:-.venv}"
REQ_FILE="requirements.txt"

info()  { printf '\033[1;34m[*]\033[0m %s\n' "$*"; }
ok()    { printf '\033[1;32m[+]\033[0m %s\n' "$*"; }
warn()  { printf '\033[1;33m[!]\033[0m %s\n' "$*" >&2; }
fail()  { printf '\033[1;31m[x]\033[0m %s\n' "$*" >&2; exit 1; }

usage() {
    cat <<EOF
Usage: ./install.sh [--dev]

  --dev       Install requirements-dev.txt (includes requirements.txt)
  -h, --help  Show this help

Environment variables:
  PYTHON=/path/to/python3   Use a specific interpreter
  VENV_DIR=.venv            Virtual environment directory
EOF
}

for arg in "$@"; do
    case "$arg" in
        --dev) REQ_FILE="requirements-dev.txt" ;;
        -h|--help) usage; exit 0 ;;
        *) fail "Unknown option: $arg (use --help)" ;;
    esac
done

cd "$(dirname "$0")"

[ -f "$REQ_FILE" ] || fail "$REQ_FILE not found in $(pwd)"

info "Looking for Python >= $MIN_MAJOR.$MIN_MINOR..."

PY=""
for candidate in ${PYTHON:-} python3 python3.14 python3.13 python3.12 python3.11 python3.10 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        if "$candidate" -c "import sys; sys.exit(0 if sys.version_info >= ($MIN_MAJOR, $MIN_MINOR) else 1)" 2>/dev/null; then
            PY="$(command -v "$candidate")"
            break
        else
            found="$("$candidate" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))' 2>/dev/null || echo '?')"
            warn "$candidate is version $found (need >= $MIN_MAJOR.$MIN_MINOR)"
        fi
    fi
done

if [ -z "$PY" ]; then
    fail "No Python >= $MIN_MAJOR.$MIN_MINOR found. Install it (macOS: brew install python) or set PYTHON=/path/to/python3"
fi

ok "Python: $PY ($("$PY" --version 2>&1))"

info "Checking pip..."
if "$PY" -m pip --version >/dev/null 2>&1; then
    ok "pip: $("$PY" -m pip --version)"
else
    warn "pip not found for $PY; trying ensurepip..."
    if "$PY" -m ensurepip --upgrade >/dev/null 2>&1; then
        ok "pip is ready"
    else
        fail "pip install failed (Debian/Ubuntu: sudo apt install python3-pip)"
    fi
fi

info "Checking venv module..."
"$PY" -c "import venv, ensurepip" >/dev/null 2>&1 || \
    fail "Python modules venv/ensurepip not available (Debian/Ubuntu: sudo apt install python3-venv)"
ok "venv ok"

if [ -x "$VENV_DIR/bin/python" ]; then
    ok "Using existing virtual enviro nment: $VENV_DIR"
else
    info "Creating virtual environment in $VENV_DIR..."
    "$PY" -m venv "$VENV_DIR" || fail "Could not create virtual environment"
    ok "Virtual environment created"
fi

VENV_PY="$VENV_DIR/bin/python"

info "Updating pip..."
"$VENV_PY" -m pip install --upgrade pip >/dev/null

info "Installing dependencies from $REQ_FILE..."
"$VENV_PY" -m pip install -r "$REQ_FILE"

info "Checking imports..."
"$VENV_PY" -c "import requests, psycopg2, reportlab, truststore" || \
    fail "Some dependencies failed to import"
ok "Done"
