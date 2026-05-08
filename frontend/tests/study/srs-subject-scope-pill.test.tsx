import { fireEvent, render, screen } from "@testing-library/preact";
import { afterEach, describe, expect, test, vi } from "vitest";

import { SrsSubjectScopePill } from "@/features/study/components/SrsSubjectScopePill";
import type { SrsSubjectSummary } from "@/services/api/endpoints";

const SUBJECTS: SrsSubjectSummary[] = [
  { subject_name: "Biology", card_count: 20, due_count: 12 },
  { subject_name: "Chemistry", card_count: 15, due_count: 5 },
  { subject_name: "Statistics", card_count: 8, due_count: 0 },
];

describe("SrsSubjectScopePill (S-1)", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  test("collapsed pill shows the All-subjects label and total due count", () => {
    render(
      <SrsSubjectScopePill
        value={null}
        subjects={SUBJECTS}
        allDueCount={17}
        onChange={() => {}}
      />,
    );
    expect(screen.getByText(/All subjects \(17 due\)/)).toBeDefined();
    // The menu is closed initially.
    expect(screen.queryByRole("menu")).toBeNull();
  });

  test("collapsed pill shows the selected subject and its due count", () => {
    render(
      <SrsSubjectScopePill
        value="Biology"
        subjects={SUBJECTS}
        allDueCount={17}
        onChange={() => {}}
      />,
    );
    expect(screen.getByText(/Biology \(12 due\)/)).toBeDefined();
  });

  test("clicking the pill opens the menu with all subject options", () => {
    render(
      <SrsSubjectScopePill
        value={null}
        subjects={SUBJECTS}
        allDueCount={17}
        onChange={() => {}}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: /All subjects \(17 due\)/ }),
    );
    expect(screen.getByRole("menu")).toBeDefined();
    expect(screen.getAllByRole("menuitem").length).toBe(SUBJECTS.length + 1); // +1 for "All"
  });

  test("disables a subject menu item when due_count is 0 but cards exist", () => {
    render(
      <SrsSubjectScopePill
        value={null}
        subjects={SUBJECTS}
        allDueCount={17}
        onChange={() => {}}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: /All subjects \(17 due\)/ }),
    );
    const stats = screen.getByRole("menuitem", { name: /Statistics/ });
    // Statistics has card_count > 0 but due_count == 0, so it's
    // disabled — the user can't review zero cards.
    expect((stats as HTMLButtonElement).disabled).toBe(true);
  });

  test("selecting a subject fires onChange with the subject name and closes the menu", () => {
    const onChange = vi.fn();
    render(
      <SrsSubjectScopePill
        value={null}
        subjects={SUBJECTS}
        allDueCount={17}
        onChange={onChange}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: /All subjects \(17 due\)/ }),
    );
    fireEvent.click(screen.getByRole("menuitem", { name: /Biology/ }));
    expect(onChange).toHaveBeenCalledWith("Biology");
    // Menu collapses after selection.
    expect(screen.queryByRole("menu")).toBeNull();
  });

  test("selecting All subjects fires onChange with null", () => {
    const onChange = vi.fn();
    render(
      <SrsSubjectScopePill
        value="Biology"
        subjects={SUBJECTS}
        allDueCount={17}
        onChange={onChange}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /Biology \(12 due\)/ }));
    fireEvent.click(screen.getByRole("menuitem", { name: /All subjects/ }));
    expect(onChange).toHaveBeenCalledWith(null);
  });

  test("Escape closes an open menu", () => {
    render(
      <SrsSubjectScopePill
        value={null}
        subjects={SUBJECTS}
        allDueCount={17}
        onChange={() => {}}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: /All subjects \(17 due\)/ }),
    );
    expect(screen.getByRole("menu")).toBeDefined();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("menu")).toBeNull();
  });

  test("renders 'No subjects yet' empty state when subjects array is empty", () => {
    render(
      <SrsSubjectScopePill
        value={null}
        subjects={[]}
        allDueCount={0}
        onChange={() => {}}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: /All subjects \(0 due\)/ }),
    );
    expect(screen.getByText(/No subjects yet/)).toBeDefined();
  });
});
