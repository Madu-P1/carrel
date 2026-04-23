import { render, screen } from "@testing-library/preact";
import { expect, test } from "vitest";

import { Skeleton, SkeletonGroup } from "./Skeleton";

test("Skeleton renders with default text shape and no hard crash", () => {
  const { container } = render(<Skeleton />);
  const el = container.firstElementChild as HTMLElement;
  expect(el).toBeDefined();
  expect(el.className).toMatch(/shape-text/);
  // Skeletons are decorative — announcement is the SkeletonGroup's job.
  expect(el.getAttribute("aria-hidden")).toBe("true");
});

test("Skeleton respects shape + width + height overrides", () => {
  const { container } = render(<Skeleton shape="circle" width={48} height={48} />);
  const el = container.firstElementChild as HTMLElement;
  expect(el.className).toMatch(/shape-circle/);
  expect(el.style.width).toBe("48px");
  expect(el.style.height).toBe("48px");
});

test("Skeleton static prop disables the shimmer animation", () => {
  const { container } = render(<Skeleton static />);
  const el = container.firstElementChild as HTMLElement;
  // The class is present; CSS handles the animation: none rule.
  expect(el.className).toMatch(/static/);
});

test("SkeletonGroup renders the sr-only label and its children", () => {
  render(
    <SkeletonGroup label="Loading the Reader">
      <Skeleton />
      <Skeleton shape="text-sm" />
    </SkeletonGroup>
  );
  // The label text is visually hidden but still in the DOM for AT.
  expect(screen.getByText("Loading the Reader")).toBeDefined();
});
