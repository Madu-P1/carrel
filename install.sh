#!/usr/bin/env bash
# Carrel beta installer.
#
# Two ways to run:
#
#   1. Already cloned the repo:
#      cd carrel && ./install.sh
#
#   2. Don't have it yet (this clones, then installs):
#      curl -fsSL https://raw.githubusercontent.com/Madu-P1/carrel/main/install.sh | bash
#
# What it does:
#   - Checks macOS + Xcode CLI tools.
#   - Installs `uv` (Astral) if missing — uv brings its own standalone
#     Python so the user does not need brew or system Python.
#   - Creates .venv with Python 3.12 and installs requirements.txt.
#   - Installs `bun` if missing.
#   - Copies .env.example to .env and prompts for ANTHROPIC_API_KEY
#     (if running interactively).
#   - Runs ./script/build_and_run.sh to build the Swift shell, build
#     the Vite frontend, start FastAPI, and launch the .app.
#
# Idempotent: re-running detects already-done steps and skips.

set -euo pipefail

REPO_URL="https://github.com/Madu-P1/carrel.git"
REPO_DIRNAME="carrel"
REQUIRED_PY="3.12"
MIN_MACOS_MAJOR=14

# ──────────────────────────────────────────────────────────────────
# Output helpers (no em dashes in user-visible copy per voice rules)
# ──────────────────────────────────────────────────────────────────

if [[ -t 1 ]]; then
  C_RESET='\033[0m'
  C_BOLD='\033[1m'
  C_DIM='\033[2m'
  C_GREEN='\033[32m'
  C_YELLOW='\033[33m'
  C_RED='\033[31m'
  C_BLUE='\033[34m'
else
  C_RESET=''; C_BOLD=''; C_DIM=''
  C_GREEN=''; C_YELLOW=''; C_RED=''; C_BLUE=''
fi

step() { printf "\n${C_BOLD}${C_BLUE}==>${C_RESET} ${C_BOLD}%s${C_RESET}\n" "$*"; }
ok()   { printf "    ${C_GREEN}ok${C_RESET} %s\n" "$*"; }
warn() { printf "    ${C_YELLOW}warn${C_RESET} %s\n" "$*"; }
fail() { printf "\n${C_RED}${C_BOLD}error${C_RESET} %s\n" "$*"; exit 1; }
note() { printf "    ${C_DIM}%s${C_RESET}\n" "$*"; }

is_interactive() { [[ -t 0 ]]; }

# ──────────────────────────────────────────────────────────────────
# 1. Sanity checks
# ──────────────────────────────────────────────────────────────────

step "Checking macOS"

if [[ "$(uname -s)" != "Darwin" ]]; then
  fail "Carrel runs on macOS only. Your system reports $(uname -s)."
fi

macos_version="$(sw_vers -productVersion)"
macos_major="${macos_version%%.*}"
if (( macos_major < MIN_MACOS_MAJOR )); then
  warn "macOS $macos_version detected. Carrel targets macOS $MIN_MACOS_MAJOR+. Build may fail."
else
  ok "macOS $macos_version"
fi

if xcode-select -p >/dev/null 2>&1; then
  ok "Xcode Command Line Tools installed at $(xcode-select -p)"
else
  warn "Xcode Command Line Tools not found."
  echo
  echo "    macOS will open an installer dialog. Click 'Install', wait for"
  echo "    it to finish (a few minutes), then re-run this script."
  echo
  xcode-select --install || true
  exit 1
fi

# ──────────────────────────────────────────────────────────────────
# 2. Resolve where the repo lives
# ──────────────────────────────────────────────────────────────────

step "Locating Carrel repo"

if [[ -f "main.py" && -d "macos-app" && -f "script/build_and_run.sh" ]]; then
  REPO_DIR="$(pwd)"
  ok "Already inside a Carrel checkout: $REPO_DIR"
else
  if ! command -v git >/dev/null 2>&1; then
    fail "git not found. Install Xcode CLI tools first (see step above)."
  fi
  if [[ -d "$REPO_DIRNAME/.git" ]]; then
    note "$REPO_DIRNAME/ already exists, fetching latest"
    git -C "$REPO_DIRNAME" fetch --quiet origin main
    git -C "$REPO_DIRNAME" checkout --quiet main
    git -C "$REPO_DIRNAME" pull --quiet --ff-only origin main
  else
    note "Cloning $REPO_URL"
    git clone --quiet "$REPO_URL" "$REPO_DIRNAME"
  fi
  REPO_DIR="$(pwd)/$REPO_DIRNAME"
  ok "Repo at $REPO_DIR"
fi

cd "$REPO_DIR"

# ──────────────────────────────────────────────────────────────────
# 3. Install uv (Astral) — manages standalone Python without brew
# ──────────────────────────────────────────────────────────────────

step "Setting up Python via uv"

if ! command -v uv >/dev/null 2>&1; then
  # uv installs to ~/.local/bin (or ~/.cargo/bin on some setups). Add
  # both to PATH for the rest of this script so we can call `uv` even
  # if the user has not sourced their shell rc.
  note "Installing uv"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
  if ! command -v uv >/dev/null 2>&1; then
    fail "uv installer succeeded but uv is not on PATH. Open a new terminal and re-run."
  fi
fi
ok "uv $(uv --version | awk '{print $2}')"

if [[ ! -d ".venv" ]]; then
  note "Creating .venv with Python $REQUIRED_PY"
  uv venv .venv --python "$REQUIRED_PY" --quiet
else
  ok "Reusing existing .venv"
fi

# ──────────────────────────────────────────────────────────────────
# 4. Install Python deps into the venv
# ──────────────────────────────────────────────────────────────────

step "Installing Python dependencies"

# uv pip is the same surface as pip but ~10x faster. The first install
# pulls ~600 MB of wheels (fastembed + docling + torch transitives are
# the bulk). Subsequent runs are near-instant.
uv pip install --python .venv/bin/python --quiet -r requirements.txt
ok "requirements.txt installed"

# ──────────────────────────────────────────────────────────────────
# 5. Install bun (or fall back to existing JS runner)
# ──────────────────────────────────────────────────────────────────

step "Setting up the JS runtime"

if command -v bun >/dev/null 2>&1; then
  ok "bun $(bun --version) already installed"
elif command -v pnpm >/dev/null 2>&1; then
  ok "pnpm $(pnpm --version) detected (build_and_run.sh will use it)"
elif command -v npm >/dev/null 2>&1; then
  ok "npm $(npm --version) detected (build_and_run.sh will use it)"
else
  note "Installing bun"
  curl -fsSL https://bun.sh/install | bash >/dev/null
  export PATH="$HOME/.bun/bin:$PATH"
  if ! command -v bun >/dev/null 2>&1; then
    fail "bun installer succeeded but bun is not on PATH. Open a new terminal and re-run."
  fi
  ok "bun $(bun --version) installed"
fi

# ──────────────────────────────────────────────────────────────────
# 6. .env setup
# ──────────────────────────────────────────────────────────────────

step "Configuring .env"

if [[ ! -f ".env" ]]; then
  cp .env.example .env
  ok "Wrote .env from .env.example"
fi

current_key="$(grep -E '^ANTHROPIC_API_KEY=' .env | cut -d= -f2- || true)"
needs_provider_setup=false
if [[ -z "$current_key" ]]; then
  current_provider="$(grep -E '^EINSTEIN_AI_PROVIDER=' .env | cut -d= -f2- || true)"
  if [[ "$current_provider" != "ollama" && "$current_provider" != "off" ]]; then
    needs_provider_setup=true
  fi
fi

if [[ "$needs_provider_setup" == "true" ]]; then
  if is_interactive; then
    echo
    echo "Carrel needs an LLM provider. Two options:"
    echo "  1. Anthropic Claude (paste an API key from console.anthropic.com)"
    echo "  2. Local Ollama (set EINSTEIN_AI_PROVIDER=ollama and run 'ollama serve')"
    echo
    printf "Paste your Anthropic API key (or press Enter to skip and use Ollama): "
    read -r -s entered_key < /dev/tty || entered_key=""
    echo
    if [[ -n "$entered_key" ]]; then
      # Replace the empty ANTHROPIC_API_KEY line in .env
      python3 - "$entered_key" <<'PY'
import os, sys, re
key = sys.argv[1]
path = ".env"
with open(path) as f: text = f.read()
text = re.sub(r"^ANTHROPIC_API_KEY=.*$",
              f"ANTHROPIC_API_KEY={key}",
              text, count=1, flags=re.MULTILINE)
with open(path, "w") as f: f.write(text)
PY
      ok "Anthropic API key written to .env"
    else
      python3 - <<'PY'
import re
path = ".env"
with open(path) as f: text = f.read()
text = re.sub(r"^EINSTEIN_AI_PROVIDER=.*$",
              "EINSTEIN_AI_PROVIDER=ollama",
              text, count=1, flags=re.MULTILINE)
with open(path, "w") as f: f.write(text)
PY
      ok "Set EINSTEIN_AI_PROVIDER=ollama in .env"
      warn "Start Ollama with 'ollama serve' before launching Carrel, or the tutor will refuse every question."
    fi
  else
    warn "Running non-interactively (curl | bash). Edit .env manually before launching:"
    note "  open -a TextEdit $REPO_DIR/.env"
    note "  Either fill ANTHROPIC_API_KEY=... or set EINSTEIN_AI_PROVIDER=ollama"
    SKIP_LAUNCH=true
  fi
else
  ok ".env already configured"
fi

# ──────────────────────────────────────────────────────────────────
# 7. Build + launch (skipped if .env still needs setup)
# ──────────────────────────────────────────────────────────────────

if [[ "${SKIP_LAUNCH:-false}" == "true" ]]; then
  step "Install complete (launch deferred)"
  echo
  echo "    Edit .env to set up your LLM provider, then run:"
  echo "        cd $REPO_DIR && ./script/build_and_run.sh"
  exit 0
fi

step "Building and launching Carrel"
note "First build: ~1 min (Swift + Vite + uvicorn boot + fastembed model download)."
note "Subsequent launches: ~1 sec."

# Hand off. build_and_run.sh handles the rest: regenerate icon if
# changed, build the Swift shell, build the Vite bundle, start uvicorn,
# launch the .app. From here, console output belongs to the launcher.
exec ./script/build_and_run.sh
