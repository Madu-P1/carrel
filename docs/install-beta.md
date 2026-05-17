# Carrel — install (developer beta)

> This is a developer-checkout install. Carrel is not yet code-signed
> or notarized, and the macOS shell expects to find a Python venv
> alongside it. Until Phase 4 ships a self-contained `.dmg`, the path
> to a working Carrel is "clone the repo, run one script."
>
> Five-to-ten minutes for the first install. One second for every
> launch after that.

## Free tier — Apple Foundation Models (macOS 26+)

Carrel's free tier runs on Apple's on-device 3B model via the
FoundationModels framework. To use it without an Anthropic key you
need:

- macOS 26 (Tahoe) or newer
- An Apple Silicon Mac (M1 or later)
- Primary language set to **English (US)**
- Apple Intelligence enabled in **System Settings → Apple Intelligence & Siri**

`install.sh` checks the three install-time conditions (Apple Silicon,
macOS 26+, en_US locale) and selects AFM automatically when all three
hold; you do not need to set `EINSTEIN_AI_PROVIDER=afm` by hand. The
fourth condition, Apple Intelligence enabled, is a runtime check the
installer cannot perform; install.sh reminds you to confirm it in
**System Settings, Apple Intelligence & Siri** before launching. On a
Mac that meets the install-time bar, the install command is just:

```bash
curl -fsSL https://raw.githubusercontent.com/Madu-P1/carrel/main/install.sh | bash
```

If your Mac is not eligible:

- **Apple Intelligence disabled** (most common): enable it in **System Settings, Apple Intelligence & Siri** and relaunch. No reinstall needed.
- **Older OS, Intel chip, or non-en_US locale**: Carrel falls back to Ollama or Claude. Install Ollama separately and run `ollama serve` before launching Carrel, or pass an Anthropic key as the one-paste path below shows.

## What you need

- macOS 14 (Sonoma) or later
- ~3 GB free disk for the venv + `fastembed` model cache
- Xcode Command Line Tools — install with `xcode-select --install`
- Python 3.12 — `brew install python@3.12` works
- Bun — `curl -fsSL https://bun.sh/install | bash` (or `pnpm`/`npm`, the build script picks whichever is on `PATH`)
- An Anthropic API key, OR a local `ollama serve` running. Carrel needs an LLM somewhere; without one the tutor will refuse every question.

## Install — the one-paste path (recommended)

Bring your Anthropic API key (get one at
https://console.anthropic.com/settings/keys), then paste this into
Terminal:

```bash
curl -fsSL https://raw.githubusercontent.com/Madu-P1/carrel/main/install.sh | \
  ANTHROPIC_API_KEY=sk-ant-api03-YOUR-KEY-HERE bash
```

Note the env var goes on `bash`, not on `curl` — pipelines run `curl`
and `bash` in separate processes, so the env var prefix only applies
to whichever side it's attached to. Wrong syntax (`ANTHROPIC_API_KEY=...
curl ...`) silently falls through to the deferred-launch path because
`bash` never sees the variable.

Want to use local Ollama instead of Claude? Same pattern:

```bash
curl -fsSL https://raw.githubusercontent.com/Madu-P1/carrel/main/install.sh | \
  EINSTEIN_AI_PROVIDER=ollama bash
```

Make sure `ollama serve` is running with a model pulled
(`ollama pull llama3.1:8b`) before launching, or the tutor will refuse
every question.

## Install — the interactive path (if you'd rather be prompted)

```bash
curl -fsSL https://raw.githubusercontent.com/Madu-P1/carrel/main/install.sh | bash
```

Without an env var, the installer runs every step except the launch.
At the end it prints "Install complete (launch deferred)" and tells
you to edit `.env` to set your provider, then run
`./script/build_and_run.sh` from the repo. Use this form if you want
to inspect `.env` before the app starts.

If you already cloned, `cd` into the repo first and run `./install.sh`
(env-var prefix works the same way, or it'll prompt interactively).
The script detects which mode you're in and acts accordingly.

## Install — the manual path (if you want to see every step)

```bash
git clone https://github.com/Madu-P1/carrel.git
cd carrel

# uv brings its own Python; no brew needed
curl -LsSf https://astral.sh/uv/install.sh | sh
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -r requirements.txt

cp .env.example .env
# Open .env and either:
#   - paste your Anthropic key into ANTHROPIC_API_KEY, OR
#   - set EINSTEIN_AI_PROVIDER=ollama and start `ollama serve`

./script/build_and_run.sh
```

The first run takes ~1 minute (Swift build + Vite bundle + uvicorn boot
+ first-time `fastembed` model download). Subsequent runs are ~1 second.

When the app launches you should see the Library view with no sources.
Drop a PDF onto the window or click **Import Source…** (⌘I) and let
ingestion finish (a job tray will show progress). Then **Ask** (⌘5)
your first question against it.

## What can go wrong

**"Backend failed to start."**
The script kills any old `uvicorn main:app` and starts its own. If it
still fails, tail the log: `tail -n 60 dist/einstein-backend.log`. Most
common cause: missing `fastapi`/`uvicorn` in the venv. Re-run
`pip install -r requirements.txt`.

**"Local study engine unavailable" inside the app.**
The Swift shell launched, but its supervisor couldn't reach
`http://127.0.0.1:8000/api/health`. Either the backend died, or your
Python doesn't have `fastapi` and `uvicorn` installed. Open Activity
Monitor and check for a `Python` process; if there isn't one, the
backend never started — see above.

**"This app cannot be opened because it is from an unidentified
developer."**
Right-click the .app and choose **Open** (not double-click), then
**Open** in the dialog. macOS remembers the choice for that .app
forever. This goes away once Carrel is notarized in Phase 4.

**Empty `ANTHROPIC_API_KEY` and no Ollama.**
The tutor will return a `weak_coverage` refusal on every question
because there's no LLM to call. Either set the key in `.env` or run
`ollama serve` with a small model pulled (`ollama pull llama3.1:8b`),
then restart Carrel.

**Ingestion seems stuck.**
First-time PDF ingestion downloads `BAAI/bge-small-en-v1.5` (~120 MB)
to `~/.cache/fastembed/` for vector retrieval. It only happens once;
subsequent ingests reuse the cache. If you're on a slow network this
can take a couple of minutes. Check the log if it's longer than that.

## What's actually in your library

`data/einstein_tutor.db` is a single SQLite file. Everything you
import, every chunk, every concept, every flashcard lives there. Back
it up if you've ingested anything you don't want to re-do (`cp data/einstein_tutor.db
~/Desktop/carrel-backup.db`). Uninstalling Carrel is "delete the
folder you cloned into."

## Filing feedback

What helps most, in order:
1. A screen recording of the moment something felt wrong (Cmd-Shift-5
   on macOS; the .mov file).
2. The contents of `dist/einstein-backend.log` from that session.
3. One sentence on what you were trying to do.

Email or DM whoever sent you the link.

## What this is

Carrel is a local-first, source-grounded study and research workspace
for macOS. Drop in PDFs (or slides, DOCX, plain text). Ask questions
that get answered with verbatim citations back to chunks of the source
— or get refused honestly if the corpus doesn't cover the question.
SRS flashcards on top, an iCal-aware coach proposing study blocks
where your week has gaps. Nothing leaves your laptop except the calls
to the LLM you chose; sources, chunks, and flashcards are SQLite on
disk.

It is **not** finished. The premium UI roadmap closed but Phase 4
(signing, notarization, Sparkle updater, monetization) is unstarted,
and a number of refinements (command palette, toast Undo, observed-
not-asked life policies for the planner) are visible debts. You're
the first user. Treat it that way.
