import { fireEvent, render, screen } from "@testing-library/preact";
import { afterEach, describe, expect, test, vi } from "vitest";

import { RatingRow } from "@/features/study/components/RatingRow";

const RATINGS = [
  { rating: "again" as const, label: "Again", key: "1" },
  { rating: "hard" as const, label: "Hard", key: "2" },
  { rating: "good" as const, label: "Good", key: "3" },
  { rating: "easy" as const, label: "Easy", key: "4" },
];

describe("RatingRow (S-2)", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  test("renders one button per rating with the keyboard shortcut visible", () => {
    render(<RatingRow ratings={RATINGS} submitting={false} onSelect={() => {}} />);
    expect(screen.getAllByRole("button").length).toBe(4);
    expect(screen.getByText("Again")).toBeDefined();
    expect(screen.getByText("Easy")).toBeDefined();
    // Number badges (1-4) are rendered for affordance.
    for (const key of ["1", "2", "3", "4"]) {
      expect(screen.getByText(key)).toBeDefined();
    }
  });

  test("clicking a rating fires onSelect with that rating's value", () => {
    const onSelect = vi.fn();
    render(<RatingRow ratings={RATINGS} submitting={false} onSelect={onSelect} />);
    fireEvent.click(screen.getByText("Good"));
    expect(onSelect).toHaveBeenCalledWith("good");
  });

  test("submitting=true disables all rating buttons", () => {
    render(<RatingRow ratings={RATINGS} submitting={true} onSelect={() => {}} />);
    for (const button of screen.getAllByRole("button")) {
      expect((button as HTMLButtonElement).disabled).toBe(true);
    }
  });

  test("data-rating attribute is set on each button so e2e tests can target", () => {
    render(<RatingRow ratings={RATINGS} submitting={false} onSelect={() => {}} />);
    expect(
      document.querySelector('[data-rating="again"]'),
    ).not.toBeNull();
    expect(
      document.querySelector('[data-rating="easy"]'),
    ).not.toBeNull();
  });

  test("aria-keyshortcuts is set so screen readers announce the keyboard hint", () => {
    render(<RatingRow ratings={RATINGS} submitting={false} onSelect={() => {}} />);
    const goodButton = screen.getByText("Good").closest("button");
    expect(goodButton?.getAttribute("aria-keyshortcuts")).toBe("3");
  });
});
