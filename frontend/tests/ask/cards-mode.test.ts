import { expect, test } from "vitest";

import { resolveCardsMode } from "../../src/features/ask/cardsMode";

test("resolveCardsMode defaults on when the env value is unset (T12 Phase 4.3)", () => {
  expect(resolveCardsMode(undefined)).toBe(true);
});

test("resolveCardsMode stays on for the explicit string 'true'", () => {
  expect(resolveCardsMode("true")).toBe(true);
});

test("resolveCardsMode treats the literal 'false' as the single opt-out", () => {
  expect(resolveCardsMode("false")).toBe(false);
});

test("resolveCardsMode keeps cards on for any other value", () => {
  expect(resolveCardsMode("")).toBe(true);
  expect(resolveCardsMode("0")).toBe(true);
  expect(resolveCardsMode("off")).toBe(true);
});
