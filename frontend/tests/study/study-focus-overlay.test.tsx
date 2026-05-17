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

  // PR 6.1: ETA chip lives in the focus header, alongside progress
  // and scope. Pin both the show-when-supplied and hide-when-null
  // shapes so a future header refactor can't silently drop the chip.
  test("renders the eta chip when an eta string is provided", () => {
    render(
      <StudyFocusOverlay open={true} onClose={() => {}} eta="~4m left">
        <div>body</div>
      </StudyFocusOverlay>,
    );
    expect(screen.getByText("~4m left")).toBeDefined();
  });

  test("hides the eta chip when eta is null", () => {
    render(
      <StudyFocusOverlay open={true} onClose={() => {}} eta={null}>
        <div>body</div>
      </StudyFocusOverlay>,
    );
    expect(screen.queryByText(/~.+left/)).toBeNull();
  });

  // PR 6.4: streak chip mirrors the ETA chip's contract — show when
  // the parent supplies a string, hide when it's null.
  test("renders the streak chip when a streak string is provided", () => {
    render(
      <StudyFocusOverlay open={true} onClose={() => {}} streak="3 in a row">
        <div>body</div>
      </StudyFocusOverlay>,
    );
    expect(screen.getByText("3 in a row")).toBeDefined();
  });

  test("hides the streak chip when streak is null", () => {
    render(
      <StudyFocusOverlay open={true} onClose={() => {}} streak={null}>
        <div>body</div>
      </StudyFocusOverlay>,
    );
    expect(screen.queryByText(/in a row/)).toBeNull();
  });
});
