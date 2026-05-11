# AFM Integration — Runbook to Ship

**Date created:** 2026-05-10
**State at creation:** AFM Pass 1 (Phases 1+2+3 of the AFM integration plan) is applied to `/Users/madu/Desktop/Codex` and verified working on this Mac (macOS 26.4.1, M-series, en_US primary). Real generation returns ok=true via the bridge and via the Python `AFMClient`.

This runbook lists the exact commands needed to take Pass 1 from "working on dev machine" to "merged on main + shipped." Each step is independently runnable. If something breaks mid-way, you can resume from the failed step.

---

## 0. Verify AFM still works (sanity check before each session)

```bash
cd /Users/madu/Desktop/Codex
echo '{"kind":"request_text","request_id":"sanity","system":"Reply in one short sentence.","prompt":"What is mitosis?","max_tokens":64}' \
  | macos-app/.build/debug/EinsteinAFMBridge | jq .
```

Expected: `ok: true`, `text: "..."` containing a real one-sentence answer about mitosis. Latency ~700ms warm, ~5s cold.

If `model_not_ready` returns: Apple is still downloading model variants. Wait 5-15 min and retry.
If `apple_intelligence_not_enabled` returns: confirm `defaults read NSGlobalDomain AppleLocale` returns `en_US` and that the master Apple Intelligence toggle is on in System Settings → Apple Intelligence & Siri.

---

## 1. Save Pass 1 to its own branch (15 min)

You're currently on `feat/flashcards-focus-2026-05-09` with both flashcard work + AFM Pass 1 in your working tree. Separate them so AFM ships independently.

```bash
cd /Users/madu/Desktop/Codex

# Stash flashcard work (M and A files unrelated to AFM)
git stash push -u -m "wip flashcard work pre-AFM" -- \
  frontend/src/features/study/StudyView.module.css \
  frontend/src/features/study/StudyView.tsx \
  frontend/src/features/study/components/FlashcardFace.module.css \
  frontend/src/features/study/components/FlashcardFace.tsx \
  frontend/src/features/study/components/FlipCard.module.css \
  frontend/tests/study/flashcard-face.test.tsx \
  script/build_and_run.sh

# Branch off main for AFM
git checkout -b feat/afm-integration-2026-05-10 main

# Stage the 8 AFM files
git add \
  ai/afm_client.py \
  ai/native_bridge_paths.py \
  ai/providers.py \
  macos-app/Package.swift \
  macos-app/Sources/EinsteinAFMBridge/main.swift \
  services/extraction/utils.py \
  tests/test_afm_client.py \
  tests/test_ai_providers.py \
  docs/plans/afm-integration-2026-05-10.md \
  docs/plans/afm-runbook-2026-05-10.md

# Commit Pass 1
git commit -m "$(cat <<'EOF'
feat(ai): Apple Foundation Models provider via EinsteinAFMBridge

Adds AFMClient implementing AIProvider Protocol, talking to a new
EinsteinAFMBridge Swift sidecar over stdin/stdout JSON.

* macos-app/Sources/EinsteinAFMBridge: new Swift target wrapping
  Apple's FoundationModels framework. macOS 26+ Apple Silicon only.
* ai/afm_client.py: Python provider, mirrors OllamaClient shape.
  request_json + request_tool_call use system-prompt enforcement +
  post-hoc rescue parse, since FoundationModels has no runtime
  guided-generation API as of macOS 26.
* ai/native_bridge_paths.py: shared candidate-walk for both bridges
  (ingestion + AFM), supports CARREL_BUNDLE_MACOS env override for
  production .app layout.
* select_provider auto path: Claude → AFM → Ollama → Null.
* tests/test_afm_client.py: 20 unit tests covering happy path,
  bridge errors, JSON rescue, tool preamble, env config.

Verified on macOS 26.4.1 / Apple Silicon: real generation returns
ok=true, ~700ms warm latency, ~5s cold start.

Plan: docs/plans/afm-integration-2026-05-10.md (Phases 1+2+3 of 9)
Runbook: docs/plans/afm-runbook-2026-05-10.md
EOF
)"

# Restore flashcard work onto your previous branch
git checkout feat/flashcards-focus-2026-05-09
git stash pop
```

---

## 2. Phase 5 — build pipeline + production binary discovery (~2-3 hr)

**Goal:** `swift build` produces all 3 targets including AFMBridge. Production .app bundle includes the AFMBridge binary. Python finds it via `CARREL_BUNDLE_MACOS` env.

### 2.1 Update `script/build_and_run.sh`

Find the existing `swift build` invocation. Either:
- If it's already `swift build` (no `--product`): no change needed (default builds all targets).
- If it specifies `--product EinsteinDesktop`: change to build all three:

```bash
( cd macos-app && swift build --product EinsteinDesktop --product EinsteinIngestionBridge --product EinsteinAFMBridge )
```

### 2.2 Update `script/package_public_beta.sh`

Find the section that copies `EinsteinIngestionBridge` into the .app bundle. Add the AFM bridge alongside:

```bash
# Existing:
cp "$BUILD_DIR/EinsteinIngestionBridge" "$APP_BUNDLE/Contents/MacOS/EinsteinIngestionBridge"
# Add:
cp "$BUILD_DIR/EinsteinAFMBridge" "$APP_BUNDLE/Contents/MacOS/EinsteinAFMBridge"
```

Same for the `dist/` copy:
```bash
cp "$BUILD_DIR/EinsteinAFMBridge" "dist/EinsteinAFMBridge"
```

### 2.3 Update `macos-app/Sources/EinsteinDesktopApp/BackendSupervisor.swift`

Find where `proc.environment` is set when spawning uvicorn. Add `CARREL_BUNDLE_MACOS` so Python's `ai/native_bridge_paths.py` finds the bundled binary:

```swift
proc.environment = (proc.environment ?? [:]).merging([
    "CARREL_BUNDLE_MACOS": Bundle.main.bundleURL
        .appendingPathComponent("Contents/MacOS").path
]) { _, new in new }
```

If `proc.environment` is unset entirely, set it:
```swift
proc.environment = [
    "CARREL_BUNDLE_MACOS": Bundle.main.bundleURL
        .appendingPathComponent("Contents/MacOS").path,
    // ... any other env vars the existing code sets ...
]
```

### 2.4 Verify

```bash
cd /Users/madu/Desktop/Codex/macos-app && swift build
ls .build/debug/EinsteinAFMBridge .build/debug/EinsteinIngestionBridge .build/debug/EinsteinDesktop

# After packaging:
./script/package_public_beta.sh  # or the existing build pipeline
find dist/EinsteinDesktop.app -name "EinsteinAFMBridge"
# Should print: dist/EinsteinDesktop.app/Contents/MacOS/EinsteinAFMBridge
```

### 2.5 Commit

```bash
git checkout feat/afm-integration-2026-05-10
git add script/build_and_run.sh script/package_public_beta.sh \
        macos-app/Sources/EinsteinDesktopApp/BackendSupervisor.swift
git commit -m "feat(ai): wire EinsteinAFMBridge into build + packaging pipeline"
```

---

## 3. Phase 6 — install.sh OS + locale detection (~2-3 hr)

**Goal:** Fresh-install detects macOS 26 + Apple Silicon + en_US locale. Sets the right `EINSTEIN_AI_PROVIDER` default. Warns clearly when AFM cannot be used.

### 3.1 Insert after current macOS check (around line 73 of `install.sh`)

```bash
# ──────────────────────────────────────────────────────────────────
# 1b. Detect Apple Foundation Models eligibility
# ──────────────────────────────────────────────────────────────────

step "Checking Apple Foundation Models eligibility"

mac_arch="$(uname -m)"
mac_locale="$(defaults read NSGlobalDomain AppleLocale 2>/dev/null || echo "")"

AFM_ELIGIBLE=false
AFM_REASON=""

if [[ "$mac_arch" != "arm64" ]]; then
  AFM_REASON="non-Apple-Silicon Mac ($mac_arch)"
elif (( macos_major < 26 )); then
  AFM_REASON="macOS $macos_version (need 26+)"
elif [[ "$mac_locale" != "en_US" ]]; then
  AFM_REASON="locale is '$mac_locale' (need en_US — open System Settings → General → Language & Region → set Primary Language to English (US))"
else
  AFM_ELIGIBLE=true
fi

if [[ "$AFM_ELIGIBLE" == "true" ]]; then
  ok "Apple Silicon + macOS $macos_version + locale en_US — Apple Foundation Models supported"
  note "After install, make sure Apple Intelligence is enabled in System Settings → Apple Intelligence & Siri"
  note "First-time enable triggers a 1-30 min model download from Apple's CDN; this is normal"
else
  warn "Apple Foundation Models unavailable: $AFM_REASON"
  note "Carrel will fall back to Ollama. Install Ollama separately (https://ollama.com)."
fi
```

### 3.2 Update the `.env` defaulting block

Replace the existing "set EINSTEIN_AI_PROVIDER=ollama and warn" branch (when no Anthropic key is provided) with:

```bash
if [[ "$AFM_ELIGIBLE" == "true" ]]; then
  # Leave EINSTEIN_AI_PROVIDER=auto in .env. Auto path will pick AFM.
  ok "Default local backend will be Apple Foundation Models (auto-detected)."
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
  ok "Set EINSTEIN_AI_PROVIDER=ollama (AFM unavailable on this Mac)"
  warn "Start Ollama with 'ollama serve' before launching, or the tutor will refuse every question"
fi
```

### 3.3 Add post-install AFM probe (optional but recommended)

After `swift build` runs, probe AFM availability so the install log surfaces the specific reason if it's not ready:

```bash
if [[ "$AFM_ELIGIBLE" == "true" ]]; then
  step "Probing Apple Foundation Models availability"
  bridge="./macos-app/.build/debug/EinsteinAFMBridge"
  if [[ -x "$bridge" ]]; then
    state=$(echo '{"kind":"availability","request_id":"install"}' | "$bridge" 2>/dev/null \
      | python3 -c "import sys, json; d=json.loads(sys.stdin.read()); print(d.get('availability_state','unknown'))")
    case "$state" in
      available)
        ok "Apple Intelligence is ready"
        ;;
      apple_intelligence_not_enabled)
        warn "Apple Intelligence is disabled. Enable it in System Settings → Apple Intelligence & Siri"
        ;;
      device_not_eligible)
        warn "This Mac is not eligible for Apple Intelligence (region/account check failed)"
        ;;
      model_not_ready)
        warn "Apple Intelligence model is downloading (1-30 min). Carrel will pick it up automatically when ready."
        ;;
      *)
        note "Could not determine Apple Intelligence state ($state); will probe at runtime"
        ;;
    esac
  fi
fi
```

### 3.4 Commit

```bash
git add install.sh
git commit -m "feat(ai): install.sh detects AFM eligibility (macOS 26 + arm64 + en_US locale)"
```

---

## 4. Phase 7 — integration tests against real bridge (~2 hr)

**Goal:** Two integration tests gated on `CARREL_RUN_AFM_INTEGRATION=1` that prove the full Python→Swift→AFM round trip works against a real model.

### 4.1 Create `tests/integration/__init__.py` if missing

```bash
mkdir -p /Users/madu/Desktop/Codex/tests/integration
touch /Users/madu/Desktop/Codex/tests/integration/__init__.py
```

### 4.2 Create `tests/integration/test_afm_real_bridge.py`

```python
import os
import platform
import sys
import unittest
from pathlib import Path

skip_reason = (
    "Set CARREL_RUN_AFM_INTEGRATION=1, run on macOS 26+ Apple Silicon "
    "with Apple Intelligence enabled and en_US primary locale, and "
    "have the bridge built (cd macos-app && swift build)."
)


def _on_macos_26_with_bridge() -> bool:
    if sys.platform != "darwin" or platform.machine() != "arm64":
        return False
    try:
        major = int(platform.mac_ver()[0].split(".")[0])
    except Exception:
        return False
    if major < 26:
        return False
    from ai.native_bridge_paths import find_binary, AFM_BRIDGE_CANDIDATES
    return find_binary(AFM_BRIDGE_CANDIDATES) is not None


@unittest.skipUnless(
    os.getenv("CARREL_RUN_AFM_INTEGRATION") == "1" and _on_macos_26_with_bridge(),
    skip_reason,
)
class AFMRealBridgeTests(unittest.TestCase):
    def test_availability_is_available(self) -> None:
        from ai.afm_client import AFMClient
        client = AFMClient()
        # Cheap availability call via a minimal request_text. If this
        # passes the bridge confirms AFM is fully serving.
        result = client.request_text(
            request_kind="integration.smoke",
            system="Reply in exactly one short sentence.",
            prompt="What is one plus one?",
            max_tokens=32,
        )
        self.assertTrue(result.ok, msg=f"AFM not available: {result.error_code} / {result.error_message}")

    def test_request_text_returns_real_generation(self) -> None:
        from ai.afm_client import AFMClient
        client = AFMClient()
        result = client.request_text(
            request_kind="integration.text",
            system="Reply in one sentence.",
            prompt="What is mitosis?",
            max_tokens=64,
        )
        self.assertTrue(result.ok, msg=result.error_message)
        self.assertIsNotNone(result.text)
        self.assertGreater(len(result.text), 10)
        self.assertLess(result.latency_ms, 30_000, msg="cold-start cap")

    def test_request_json_with_real_model(self) -> None:
        from ai.afm_client import AFMClient
        client = AFMClient()
        result = client.request_json(
            request_kind="integration.json",
            system='Return JSON: {"answer": <string>}.',
            prompt="What is the capital of France?",
            fallback={"answer": ""},
        )
        self.assertTrue(result.ok)
        self.assertIsInstance(result.json_payload, dict)
        self.assertIn("answer", result.json_payload)
        self.assertGreater(len(result.json_payload["answer"]), 0)


class AFMPerfSmokeTests(unittest.TestCase):
    @unittest.skipUnless(
        os.getenv("CARREL_RUN_AFM_INTEGRATION") == "1" and _on_macos_26_with_bridge(),
        skip_reason,
    )
    def test_warm_call_under_three_seconds(self) -> None:
        from ai.afm_client import AFMClient
        client = AFMClient()
        # Warm up
        client.request_text(
            request_kind="perf.warmup",
            system="",
            prompt="Hi.",
            max_tokens=8,
        )
        # Real measure
        result = client.request_text(
            request_kind="perf.measure",
            system="",
            prompt="Write one short paragraph about cell division.",
            max_tokens=120,
        )
        self.assertTrue(result.ok)
        self.assertLess(
            result.latency_ms, 3_000,
            msg=f"Warm latency degraded to {result.latency_ms:.0f}ms",
        )


if __name__ == "__main__":
    unittest.main()
```

### 4.3 Run integration suite

```bash
cd /Users/madu/Desktop/Codex
CARREL_RUN_AFM_INTEGRATION=1 ./.venv/bin/python -m unittest tests.integration.test_afm_real_bridge -v
```

Expected: 4 tests pass. If any fail, paste the output and we diagnose.

### 4.4 Update CLAUDE.md verify chain

Add the integration test command to the "verify chain" block in `CLAUDE.md` as an optional pre-release step:

```bash
# Optional pre-release: integration tests against real AFM bridge.
# Requires macOS 26+ Apple Silicon, Apple Intelligence enabled, en_US locale.
CARREL_RUN_AFM_INTEGRATION=1 ./.venv/bin/python -m unittest \
    tests.integration.test_afm_real_bridge -v
```

### 4.5 Commit

```bash
git add tests/integration/test_afm_real_bridge.py tests/integration/__init__.py CLAUDE.md
git commit -m "test(ai): integration tests against real AFM bridge (gated on env var)"
```

---

## 5. Phase 8 — documentation sweep (~1 hr)

### 5.1 README.md

Find the "Configuration" or "AI provider" section. Replace the Ollama emphasis with AFM:

```markdown
## AI provider

Carrel routes LLM calls through a provider abstraction at `ai/providers.py`.
The auto resolution order is:

1. **Claude** (paid Pro tier) when `ANTHROPIC_API_KEY` is set.
2. **Apple Foundation Models** (free, on-device) on macOS 26+ Apple
   Silicon with `AppleLocale=en_US` and Apple Intelligence enabled.
3. **Ollama** as legacy fallback for users on macOS 14/15 or Intel.

Override with `EINSTEIN_AI_PROVIDER=claude|afm|ollama|off` in `.env`.

The free tier uses Apple's on-device 3B model via the EinsteinAFMBridge
Swift sidecar. Zero download required (model ships with macOS 26).
First-time enable triggers a 1-30 min model variant download from
Apple's CDN; subsequent launches are instant.
```

### 5.2 CLAUDE.md

Update the Stack section:

```markdown
- **AI:** Claude API via `ai/router.py`. Models: `claude-haiku-4-5`,
  `claude-sonnet-4-6`, `claude-opus-4-7`. Local default on macOS 26+:
  Apple Foundation Models via `ai/afm_client.py` and the
  `EinsteinAFMBridge` Swift sidecar. Ollama (`ai/ollama.py`) is the
  legacy fallback for macOS 14/15 / Intel. Structured output via
  `request_tool_call` with forced tool use on Claude; system-prompt
  enforcement + post-hoc parse on AFM and Ollama (neither has runtime
  guided-generation as of their respective public APIs).
```

### 5.3 docs/install-beta.md

Add to the top:

```markdown
**Free tier requirements (macOS 26+):** Carrel's free tier runs on
Apple's on-device 3B model via the FoundationModels framework. To use
it you need: macOS 26 (Tahoe) or newer, an Apple Silicon Mac, primary
language set to **English (US)**, and Apple Intelligence enabled in
System Settings → Apple Intelligence & Siri.

If your Mac is not eligible (older OS, Intel chip, non-en_US locale),
Carrel falls back to Ollama; install Ollama separately and run
`ollama serve` before launching Carrel.
```

### 5.4 Commit

```bash
git add README.md CLAUDE.md docs/install-beta.md
git commit -m "docs(ai): document AFM as default free-tier backend"
```

---

## 6. Phase 9 — final verify chain (~30 min)

```bash
cd /Users/madu/Desktop/Codex

# Full verify
./script/generate-api-types.sh
corepack pnpm --dir frontend typecheck
corepack pnpm --dir frontend lint
corepack pnpm --dir frontend test
corepack pnpm --dir frontend build:macos
( cd macos-app && swift build )
./.venv/bin/python -m ruff check ai services evals tests main.py db.py routes api_models.py benchmarks
./.venv/bin/python -m unittest discover -s tests -p "test_*.py" -v

# Optional integration suite
CARREL_RUN_AFM_INTEGRATION=1 ./.venv/bin/python -m unittest tests.integration.test_afm_real_bridge -v

# End-to-end smoke
./script/build_and_run.sh --verify
```

All green or it does not land. If something fails, paste the error and we diagnose.

---

## 7. Open the PR

```bash
git push -u origin feat/afm-integration-2026-05-10
gh pr create --title "feat(ai): Apple Foundation Models provider" --body "$(cat <<'EOF'
## Summary

* Adds `AFMClient` Python provider implementing `AIProvider` Protocol
* Adds `EinsteinAFMBridge` Swift sidecar wrapping FoundationModels
* `select_provider` auto path now: Claude → AFM → Ollama → Null
* `install.sh` detects macOS 26 + arm64 + en_US locale and sets the
  right default
* Carrel free tier is now functional on Apple's on-device 3B model

## Files

NEW: `ai/afm_client.py` (+409), `ai/native_bridge_paths.py` (+58),
     `macos-app/Sources/EinsteinAFMBridge/main.swift` (+271),
     `tests/test_afm_client.py` (+398),
     `tests/integration/test_afm_real_bridge.py` (+90)
MOD: `ai/providers.py`, `macos-app/Package.swift`,
     `services/extraction/utils.py`, `tests/test_ai_providers.py`,
     `install.sh`, `script/build_and_run.sh`,
     `script/package_public_beta.sh`, `BackendSupervisor.swift`,
     `README.md`, `CLAUDE.md`, `docs/install-beta.md`

## Verified on

* macOS 26.4.1, M-series, en_US primary locale
* `swift build` clean for all 3 targets
* 47 unit tests passing in 0.011s
* Integration suite: 4 tests passing against real model
* Real generation: ok=true, ~700ms warm latency, ~5s cold start

## Test plan

- [ ] Reviewer on macOS 26+ runs full verify chain locally
- [ ] Reviewer toggles `EINSTEIN_AI_PROVIDER=ollama` and confirms
      fallback path still works
- [ ] Reviewer toggles `EINSTEIN_AI_PROVIDER=off` and confirms tutor
      surfaces "AI synthesis unavailable" rather than silent failure

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Common failure modes + fixes

| Symptom | Likely cause | Fix |
|---|---|---|
| `swift build` fails on `String(describing: response.content)` | AFM SDK changed `Response.content` typing | Adjust `main.swift:171` to `response.content` directly (no `String(describing:)`); rebuild |
| `model_not_ready` after restart | Apple still downloading variants | Wait 5-15 min, retry. Watch `/usr/bin/log show --predicate 'process == "modelcatalogd"' --last 5m` for download activity |
| `apple_intelligence_not_enabled` | Master toggle off in System Settings | Open System Settings → Apple Intelligence & Siri, toggle Apple Intelligence on |
| Bridge JSON output empty | Bridge crashed silently | Run `swift build` then re-execute the bridge directly to see stderr |
| Test `test_afm_client_is_ai_provider` fails | `AFMClient` doesn't implement Protocol | Check `ai/providers.py::AIProvider` for any new method requirement |
| `ruff check` complains about import order | Auto-fixable | `./.venv/bin/python -m ruff check --fix ai/afm_client.py` |

---

## Memory references

These memory entries carry context for future sessions:

* `carrel_afm_integration_plan.md` — the full 9-phase plan
* `carrel_afm_implementation_pass1.md` — what shipped in Pass 1 + the en_US gotcha
* `carrel_strategy_2026-05-10.md` — strategic context for why AFM matters

---

*End of runbook.*
