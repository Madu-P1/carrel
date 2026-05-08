import { fireEvent, render, screen } from "@testing-library/preact";
import { afterEach, describe, expect, test, vi } from "vitest";

import { StudyFocusOverlay } from "@/features/study/components/StudyFocusOverlay";

describe("StudyFocusOverlay (S-2)", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  test("renders nothing when open=false", () => {
    render(
      <StudyFocusOverlay open={false} onClose={() => {}}>
        <div data-testid="child">card body</div>
      </StudyFocusOverlay>,
    );
    expect(screen.queryByTestId("child")).toBeNull();
  });

  test("renders children inside a dialog when open=true", () => {
    render(
      <StudyFocusOverlay open={true} onClose={() => {}}>
        <div data-testid="child">card body</div>
      </StudyFocusOverlay>,
    );
    expect(screen.getByRole("dialog")).toBeDefined();
    expect(screen.getByTestId("child")).toBeDefined();
  });

  test("renders progress and scope eyebrows when provided", () => {
    render(
      <StudyFocusOverlay
        open={true}
        onClose={() => {}}
        progress="Card 3 of 12"
        scope="Biology"
      >
        <div>body</div>
      </StudyFocusOverlay>,
    );
    expect(screen.getByText("Card 3 of 12")).toBeDefined();
    expect(screen.getByText("Biology")).toBeDefined();
  });

  test("clicking the close button fires onClose", () => {
    const onClose = vi.fn();
    render(
      <StudyFocusOverlay open={true} onClose={onClose}>
        <div>body</div>
      </StudyFocusOverlay>,
    );
    fireEvent.click(screen.getByRole("button", { name: /Exit focus mode/i }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  test("Escape key fires onClose", () => {
    const onClose = vi.fn();
    render(
      <StudyFocusOverlay open={true} onClose={onClose}>
        <div>body</div>
      </StudyFocusOverlay>,
    );
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  test("Escape does not fire onClose when overlay is closed", () => {
    const onClose = vi.fn();
    render(
      <StudyFocusOverlay open={false} onClose={onClose}>
        <div>body</div>
      </StudyFocusOverlay>,
    );
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).not.toHaveBeenCalled();
  });
});
