#!/usr/bin/env bash
# Build the bundled Cachet desktop app on macOS/Linux. Produces dist/Cachet
# (a single double-click-able file). Run from anywhere:
#   bash packaging/build.sh
#
# Windows uses packaging/build.bat. Cross-compiling is not possible (PyInstaller
# builds for the OS it runs on), so the Windows .exe must be built on Windows
# (build.bat) or by the GitHub Actions workflow (.github/workflows/cachet-package.yml).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[1/3] Building the Cachet frontend (build:cachet) ..."
corepack pnpm --dir frontend install --frozen-lockfile
corepack pnpm --dir frontend build:cachet

echo "[2/3] Creating a clean build venv with core deps only ..."
PYBASE="${CACHET_BUILD_PYTHON:-python3}"
"$PYBASE" -m venv .venv-package
.venv-package/bin/pip install --quiet --upgrade pip
.venv-package/bin/pip install --quiet -r packaging/requirements-package.txt

echo "[3/3] Freezing with PyInstaller ..."
.venv-package/bin/pyinstaller --clean --noconfirm packaging/cachet.spec

echo ""
echo "Done. Built: $ROOT/dist/Cachet"
echo "Run it to launch Cachet in your browser (it opens automatically)."
