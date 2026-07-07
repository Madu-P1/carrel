import { Stack, Text } from "@/design-system";

import styles from "./ProviderQualityGateBanner.module.css";

const PROVIDER_LABELS: Record<string, string> = {
  claude: "Claude",
  afm: "Apple Intelligence",
  ollama: "Ollama",
  null: "No provider",
};

function describeProvider(provider: string): string {
  const key = (provider ?? "").trim().toLowerCase();
  if (!key) return "the active provider";
  return PROVIDER_LABELS[key] ?? `the ${key} provider`;
}

export interface ProviderQualityGateBannerProps {
  /** Provider that the backend reported on the fail-loud response. */
  provider: string;
  /** Surface name shown in the lead sentence ("verification", "grounded answer"). */
  surface: string;
}

/**
 * Non-dismissable banner shown when a high-stakes surface (Ask, Verify)
 * receives a fail-loud response with `error === "provider_below_quality_bar"`.
 *
 * The backend's fail-loud gate at `ai.providers.ensure_provider_allowed`
 * fires when the active provider is not Claude for a high-stakes
 * request_kind. This banner explains the gate and points the user at
 * the remediation: set ANTHROPIC_API_KEY in their environment.
 *
 * Rendered with role="alert" so screen readers announce it on mount.
 * Has no close button: the policy decision (2026-05-27) requires the
 * gate stay visible until the user fixes the underlying provider
 * configuration.
 */
export function ProviderQualityGateBanner({
  provider,
  surface,
}: ProviderQualityGateBannerProps) {
  const providerName = describeProvider(provider);
  return (
    <section className={styles.root} role="alert" aria-live="assertive">
      <Stack gap={3}>
        <Stack gap={1}>
          <Text as="h2" variant="h3" weight="bold" className={styles.title}>
            Claude is required for {surface}.
          </Text>
          <Text tone="secondary">
            Cachet routes {surface} through the Claude API because the
            stakes are too high for a fallback model. Right now Cachet
            is using {providerName}, so the engine refused to answer
            rather than risk a hollow or hallucinated result.
          </Text>
        </Stack>
        <div className={styles.remediation}>
          <Text variant="body" weight="semibold" className={styles.remediationTitle}>
            How to enable
          </Text>
          <ol className={styles.steps}>
            <li>
              Set <code className={styles.code}>ANTHROPIC_API_KEY</code> in
              your environment (a <code className={styles.code}>.env</code>
              {" "}file at the repo root works).
            </li>
            <li>Restart Cachet so the new key is picked up at boot.</li>
          </ol>
        </div>
      </Stack>
    </section>
  );
}
