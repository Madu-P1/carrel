import { render, screen } from "@testing-library/preact";
import { expect, test } from "vitest";

import { ProvenanceBadge } from "./ProvenanceBadge";

test("ProvenanceBadge renders the Claude label when provider is claude", () => {
  render(<ProvenanceBadge provider="claude" />);

  expect(screen.getByText("Claude")).toBeDefined();
});

test("ProvenanceBadge renders Apple Intelligence for the afm provider", () => {
  render(<ProvenanceBadge provider="afm" />);

  expect(screen.getByText("Apple Intelligence")).toBeDefined();
});

test("ProvenanceBadge renders Ollama for the ollama provider", () => {
  render(<ProvenanceBadge provider="ollama" />);

  expect(screen.getByText("Ollama")).toBeDefined();
});

test("ProvenanceBadge falls back to Unavailable on an unknown provider", () => {
  render(<ProvenanceBadge provider="something-else" />);

  expect(screen.getByText("Unavailable")).toBeDefined();
});

test("ProvenanceBadge falls back to Unavailable when provider is empty", () => {
  render(<ProvenanceBadge provider="" />);

  expect(screen.getByText("Unavailable")).toBeDefined();
});

test("ProvenanceBadge is case-insensitive on provider name", () => {
  render(<ProvenanceBadge provider="Claude" />);

  expect(screen.getByText("Claude")).toBeDefined();
});
