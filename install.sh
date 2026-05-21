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

# ──────────────────────────────────────────────────────────────────
# 1b. Detect Apple Foundation Models eligibility
# ──────────────────────────────────────────────────────────────────
# AFM is the on-device LLM that ships with macOS 26+ on Apple Silicon,
# gated on Apple Intelligence being enabled and the primary locale
# being English (US). When eligible, fresh installs land on AFM by
# default (EINSTEIN_AI_PROVIDER stays "auto" in .env, which
# ai/providers.py:304-342 resolves to AFM when _afm_available()
# returns true). When not eligible, install falls through to Ollama
# exactly as before. Runtime is already fail-closed: AFMClient returns
# error_code="apple_intelligence_not_enabled" when AI is disabled, and
# the UI deep-links to System Settings rather than silently failing.

step "Checking Apple Foundation Models eligibility"

mac_arch="$(uname -m)"
mac_locale="$(defaults read NSGlobalDomain AppleLocale 2>/dev/null || echo "")"

AFM_ELIGIBLE=false
AFM_REASON=""

if [[ "$mac_arch" != "arm64" ]]; then
  AFM_REASON="non-Apple-Silicon Mac ($mac_arch)"
elif (( macos_major < 26 )); then
  AFM_REASON="macOS $macos_version (need 26+)"
elif [[ ! "$mac_locale" =~ ^en[_-]US ]]; then
  AFM_REASON="locale is '$mac_locale' (need en_US: open System Settings, General, Language & Region, then set Primary Language to English (US))"
elif [[ "$(xcode-select -p 2>/dev/null || echo CommandLineTools)" == *"CommandLineTools"* ]]; then
  # Apple Foundation Models needs the @Generable / @Guide macros, whose
  # compiler plugin ships only inside full Xcode, not the Command Line
  # Tools. Without it the AFM bridge cannot be built, so do not route
  # this Mac to AFM; it installs and runs fine on Claude or Ollama.
  AFM_REASON="only the Command Line Tools are installed, not full Xcode. The Apple Intelligence build needs the FoundationModels macros from Xcode 26+ (free in the App Store). Install it, run 'sudo xcode-select -s /Applications/Xcode.app', then re-run this script to enable on-device AI."
else
  AFM_ELIGIBLE=true
fi

if [[ "$AFM_ELIGIBLE" == "true" ]]; then
  ok "Apple Silicon + macOS $macos_version + locale '$mac_locale' detected. Apple Foundation Models supported."
  note "After install, make sure Apple Intelligence is enabled in System Settings, Apple Intelligence & Siri."
  note "First-time enable triggers a 1 to 30 minute model download from Apple's CDN; this is normal."
else
  note "Apple Foundation Models unavailable: $AFM_REASON"
  note "Carrel will fall back to Ollama (install separately from https://ollama.com) unless you provide an Anthropic API key."
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

step "Setting up pnpm"

# Why pnpm and not bun: the project's package.json declares
# `packageManager: pnpm@9.12.0` and CI runs pnpm, so pnpm is the
# canonical choice. pnpm-standalone has a single-curl installer that
# bundles its own Node, so a fresh Mac with no Homebrew works.
#
# If bun or npm are already on PATH we still respect them (build_and_run.sh
# falls back through the chain), but the default install path is pnpm.

if command -v pnpm >/dev/null 2>&1; then
  ok "pnpm $(pnpm --version) already installed"
elif command -v bun >/dev/null 2>&1; then
  ok "bun $(bun --version) detected (build_and_run.sh will use it as fallback)"
elif command -v npm >/dev/null 2>&1; then
  ok "npm $(npm --version) detected (build_and_run.sh will use it as fallback)"
else
  note "Installing pnpm (standalone, bundles Node)"
  # Download to a temp file rather than piping curl to sh; some
  # shells truncate the pipe on macOS Sonoma+.
  installer="$(mktemp -t pnpm-install)"
  curl -fsSL https://get.pnpm.io/install.sh -o "$installer"
  bash "$installer" >/dev/null
  rm -f "$installer"
  # macOS standalone install puts pnpm under ~/Library/pnpm/bin.
  # On Linux the same installer uses ~/.local/share/pnpm, which we add
  # too as a belt-and-suspenders so this script keeps working if the
  # default ever shifts.
  export PNPM_HOME="$HOME/Library/pnpm"
  export PATH="$PNPM_HOME/bin:$HOME/.local/share/pnpm:$PATH"
  if ! command -v pnpm >/dev/null 2>&1; then
    fail "pnpm installer succeeded but pnpm is not on PATH. Open a new terminal and re-run."
  fi
  ok "pnpm $(pnpm --version) installed"
fi

# Make sure Node is on PATH. pnpm-standalone installs only pnpm itself;
# the build script invokes `node` and `tsc` (which exec node) directly,
# so pnpm-without-Node fails at first build. `pnpm env use --global lts`
# pulls a Node into PNPM_HOME/bin where it's reachable for the rest of
# this script and any future shell that has PNPM_HOME on PATH (set by
# the pnpm installer's shell-rc edits).
if ! command -v node >/dev/null 2>&1; then
  note "Installing Node (LTS) via pnpm"
  pnpm env use --global lts >/dev/null
  if ! command -v node >/dev/null 2>&1; then
    fail "pnpm env reported success but node is not on PATH."
  fi
  ok "node $(node --version) installed via pnpm"
fi

# ──────────────────────────────────────────────────────────────────
# 6. .env setup
# ──────────────────────────────────────────────────────────────────

step "Configuring .env"

if [[ ! -f ".env" ]]; then
  cp .env.example .env
  ok "Wrote .env from .env.example"
fi

# Pre-fill from the inherited environment so the one-paste form works:
#
#   curl -fsSL .../install.sh | ANTHROPIC_API_KEY=sk-ant-... bash
#
# When the env var is set, we write it straight to .env and skip the
# interactive prompt + the SKIP_LAUNCH defer. The friend ends up at a
# running app with no manual editing.
#
# Only act on env-vars that were explicitly passed in by the caller —
# if neither is set, fall through to the existing prompt-or-skip logic
# so a re-run preserves whatever is already in .env.
ENV_API_KEY="${ANTHROPIC_API_KEY:-}"
ENV_AI_PROVIDER="${EINSTEIN_AI_PROVIDER:-}"

if [[ -n "$ENV_API_KEY" ]]; then
  python3 - "$ENV_API_KEY" <<'PY'
import sys, re
key = sys.argv[1]
path = ".env"
with open(path) as f: text = f.read()
text = re.sub(r"^ANTHROPIC_API_KEY=.*$",
              f"ANTHROPIC_API_KEY={key}",
              text, count=1, flags=re.MULTILINE)
with open(path, "w") as f: f.write(text)
PY
  ok "ANTHROPIC_API_KEY taken from environment, written to .env"
  needs_provider_setup=false
elif [[ "$ENV_AI_PROVIDER" == "ollama" ]]; then
  python3 - <<'PY'
import re
path = ".env"
with open(path) as f: text = f.read()
text = re.sub(r"^EINSTEIN_AI_PROVIDER=.*$",
              "EINSTEIN_AI_PROVIDER=ollama",
              text, count=1, flags=re.MULTILINE)
with open(path, "w") as f: f.write(text)
PY
  ok "EINSTEIN_AI_PROVIDER=ollama taken from environment, written to .env"
  warn "Make sure 'ollama serve' is running before launching, or the tutor will refuse every question."
  needs_provider_setup=false
else
  current_key="$(grep -E '^ANTHROPIC_API_KEY=' .env | cut -d= -f2- || true)"
  needs_provider_setup=false
  if [[ -z "$current_key" ]]; then
    current_provider="$(grep -E '^EINSTEIN_AI_PROVIDER=' .env | cut -d= -f2- || true)"
    if [[ "$current_provider" != "ollama" && "$current_provider" != "off" ]]; then
      needs_provider_setup=true
    fi
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
    elif [[ "$AFM_ELIGIBLE" == "true" ]]; then
      # User pressed Enter on an eligible Mac. Leave the .env default
      # (EINSTEIN_AI_PROVIDER=auto from .env.example) in place; runtime
      # auto-resolution in ai/providers.py:304-342 will pick AFM via
      # _afm_available(). The AFM client backs grounded answers with
      # Apple's @Generable constrained decoding (ai/afm_grounded.py),
      # so structured output works without the legacy nested-claims
      # tool schema in services/tutor.py.
      ok "Leaving EINSTEIN_AI_PROVIDER=auto. Runtime will resolve to Apple Foundation Models."
      note "Carrel runs entirely on-device; no API key needed. The first grounded answer may take 1 to 10 seconds while Apple Intelligence warms the model."
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
      ok "Set EINSTEIN_AI_PROVIDER=ollama in .env (AFM unavailable: $AFM_REASON)"
      warn "Start Ollama with 'ollama serve' before launching Carrel, or the tutor will refuse every question."
    fi
  elif [[ "$AFM_ELIGIBLE" == "true" ]]; then
    # Non-interactive (curl | bash) on an eligible Mac: leave the
    # .env default (auto) in place and let build_and_run.sh launch.
    # AFM resolves at runtime; if Apple Intelligence is disabled, the
    # UI surfaces the System Settings deep-link rather than failing
    # silently.
    ok "Running non-interactively. Leaving EINSTEIN_AI_PROVIDER=auto. Runtime will resolve to Apple Foundation Models."
    note "Add an Anthropic API key to .env at $REPO_DIR/.env later if you want the paid Claude tier."
  else
    warn "Running non-interactively (curl | bash). Edit .env manually before launching:"
    note "  open -a TextEdit $REPO_DIR/.env"
    note "  Either fill ANTHROPIC_API_KEY=... or set EINSTEIN_AI_PROVIDER=ollama (AFM unavailable: $AFM_REASON)"
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
