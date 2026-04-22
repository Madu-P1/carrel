import { render, screen } from "@testing-library/preact";
import { expect, test } from "vitest";

import { Spinner } from "./Spinner";

test("Spinner renders as a status indicator", () => {
  render(<Spinner />);

  expect(screen.getByRole("status")).toBeDefined();
});

test("Spinner exposes the configured label", () => {
  render(<Spinner label="Syncing" size={24} />);

  expect(screen.getByLabelText("Syncing")).toBeDefined();
});
