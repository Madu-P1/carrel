import { fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { afterEach, expect, test } from "vitest";

import { App } from "../src/app/App";
import shellStyles from "../src/app/shell/AppShell.module.css";
import { readerState } from "../src/features/reader/state";
import { dispatchMenuCommand } from "../src/services/native/menu";
import { mockJson } from "./support/mockFetch";

async function renderAppReady() {
  // Shell tests don't care about the Dashboard content; they want a stable
  // "app has booted" marker. We navigate to /library before render so the
  // existing "No sources yet" empty-state still fires deterministically.
  window.history.pushState({}, "", "/library");
  const view = render(<App />);
  await screen.findByText(/No sources yet\./i);
  return view;
}

afterEach(() => {
  window.history.pushState({}, "", "/");
});

test("shell renders left sidebar, main content, and right panel", async () => {
  await renderAppReady();

  expect(screen.getByTestId("left-sidebar")).toBeDefined();
  expect(screen.getByTestId("main-content")).toBeDefined();
  expect(screen.getByTestId("right-panel")).toBeDefined();
});

test("shell plays cold-boot motion only before the boot flag is set", async () => {
  await renderAppReady();

  expect(screen.getByTestId("left-sidebar").className).toContain(shellStyles.bootLeftRail);
  expect(screen.getByTestId("main-content").className).toContain(shellStyles.bootMain);
  expect(screen.getByTestId("right-panel").className).toContain(shellStyles.bootRightPanel);
});

test("shell skips cold-boot motion once the body boot flag is present", async () => {
  document.body.dataset.appBooted = "true";

  await renderAppReady();

  expect(screen.getByTestId("left-sidebar").className).not.toContain(shellStyles.bootLeftRail);
  expect(screen.getByTestId("main-content").className).not.toContain(shellStyles.bootMain);
  expect(screen.getByTestId("right-panel").className).not.toContain(shellStyles.bootRightPanel);
});

test("toggle left sidebar command collapses the sidebar", async () => {
  await renderAppReady();

  const sidebar = screen.getByTestId("left-sidebar");
  expect(sidebar.getAttribute("aria-hidden")).toBe("false");

  dispatchMenuCommand("view.toggleLeftSidebar");

  await waitFor(() => {
    expect(sidebar.getAttribute("aria-hidden")).toBe("true");
  });
});

test("menu dispatch navigates to Ask route", async () => {
  await renderAppReady();

  dispatchMenuCommand("nav.ask");

  expect(await screen.findByText(/Ask a question about your sources/i)).toBeDefined();
});

test("theme toggle command cycles html theme classes", async () => {
  await renderAppReady();

  expect(document.documentElement.classList.contains("theme-dark")).toBe(true);

  dispatchMenuCommand("view.toggleTheme");
  expect(document.documentElement.classList.contains("theme-dark")).toBe(true);

  dispatchMenuCommand("view.toggleTheme");
  expect(document.documentElement.classList.contains("theme-light")).toBe(true);

  dispatchMenuCommand("view.toggleTheme");
  expect(document.documentElement.classList.contains("theme-dark")).toBe(true);
});

test("menu zoom commands update reader state", async () => {
  await renderAppReady();

  dispatchMenuCommand("view.zoomIn");
  expect(readerState.scale.value).toBeGreaterThan(1);

  dispatchMenuCommand("view.zoomReset");
  expect(readerState.scale.value).toBe(1);
});

test("meta+b keydown inside the web app does not toggle the sidebar by itself", async () => {
  await renderAppReady();

  const sidebar = screen.getByTestId("left-sidebar");
  expect(sidebar.getAttribute("aria-hidden")).toBe("false");

  fireEvent.keyDown(document.body, { key: "b", metaKey: true });

  expect(sidebar.getAttribute("aria-hidden")).toBe("false");
});

test("router renders each route without crashing", async () => {
  const cases: Array<[string, RegExp]> = [
    ["/library", /No sources yet\./i],
    ["/reader", /No source selected yet\./i],
    ["/ask", /Ask a question about your sources/i],
    // StudyView: shows the caught-up empty state when /api/srs/due returns [] (default mock).
    ["/study", /You.*caught up/i],
    ["/missing", /This workspace page does not exist yet/i]
  ];

  for (const [path, matcher] of cases) {
    window.history.pushState({}, "", path);
    const view = render(<App />);
    expect(await screen.findByText(matcher)).toBeDefined();
    view.unmount();
    await Promise.resolve();
  }
});

test("reader route deep-link populates the right panel and highlights the chunk", async () => {
  mockJson("GET", "/api/documents/doc-1", {
    chunks: [
      { content: "Mitosis creates identical daughter cells.", id: "chunk-1", page_num: 1, section: "Basics" },
      { content: "Checkpoints pause progression when DNA is damaged.", id: "chunk-2", page_num: 2, section: "Regulation" }
    ],
    concept_options: [],
    concepts: [{ description: "Cell division", id: "concept-1", name: "Mitosis" }],
    counts: { cards: 0, chunks: 2, concepts: 1, questions: 0 },
    document: {
      concept_count: 1,
      confidence: 0.93,
      filename: "biology-notes.md",
      file_type: "md",
      id: "doc-1",
      page_count: 2,
      parser_diagnostics: {},
      question_count: 0,
      status: "ready",
      summary: "",
      subject_name: "Biology"
    },
    questions: [],
    summary: "Cell-cycle notes"
  });

  window.history.pushState({}, "", "/reader/doc-1?chunk=chunk-2");
  render(<App />);

  expect(await screen.findByText(/biology-notes\.md/i)).toBeDefined();
  expect(screen.getByTestId("right-panel")).toBeDefined();
  expect(await screen.findByText(/Chunks \(2\)/i)).toBeDefined();
  expect(document.querySelector('[data-chunk-id="chunk-2"]')).toBeTruthy();
});
