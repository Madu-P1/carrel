import { fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { expect, test } from "vitest";

import { App } from "../src/app/App";
import { appShell } from "../src/app/shell/useAppShell";
import { AskView } from "../src/features/ask/AskView";
import { useAskTutor } from "../src/features/ask/hooks/useAskTutor";
import { DEMO_ANSWER, DEMO_FALLBACK } from "../src/features/ask/fixtures/grounded-answer.fixture";
import { getFetchCalls, jsonResponse, mockJson, registerFetchHandler } from "./support/mockFetch";

function HookHarness() {
  const { answer, error, pending, submit } = useAskTutor();

  return (
    <div>
      <button
        onClick={() => {
          void submit("What is mitosis?");
        }}
        type="button"
      >
        Submit
      </button>
      <span data-testid="hook-pending">{String(pending.value)}</span>
      <span data-testid="hook-error">{error.value?.message ?? ""}</span>
      <span data-testid="hook-answer">{answer.value?.answer ?? ""}</span>
    </div>
  );
}

test("useAskTutor toggles pending and stores the tutor answer", async () => {
  const requestState: { resolve: null | (() => void) } = { resolve: null };

  registerFetchHandler((url, init) => {
    if (url.pathname !== "/api/tutor/query" || init.method !== "POST") {
      return undefined;
    }

    return new Promise<Response>((resolve) => {
      requestState.resolve = () => resolve(jsonResponse(DEMO_ANSWER));
    });
  });

  render(<HookHarness />);

  fireEvent.click(screen.getByRole("button", { name: /Submit/i }));

  await waitFor(() => {
    expect(screen.getByTestId("hook-pending").textContent).toBe("true");
  });

  await waitFor(() => expect(requestState.resolve).not.toBeNull());
  requestState.resolve?.();

  await waitFor(() => {
    expect(screen.getByTestId("hook-pending").textContent).toBe("false");
    expect(screen.getByTestId("hook-answer").textContent).toContain("Mitosis produces");
  });
});

test("AskView renders the loading skeleton and grounded answer after submit", async () => {
  const requestState: { resolve: null | (() => void) } = { resolve: null };

  registerFetchHandler((url, init) => {
    if (url.pathname !== "/api/tutor/query" || init.method !== "POST") {
      return undefined;
    }

    return new Promise<Response>((resolve) => {
      requestState.resolve = () => resolve(jsonResponse(DEMO_ANSWER));
    });
  });

  render(<AskView />);

  fireEvent.input(screen.getByLabelText(/Question/i), {
    currentTarget: { value: "What is mitosis?" },
    target: { value: "What is mitosis?" }
  });
  fireEvent.click(screen.getByRole("button", { name: /^Ask$/i }));

  expect(screen.getByTestId("ask-answer-skeleton")).toBeDefined();

  await waitFor(() => expect(requestState.resolve).not.toBeNull());
  requestState.resolve?.();

  expect(await screen.findByText(/Mitosis produces two genetically identical daughter cells/i)).toBeDefined();
  expect(screen.getByText(/Mitosis creates two genetically identical daughter cells\./i)).toBeDefined();
});

test("AskView stages grounded answers with escalating reveal delays", async () => {
  mockJson("POST", "/api/tutor/query", DEMO_ANSWER);

  render(<AskView />);

  fireEvent.input(screen.getByLabelText(/Question/i), {
    currentTarget: { value: "What is mitosis?" },
    target: { value: "What is mitosis?" }
  });
  fireEvent.click(screen.getByRole("button", { name: /^Ask$/i }));

  const firstClaim = await screen.findByText(/Mitosis creates two genetically identical daughter cells\./i);
  const secondClaim = screen.getByText(/Checkpoints pause progression if DNA is damaged\./i);
  const firstCitation = screen.getByRole("button", { name: /Cell division basics/i });
  const secondCitation = screen.getByRole("button", { name: /Cell-cycle regulation/i });
  const unsupported = screen.getByRole("button", { name: /Not in your sources/i }).closest("section");

  expect(firstClaim.closest("article")?.getAttribute("style")).toContain("animation-delay: 80ms");
  expect(secondClaim.closest("article")?.getAttribute("style")).toContain("animation-delay: 140ms");
  expect(firstCitation.getAttribute("style")).toContain("animation-delay: 200ms");
  expect(secondCitation.getAttribute("style")).toContain("animation-delay: 260ms");
  expect(unsupported?.getAttribute("style")).toContain("animation-delay: 440ms");
});

test("AskView renders the visible fallback state when the tutor response is not grounded", async () => {
  mockJson("POST", "/api/tutor/query", DEMO_FALLBACK);

  render(<AskView />);

  fireEvent.input(screen.getByLabelText(/Question/i), {
    currentTarget: { value: "What is mitosis?" },
    target: { value: "What is mitosis?" }
  });
  fireEvent.click(screen.getByRole("button", { name: /^Ask$/i }));

  // Ship 7 voice sweep: "AI synthesis unavailable" → "Couldn't synthesize an answer."
  expect(await screen.findByText(/Couldn't synthesize an answer/i)).toBeDefined();
  expect(screen.getByText(/Cell-cycle checkpoints pause progression/i)).toBeDefined();
});

test("AskView renders an in-place error and retry recovers", async () => {
  let attempts = 0;
  registerFetchHandler((url, init) => {
    if (url.pathname !== "/api/tutor/query" || init.method !== "POST") {
      return undefined;
    }

    attempts += 1;
    if (attempts === 1) {
      return jsonResponse({ detail: "temporary failure" }, 500);
    }
    return jsonResponse(DEMO_ANSWER);
  });

  render(<AskView />);

  fireEvent.input(screen.getByLabelText(/Question/i), {
    currentTarget: { value: "What is mitosis?" },
    target: { value: "What is mitosis?" }
  });
  fireEvent.click(screen.getByRole("button", { name: /^Ask$/i }));

  expect(await screen.findByText(/Could not reach the tutor service/i)).toBeDefined();

  fireEvent.click(screen.getByRole("button", { name: /Retry/i }));

  expect(await screen.findByText(/Mitosis creates two genetically identical daughter cells\./i)).toBeDefined();
});

test("AskView hydrates scoped auto-submit route params before asking", async () => {
  appShell.currentRoute.value = "/ask?q=Explain%20capex&auto=1&scope_kind=document&doc_id=doc-1";
  mockJson("GET", "/api/documents", [
    { id: "doc-1", filename: "finance.pdf", subject_name: "Finance" }
  ]);
  mockJson("GET", "/api/srs/subjects", { subjects: [] });

  render(<AskView />);

  expect(await screen.findByText(/Doc: finance\.pdf/i)).toBeDefined();
  await waitFor(() => {
    const tutorCall = getFetchCalls().find((call) => call.url.includes("/api/tutor/query"));
    expect(tutorCall).toBeDefined();
    const body = JSON.parse(String(tutorCall?.body ?? "{}"));
    expect(body).toMatchObject({
      question: "Explain capex",
      doc_id: "doc-1"
    });
  });
});

test("Ask flow navigates to the reader deep link when a citation chip is clicked", async () => {
  mockJson("POST", "/api/tutor/query", DEMO_ANSWER);
  mockJson("GET", "/api/documents/demo-doc-biology", {
    chunks: [
      {
        chunk_hash: null,
        chunk_index: 1,
        content:
          "Mitosis creates two genetically identical daughter cells and is used for growth and maintenance.",
        embedding_status: null,
        id: "demo-1",
        page_num: 1,
        provenance_json: {},
        section: "Cell division basics",
        token_count: 12
      }
    ],
    concept_options: [],
    concepts: [],
    counts: { cards: 0, chunks: 1, concepts: 0, questions: 0 },
    document: {
      concept_count: 0,
      confidence: 0.93,
      duplicate_of: null,
      extracted_at: null,
      file_type: "md",
      filename: "cell-division.md",
      id: "demo-doc-biology",
      page_count: 1,
      parser_diagnostics: {},
      parser_status: null,
      question_count: 0,
      source_hash: null,
      source_kind: null,
      status: "ready",
      storage_name: null,
      subject_name: "Biology",
      summary: "Cell division notes",
      updated_at: null,
      upload_date: null
    },
    questions: [],
    summary: "Cell division notes"
  });

  window.history.pushState({}, "", "/ask");
  render(<App />);

  fireEvent.input(screen.getByLabelText(/Question/i), {
    currentTarget: { value: "What is mitosis?" },
    target: { value: "What is mitosis?" }
  });
  fireEvent.click(screen.getByRole("button", { name: /^Ask$/i }));

  expect(await screen.findByText(/Mitosis creates two genetically identical daughter cells\./i)).toBeDefined();

  fireEvent.click(screen.getByRole("button", { name: /Cell division basics/i }));

  expect(await screen.findByText(/cell-division\.md/i)).toBeDefined();
  expect(document.querySelector('[data-chunk-id="demo-1"]')).toBeTruthy();
  expect(window.location.pathname).toBe("/reader/demo-doc-biology");
  expect(window.location.search).toBe("?node=demo-1");
});
