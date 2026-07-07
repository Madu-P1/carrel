import { render, screen } from "@testing-library/preact";
import { describe, expect, test } from "vitest";

import { ProviderQualityGateBanner } from "../../src/features/shared/ProviderQualityGateBanner";

describe("ProviderQualityGateBanner", () => {
  test("renders the surface name in the lead sentence", () => {
    render(<ProviderQualityGateBanner provider="afm" surface="verification" />);

    expect(
      screen.getByRole("heading", { name: /Claude is required for verification/i })
    ).toBeDefined();
  });

  test("names the active provider so the user sees what's serving traffic", () => {
    render(<ProviderQualityGateBanner provider="afm" surface="grounded answers" />);

    expect(screen.getByText(/Apple Intelligence/)).toBeDefined();
  });

  test("falls back to 'the active provider' when provider is empty", () => {
    render(<ProviderQualityGateBanner provider="" surface="verification" />);

    expect(screen.getByText(/the active provider/)).toBeDefined();
  });

  test("renders the ANTHROPIC_API_KEY remediation step", () => {
    render(<ProviderQualityGateBanner provider="afm" surface="verification" />);

    expect(screen.getByText("ANTHROPIC_API_KEY")).toBeDefined();
  });

  test("uses role=alert so screen readers announce on mount", () => {
    render(<ProviderQualityGateBanner provider="afm" surface="verification" />);

    expect(screen.getByRole("alert")).toBeDefined();
  });

  test("has no dismiss button (policy: must stay visible until provider is fixed)", () => {
    render(<ProviderQualityGateBanner provider="afm" surface="verification" />);

    expect(screen.queryByRole("button")).toBeNull();
  });
});
