#!/usr/bin/env bash
# VerdantME — macOS / Linux setup
# Run from the repo root: bash setup/setup.sh
set -euo pipefail

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # no colour

ok()   { echo -e "  ${GREEN}✓${NC} $*"; }
warn() { echo -e "  ${YELLOW}!${NC} $*"; }
fail() { echo -e "  ${RED}✗${NC} $*"; exit 1; }
step() { echo -e "\n${BOLD}$*${NC}"; }

# ── Resolve repo root (works regardless of CWD) ─────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

echo -e "\n${BOLD}VerdantME setup${NC}"
echo "────────────────────────────────────"

# ── 1. Check Python ──────────────────────────────────────────────────────────
step "1. Checking Python"

PYTHON=""
for cmd in python3 python; do
  if command -v "$cmd" &>/dev/null; then
    VER=$("$cmd" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    MAJOR=$(echo "$VER" | cut -d. -f1)
    MINOR=$(echo "$VER" | cut -d. -f2)
    if [ "$MAJOR" -eq 3 ] && [ "$MINOR" -ge 10 ]; then
      PYTHON="$cmd"
      ok "Found Python $VER ($cmd)"
      break
    fi
  fi
done

if [ -z "$PYTHON" ]; then
  fail "Python 3.10+ not found. Install it from https://python.org or via pyenv/Homebrew.\n     See setup/README.md for details."
fi

# ── 2. Create virtual environment ───────────────────────────────────────────
step "2. Virtual environment"

if [ -d ".venv" ]; then
  ok ".venv already exists — skipping creation"
else
  "$PYTHON" -m venv .venv
  ok "Created .venv"
fi

PIP=".venv/bin/pip"
JOBFINDER=".venv/bin/jobfinder"

# ── 3. Install dependencies ──────────────────────────────────────────────────
step "3. Installing dependencies"

"$PIP" install --quiet --upgrade pip
"$PIP" install --quiet -e .
ok "Installed jobfinder and all dependencies"

# ── 4. Config file ───────────────────────────────────────────────────────────
step "4. Config file"

if [ -f "config.json" ]; then
  ok "config.json already exists — skipping"
else
  cp config.example.json config.json
  ok "Created config.json from example (edit it to customise filters)"
fi

# ── 5. .env file ─────────────────────────────────────────────────────────────
step "5. API key file"

if [ -f ".env" ]; then
  ok ".env already exists — skipping"
else
  cp .env.example .env
  warn "Created .env — add your API key before running"
fi

# ── Done ─────────────────────────────────────────────────────────────────────
echo -e "\n────────────────────────────────────"
echo -e "${BOLD}${GREEN}Setup complete!${NC}\n"
echo -e "Next steps:\n"
echo -e "  1. Open ${BOLD}.env${NC} and add your API key"
echo -e "     Anthropic: https://console.anthropic.com"
echo -e "     Gemini:    https://aistudio.google.com (free tier available)\n"
echo -e "  2. Start the app:"
echo -e "     ${BOLD}source .venv/bin/activate${NC}"
echo -e "     ${BOLD}jobfinder serve${NC}\n"
echo -e "  3. Open ${BOLD}http://localhost:8000${NC} in your browser\n"
echo -e "Need help? See ${BOLD}setup/README.md${NC}"
echo ""
