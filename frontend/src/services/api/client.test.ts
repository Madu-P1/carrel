import { describe, expect, test } from "vitest";

import { ApiError, apiErrorMessage } from "./client";

describe("apiErrorMessage", () => {
  test("prefers the FastAPI detail string so designed copy reaches the user", () => {
    const e = new ApiError(409, "Conflict", {
      detail: "This vault still holds records. Move or delete them first."
    });
    expect(apiErrorMessage(e)).toBe("This vault still holds records. Move or delete them first.");
  });

  test("falls back to the generic message when no detail is present", () => {
    expect(apiErrorMessage(new ApiError(500, "Internal Server Error"))).toBe(
      "API 500 Internal Server Error"
    );
  });

  test("non-Error values fall through to the caller's fallback", () => {
    expect(apiErrorMessage("boom", "Something failed.")).toBe("Something failed.");
    expect(apiErrorMessage(undefined)).toBeUndefined();
  });
});
