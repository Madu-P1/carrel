import { fireEvent, render, screen } from "@testing-library/preact";
import { afterEach, describe, expect, test, vi } from "vitest";

import { FlipCard } from "@/features/study/components/FlipCard";

describe("FlipCard (S-2)", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  test("renders both faces (front + back) so backface visibility can do the work", () => {
    render(
      <FlipCard
        flipped={false}
        front={<span data-testid="front">QUESTION</span>}
        back={<span data-testid="back">ANSWER</span>}
      />,
    );
    expect(screen.getByTestId("front")).toBeDefined();
    expect(screen.getByTestId("back")).toBeDefined();
  });

  test("aria-pressed reflects the flipped state", () => {
    const { rerender } = render(
      <FlipCard flipped={false} front={<span>F</span>} back={<span>B</span>} />,
    );
    expect(screen.getByRole("button").getAttribute("aria-pressed")).toBe("false");
    rerender(
      <FlipCard flipped={true} front={<span>F</span>} back={<span>B</span>} />,
    );
    expect(screen.getByRole("button").getAttribute("aria-pressed")).toBe("true");
  });

  test("clicking the card fires onFlip", () => {
    const onFlip = vi.fn();
    render(
      <FlipCard
        flipped={false}
        onFlip={onFlip}
        front={<span>F</span>}
        back={<span>B</span>}
      />,
    );
    fireEvent.click(screen.getByRole("button"));
    expect(onFlip).toHaveBeenCalledTimes(1);
  });

  test("Space and Enter keys both fire onFlip", () => {
    const onFlip = vi.fn();
    render(
      <FlipCard
        flipped={false}
        onFlip={onFlip}
        front={<span>F</span>}
        back={<span>B</span>}
      />,
    );
    const card = screen.getByRole("button");
    fireEvent.keyDown(card, { key: " " });
    fireEvent.keyDown(card, { key: "Enter" });
    expect(onFlip).toHaveBeenCalledTimes(2);
  });

  test("aria-hidden flips between the faces so AT only announces the visible side", () => {
    const { rerender } = render(
      <FlipCard flipped={false} front={<span data-testid="f">F</span>} back={<span data-testid="b">B</span>} />,
    );
    // Front visible (flipped=false): front aria-hidden=false, back aria-hidden=true
    expect(screen.getByTestId("f").parentElement?.getAttribute("aria-hidden")).toBe("false");
    expect(screen.getByTestId("b").parentElement?.getAttribute("aria-hidden")).toBe("true");
    rerender(
      <FlipCard flipped={true} front={<span data-testid="f">F</span>} back={<span data-testid="b">B</span>} />,
    );
    expect(screen.getByTestId("f").parentElement?.getAttribute("aria-hidden")).toBe("true");
    expect(screen.getByTestId("b").parentElement?.getAttribute("aria-hidden")).toBe("false");
  });
});
