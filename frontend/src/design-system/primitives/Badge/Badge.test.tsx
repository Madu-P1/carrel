import { render, screen } from "@testing-library/preact";
import { expect, test } from "vitest";

import { Badge } from "./Badge";

test("Badge renders content", () => {
  render(<Badge>Fresh</Badge>);

  expect(screen.getByText("Fresh")).toBeDefined();
});

test("Badge supports semantic tones", () => {
  render(<Badge tone="success">Grounded</Badge>);

  expect(screen.getByText("Grounded")).toBeDefined();
});
