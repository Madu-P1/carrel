import { useCallback, useEffect, useState } from "preact/hooks";

import { Button, Dialog, Stack, Text } from "@/design-system";
import { API_BASE } from "@/services/api/client";

const HEALTH_TIMEOUT_MS = 5000;
// The Python backend exempts /api/health from the local-API token gate;
// matches the path the Swift BackendSupervisor already polls.
const HEALTH_PATH = "/api/health";

type BootState = "checking" | "ok" | "error";

async function probeBackend(): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE}${HEALTH_PATH}`, {
      cache: "no-store",
      method: "GET",
      signal: AbortSignal.timeout(HEALTH_TIMEOUT_MS)
    });
    return response.ok;
  } catch {
    return false;
  }
}

function quitCarrel(): void {
  const native = (window as Window & {
    webkit?: { messageHandlers?: { quit?: { postMessage?: (msg: string) => void } } };
  }).webkit?.messageHandlers?.quit;
  if (native && typeof native.postMessage === "function") {
    native.postMessage("quit");
    return;
  }
  window.close();
}

/**
 * PR-S1: shows a blocking overlay when the local backend can't be reached.
 *
 * Cachet is a local-first macOS app — the Python service runs as a child of
 * the Swift host and ships the request-scoped local-API token via
 * WKUserScript. If the supervisor hasn't booted the Python yet (or the
 * Python died and hasn't respawned), every /api/* call would 403. Instead
 * of letting features show their own "Load failed" toasts, we surface a
 * single boot-error overlay with a Retry button.
 */
export function BackendBootCheck() {
  const [state, setState] = useState<BootState>("checking");

  const runCheck = useCallback(async () => {
    setState("checking");
    const ok = await probeBackend();
    setState(ok ? "ok" : "error");
  }, []);

  useEffect(() => {
    void runCheck();
  }, [runCheck]);

  // Auto-recover from the cold-start race. The Swift BackendSupervisor
  // spawns Python on app launch; cold start (imports + SQLite migrations
  // + provider warmup) routinely takes 5–30 seconds. The first probe
  // runs at app boot and frequently loses the race against a 5-second
  // timeout. Without this, the overlay sticks indefinitely until the
  // user notices the "Retry" button — even though the backend is alive
  // a few seconds later. We silently re-probe every 2s while state is
  // "error" and flip to "ok" the moment one succeeds. State is left at
  // "error" between attempts so the overlay doesn't flicker.
  useEffect(() => {
    if (state !== "error") return;
    const interval = window.setInterval(async () => {
      const ok = await probeBackend();
      if (ok) setState("ok");
    }, 2000);
    return () => window.clearInterval(interval);
  }, [state]);

  if (state !== "error") {
    return null;
  }

  return (
    <Dialog
      actions={
        <Stack direction="horizontal" gap={2}>
          <Button onClick={() => void runCheck()} variant="primary">
            Retry
          </Button>
          <Button onClick={quitCarrel} variant="ghost">
            Quit Cachet
          </Button>
        </Stack>
      }
      onClose={() => void runCheck()}
      open
      title="Couldn't connect to local backend"
    >
      <Stack gap={3}>
        <Text>
          Cachet uses a local Python service to keep your data on device. It looks like it didn't start.
        </Text>
        <Text tone="secondary">
          If this keeps happening, restart Cachet from the menu bar or check Console.app for "Cachet" errors.
        </Text>
      </Stack>
    </Dialog>
  );
}
