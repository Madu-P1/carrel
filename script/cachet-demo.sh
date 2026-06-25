#!/usr/bin/env bash
# Launch Cachet for the Wedge-2 contract demo against an ISOLATED, clean database.
#
# Why a separate data dir: the deterministic contract close scopes to every
# `ready` document. The real library (data/einstein_tutor.db) holds many ready
# docs (study PDFs, prior uploads) that would join the comparison and surface the
# wrong clause. This points Cachet at a dedicated demo DB so the only ready doc is
# the one you upload on stage.
#
# Usage:
#   bash script/cachet-demo.sh           # launch (keeps any doc already uploaded)
#   bash script/cachet-demo.sh --reset   # wipe the demo DB first (fresh upload theater)
#
# serve-cachet.py sets CACHET_DETERMINISTIC_VERIFY=1, EMBED_ON_INGEST=false,
# COURTLISTENER_API_TOKEN=local and serves UI+API same-origin on 127.0.0.1:8000.

set -euo pipefail
cd "$(dirname "$0")/.."

DEMO_DATA_DIR="${CACHET_DEMO_DATA_DIR:-$PWD/data-cachet-demo}"

if [[ "${1:-}" == "--reset" ]]; then
  echo "Resetting demo DB at $DEMO_DATA_DIR"
  rm -rf "$DEMO_DATA_DIR"
fi
mkdir -p "$DEMO_DATA_DIR/uploads"

export EINSTEIN_DATA_DIR="$DEMO_DATA_DIR"
echo "Cachet demo data dir: $EINSTEIN_DATA_DIR"
exec ./.venv/bin/python script/serve-cachet.py
