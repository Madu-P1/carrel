import { render, screen } from "@testing-library/preact";
import { expect, test, vi } from "vitest";

import { ErrorBoundary } from "./ErrorBoundary";

// `: never` is load-bearing. Bomb only throws, never returns; without the
// annotation TS infers `void`, which fails the JSX-component contract
// (`ComponentChildren`). vitest passes either way because esbuild strips
// types, but `pnpm typecheck` and `build:macos` reject it.
function Bomb({ message }: { message: string }): never {
  throw new Error(message);
}

test("ErrorBoundary renders children when nothing throws", () => {
  render(
    <ErrorBoundary>
      <p>still here</p>
    </ErrorBoundary>
  );
  expect(screen.getByText("still here")).toBeDefined();
});

test("ErrorBoundary swaps to the default fallback when a child throws", () => {
  // Preact logs the caught error to console.error during the catch
  // phase. Silence it so the test output stays readable.
  const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
  render(
    <ErrorBoundary>
      <Bomb message="boom" />
    </ErrorBoundary>
  );
  expect(screen.getByRole("alert")).toBeDefined();
  expect(screen.getByText(/Something went wrong/i)).toBeDefined();
  expect(screen.getByText(/boom/i)).toBeDefined();
  expect(screen.getByRole("button", { name: /Try again/i })).toBeDefined();
  consoleSpy.mockRestore();
});

test("ErrorBoundary onError is called with the caught error", () => {
  const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
  const onError = vi.fn();
  render(
    <ErrorBoundary onError={onError}>
      <Bomb message="caught" />
    </ErrorBoundary>
  );
  expect(onError).toHaveBeenCalledTimes(1);
  const [err] = onError.mock.calls[0];
  expect(err).toBeInstanceOf(Error);
  expect((err as Error).message).toBe("caught");
  consoleSpy.mockRestore();
});

test("ErrorBoundary render-function fallback receives error + reset", () => {
  const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
  render(
    <ErrorBoundary
      fallback={(error, reset) => (
        <div>
          <p>caught: {error.message}</p>
          <button type="button" onClick={reset}>retry now</button>
        </div>
      )}
    >
      <Bomb message="oops" />
    </ErrorBoundary>
  );
  expect(screen.getByText(/caught: oops/i)).toBeDefined();
  expect(screen.getByRole("button", { name: /retry now/i })).toBeDefined();
  consoleSpy.mockRestore();
});

test("ErrorBoundary auto-resets when resetKey changes", () => {
  const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
  const { rerender } = render(
    <ErrorBoundary resetKey="a">
      <Bomb message="boom1" />
    </ErrorBoundary>
  );
  expect(screen.getByRole("alert")).toBeDefined();
  // Change resetKey AND swap the child to a non-throwing one. The
  // boundary's componentDidUpdate clears its error state when the
  // key changes.
  rerender(
    <ErrorBoundary resetKey="b">
      <p>recovered</p>
    </ErrorBoundary>
  );
  expect(screen.getByText("recovered")).toBeDefined();
  consoleSpy.mockRestore();
});
