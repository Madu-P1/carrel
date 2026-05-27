import { render, screen } from "@testing-library/preact";
import { describe, expect, test } from "vitest";

import { AnswerSummary } from "../../src/features/ask/components/AnswerSummary";
import {
  DEMO_ANSWER,
  DEMO_PROVIDER_GATE_REJECTED,
} from "../../src/features/ask/fixtures/grounded-answer.fixture";
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

describe("AnswerSummary provenance badge", () => {
  test("renders the ProvenanceBadge when provider is set", () => {
    render(
      <AnswerSummary
        summary={DEMO_ANSWER.answer}
        citations={DEMO_ANSWER.citations}
        cacheHit={DEMO_ANSWER.cache_hit}
        latencyMs={DEMO_ANSWER.latency_ms}
        model={DEMO_ANSWER.model}
        provider="claude"
      />
    );

    expect(screen.getByText("Claude")).toBeDefined();
  });

  test("omits the ProvenanceBadge when provider is empty", () => {
    render(
      <AnswerSummary
        summary={DEMO_ANSWER.answer}
        citations={DEMO_ANSWER.citations}
        cacheHit={DEMO_ANSWER.cache_hit}
        latencyMs={DEMO_ANSWER.latency_ms}
        model={DEMO_ANSWER.model}
        provider=""
      />
    );

    expect(screen.queryByText("Claude")).toBeNull();
    expect(screen.queryByText("Apple Intelligence")).toBeNull();
    expect(screen.queryByText("Unavailable")).toBeNull();
  });
});

describe("DEMO_PROVIDER_GATE_REJECTED fixture", () => {
  test("matches the fail-loud contract", () => {
    expect(DEMO_PROVIDER_GATE_REJECTED.error).toBe("provider_below_quality_bar");
    expect(DEMO_PROVIDER_GATE_REJECTED.grounded).toBe(false);
    expect(DEMO_PROVIDER_GATE_REJECTED.answer).toBe("");
    expect(DEMO_PROVIDER_GATE_REJECTED.model).toBe("");
    expect(DEMO_PROVIDER_GATE_REJECTED.provider).toBe("afm");
  });
});
