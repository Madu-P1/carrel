# Einstein ChatGPT App

This folder contains the first Apps SDK scaffold for running Einstein Tutor inside ChatGPT.

It follows OpenAI's current Apps SDK pattern:

- an MCP server that exposes tools to ChatGPT
- a widget UI rendered inside ChatGPT
- a public `/mcp` endpoint that ChatGPT connects to

The scaffold is intentionally narrow but real. It wraps the existing FastAPI backend instead of reimplementing Einstein from scratch.

## Included

- `server.js`
  - Node MCP server using `@modelcontextprotocol/sdk` and `@modelcontextprotocol/ext-apps`
  - exposes:
    - `get_workspace_overview`
    - `set_learning_goal`
    - `ask_einstein`
    - `start_study_session`
- `public/einstein-widget.html`
  - first embedded Einstein widget for ChatGPT
  - uses the MCP Apps bridge (`ui/initialize`, `tools/call`, `ui/notifications/tool-result`)

## Run locally

1. Start the existing Einstein backend:

```bash
cd /Users/madu/Desktop/Codex
python3 -m uvicorn main:app --reload --app-dir /Users/madu/Desktop/Codex
```

If Einstein is already running on `127.0.0.1:8000`, do not start a second copy.
If some other service is using port `8000`, start Einstein on another port and point the ChatGPT app at it:

```bash
cd /Users/madu/Desktop/Codex
python3 -m uvicorn main:app --reload --host 127.0.0.1 --port 8001 --app-dir /Users/madu/Desktop/Codex
```

2. Install the Apps SDK dependencies:

```bash
cd /Users/madu/Desktop/Codex/chatgpt-app
npm install
```

3. Start the MCP server:

```bash
npm start
```

By default, the ChatGPT app server runs on `http://127.0.0.1:8787/mcp` and proxies Einstein API calls to `http://127.0.0.1:8000`.

## Environment

- `PORT`
  - Defaults to `8787`
- `MCP_PATH`
  - Defaults to `/mcp`
- `EINSTEIN_API_BASE_URL`
  - Defaults to `http://127.0.0.1:8000`
- `CHATGPT_APP_DOMAIN`
  - Optional. Set this when you host the widget on a dedicated origin for production/app submission.

Example:

```bash
PORT=8787 EINSTEIN_API_BASE_URL=http://127.0.0.1:8000 npm start
```

If Einstein is running on `8001` instead:

```bash
PORT=8787 EINSTEIN_API_BASE_URL=http://127.0.0.1:8001 npm start
```

## Local checks

- Health:

```bash
curl http://127.0.0.1:8787/health
```

- Widget preview:

```bash
open http://127.0.0.1:8787/widget-preview
```

The widget preview is only a visual shell. Real tool calls require the ChatGPT Apps bridge.

## Connect to ChatGPT

OpenAI's current Apps SDK flow is:

1. Enable developer mode in ChatGPT.
2. Expose the local MCP server to the public internet, for example with `ngrok`.
3. Add a connector in ChatGPT using your public HTTPS URL plus `/mcp`.

Typical tunnel command:

```bash
ngrok http 8787
```

Then use:

```text
https://<your-subdomain>.ngrok.app/mcp
```

## Next steps

- add `complete_study_session`
- add file upload and source selection support
- add richer session controls and evidence interactions in the widget
- move more of the standalone Einstein surfaces into ChatGPT-safe iframe components
