import { fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { beforeEach, expect, test } from "vitest";

import {
  getFetchCalls,
  mockJson,
  registerFetchHandler
} from "../../../tests/support/mockFetch";

import { SettingsView } from "./SettingsView";
import { resetAiSettingsQuery } from "./hooks/useAiSettings";

/* The settings query is module-scoped (shared cache), so each test
 * starts from a clean slate — same reason tests/setup.ts resets the
 * library query. */
beforeEach(() => {
  resetAiSettingsQuery();
});

type ProviderVerdict = {
  kind: string;
  configured: boolean;
  available: boolean;
  detail: string;
  error_code: string | null;
};

interface AiSettingsFixture {
  provider?: string;
  key_set?: boolean;
  key_valid?: boolean | null;
  claude?: Partial<ProviderVerdict>;
  ollama?: Partial<ProviderVerdict>;
  afm?: Partial<ProviderVerdict>;
}

function verdict(kind: string, over: Partial<ProviderVerdict> = {}): ProviderVerdict {
  return {
    kind,
    configured: false,
    available: false,
    detail: `${kind} detail`,
    error_code: null,
    ...over
  };
}

function aiSettings(over: AiSettingsFixture = {}) {
  return {
    provider: over.provider ?? "auto",
    key_set: over.key_set ?? false,
    key_valid: over.key_valid ?? null,
    availability: {
      claude: verdict("claude", over.claude),
      ollama: verdict("ollama", over.ollama),
      afm: verdict("afm", over.afm)
    }
  };
}

/** Stub GET /api/settings/ai with the given payload. */
function mockGetSettings(payload: ReturnType<typeof aiSettings>) {
  return mockJson("GET", "/api/settings/ai", payload);
}

test("renders the three provider cards", async () => {
  mockGetSettings(aiSettings());
  render(<SettingsView />);

  await waitFor(() => {
    expect(screen.getByTestId("provider-card-claude")).toBeDefined();
  });
  expect(screen.getByTestId("provider-card-ollama")).toBeDefined();
  expect(screen.getByTestId("provider-card-afm")).toBeDefined();
});

test("picking a provider POSTs that provider to updateAi", async () => {
  mockGetSettings(aiSettings({ provider: "auto" }));
  // The POST returns the new state — reflect the switch.
  mockJson("POST", "/api/settings/ai", () => aiSettings({ provider: "ollama" }));

  render(<SettingsView />);
  await waitFor(() => {
    expect(screen.getByRole("tab", { name: "Ollama" })).toBeDefined();
  });

  fireEvent.click(screen.getByRole("tab", { name: "Ollama" }));

  await waitFor(() => {
    const post = getFetchCalls().find(
      (call) => call.url.endsWith("/api/settings/ai") && call.method === "POST"
    );
    expect(post).toBeDefined();
    expect(JSON.parse(String(post?.body))).toEqual({ provider: "ollama" });
  });
});

test("entering a key and saving POSTs anthropic_key", async () => {
  mockGetSettings(aiSettings({ provider: "claude" }));
  mockJson("POST", "/api/settings/ai", () =>
    aiSettings({ provider: "claude", key_set: true, key_valid: true })
  );

  render(<SettingsView />);
  await waitFor(() => {
    expect(screen.getByTestId("claude-key-input")).toBeDefined();
  });

  fireEvent.input(screen.getByTestId("claude-key-input"), {
    target: { value: "sk-ant-secret-123" }
  });
  fireEvent.click(screen.getByRole("button", { name: "Save key" }));

  await waitFor(() => {
    const post = getFetchCalls().find(
      (call) => call.url.endsWith("/api/settings/ai") && call.method === "POST"
    );
    expect(post).toBeDefined();
    expect(JSON.parse(String(post?.body))).toEqual({
      anthropic_key: "sk-ant-secret-123"
    });
  });
});

test("the API key value never appears in the DOM after a save", async () => {
  const secret = "sk-ant-super-secret-value";
  mockGetSettings(aiSettings({ provider: "claude" }));
  // The backend contract: the POST response carries key_set, never the
  // key value. The view must not echo the typed value back either.
  mockJson("POST", "/api/settings/ai", () =>
    aiSettings({ provider: "claude", key_set: true, key_valid: true })
  );

  render(<SettingsView />);
  await waitFor(() => {
    expect(screen.getByTestId("claude-key-input")).toBeDefined();
  });

  fireEvent.input(screen.getByTestId("claude-key-input"), {
    target: { value: secret }
  });
  fireEvent.click(screen.getByRole("button", { name: "Save key" }));

  await waitFor(() => {
    expect(screen.getByTestId("claude-key-status")).toBeDefined();
  });

  // After the save lands, the secret must not be present anywhere in the
  // rendered tree — not in text, not as an input value.
  expect(document.body.textContent).not.toContain(secret);
  const passwordInput = screen.getByTestId("claude-key-input") as HTMLInputElement;
  expect(passwordInput.value).not.toContain(secret);
  expect(passwordInput.type).toBe("password");
});

test("AFM not-enabled renders the System Settings affordance", async () => {
  mockGetSettings(
    aiSettings({
      afm: {
        configured: true,
        available: false,
        detail: "Apple Intelligence is turned off.",
        error_code: "apple_intelligence_not_enabled"
      }
    })
  );

  render(<SettingsView />);

  await waitFor(() => {
    expect(
      screen.getByRole("button", { name: "Open System Settings" })
    ).toBeDefined();
  });
  // The guidance fallback text always renders alongside the button.
  expect(
    screen.getByText(/Turn on Apple Intelligence in System Settings/i)
  ).toBeDefined();
});

test("Ollama unreachable surfaces the detail hint", async () => {
  mockGetSettings(
    aiSettings({
      ollama: {
        configured: true,
        available: false,
        detail: "Ollama is not running. Start it with `ollama serve`.",
        error_code: "ollama_unreachable"
      }
    })
  );

  render(<SettingsView />);

  await waitFor(() => {
    expect(
      screen.getByText(/Start it with `ollama serve`/i)
    ).toBeDefined();
  });
});

test("AFM is disabled in the picker when the device is not eligible", async () => {
  mockGetSettings(
    aiSettings({
      afm: {
        configured: false,
        available: false,
        detail: "This Mac does not support Apple Intelligence.",
        error_code: "device_not_eligible"
      }
    })
  );

  render(<SettingsView />);

  await waitFor(() => {
    expect(screen.getByRole("tab", { name: "Apple Intelligence" })).toBeDefined();
  });
  const afmTab = screen.getByRole("tab", {
    name: "Apple Intelligence"
  }) as HTMLButtonElement;
  expect(afmTab.disabled).toBe(true);

  // Clicking the disabled tab must not POST.
  let posted = false;
  registerFetchHandler((url, init) => {
    if (url.pathname === "/api/settings/ai" && init.method.toUpperCase() === "POST") {
      posted = true;
    }
    return undefined;
  });
  fireEvent.click(afmTab);
  expect(posted).toBe(false);
});
