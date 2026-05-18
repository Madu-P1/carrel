import { render, screen } from "@testing-library/preact";
import { expect, test } from "vitest";

import { LoadingBoundary } from "./LoadingBoundary";

test("LoadingBoundary renders children when not loading", () => {
  render(
    <LoadingBoundary loading={false} fallback={<p>loading...</p>}>
      <p>loaded</p>
    </LoadingBoundary>
  );
  expect(screen.getByText("loaded")).toBeDefined();
  expect(screen.queryByText("loading...")).toBeNull();
});

test("LoadingBoundary renders fallback while loading", () => {
  render(
    <LoadingBoundary loading={true} fallback={<p>loading...</p>}>
      <p>loaded</p>
    </LoadingBoundary>
  );
  expect(screen.getByText("loading...")).toBeDefined();
  expect(screen.queryByText("loaded")).toBeNull();
});

test("LoadingBoundary swaps when the loading flag flips", () => {
  const { rerender } = render(
    <LoadingBoundary loading={true} fallback={<p>loading...</p>}>
      <p>loaded</p>
    </LoadingBoundary>
  );
  expect(screen.queryByText("loaded")).toBeNull();
  rerender(
    <LoadingBoundary loading={false} fallback={<p>loading...</p>}>
      <p>loaded</p>
    </LoadingBoundary>
  );
  expect(screen.getByText("loaded")).toBeDefined();
  expect(screen.queryByText("loading...")).toBeNull();
});
