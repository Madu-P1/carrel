import { useState } from "preact/hooks";

import {
  Badge,
  Button,
  Card,
  Icon,
  Input,
  Spinner,
  Stack,
  Tabs,
  Text,
  showToast
} from "@/design-system";
import type { ProviderAvailability } from "@/services/api/endpoints";

import { useAiSettings } from "./hooks/useAiSettings";
import styles from "./SettingsView.module.css";

/*
 * Settings — AI provider selector.
 *
 * Statically imported (App.tsx wires it into both routers): preact/compat
 * Suspense is broken under the bundled file:// shell, so no lazy()/Suspense
 * here — see the App.tsx header comment.
 *
 * Layout: heading + explainer, a provider picker (Tabs — there is no
 * RadioGroup primitive), then one card per provider showing the live
 * availability verdict from `/api/settings/ai`'s `availability` map.
 */

/** Picker options. `auto`/`off` are valid persisted values but are not
 *  provider cards — they get their own picker entries so the current
 *  value is always representable. */
const PICKER_TABS = [
  { id: "auto", label: "Automatic" },
  { id: "claude", label: "Claude" },
  { id: "ollama", label: "Ollama" },
  { id: "afm", label: "Apple Intelligence" },
  { id: "off", label: "Off" }
];

/** Deep link to the macOS Apple Intelligence / Siri settings pane. The
 *  scheme is best-effort — if it does not resolve, the card always also
 *  shows the guidance text as a fallback. */
const APPLE_INTELLIGENCE_SETTINGS_URL =
  "x-apple.systempreferences:com.apple.Siri-Settings.extension";

type AvailabilityState = "available" | "configured" | "unavailable";

function availabilityState(verdict: ProviderAvailability): AvailabilityState {
  if (verdict.available) return "available";
  if (verdict.configured) return "configured";
  return "unavailable";
}

function StatusBadge({ verdict }: { verdict: ProviderAvailability }) {
  const state = availabilityState(verdict);
  if (state === "available") {
    return <Badge tone="success">Available</Badge>;
  }
  if (state === "configured") {
    return <Badge tone="warning">Configured, unavailable</Badge>;
  }
  return <Badge tone="neutral">Not configured</Badge>;
}

interface ProviderCardProps {
  title: string;
  verdict: ProviderAvailability;
  /** When set, the card is the active provider and gets an accent ring. */
  selected: boolean;
  children?: import("preact").ComponentChildren;
}

function ProviderCard({ title, verdict, selected, children }: ProviderCardProps) {
  return (
    <Card
      className={[styles.card, selected ? styles.cardSelected : ""]
        .filter(Boolean)
        .join(" ")}
      padding="md"
      data-testid={`provider-card-${verdict.kind}`}
    >
      <Stack gap={3}>
        <div className={styles.cardHead}>
          <Text variant="h3" weight="semibold">
            {title}
          </Text>
          <StatusBadge verdict={verdict} />
        </div>
        <Text tone="secondary">{verdict.detail}</Text>
        {children}
      </Stack>
    </Card>
  );
}

/** Claude card — API key entry. The key value is write-only: the input
 *  starts empty every render and `key_set` drives a "Key saved" note. */
function ClaudeCard({
  verdict,
  selected,
  keySet,
  keyValid,
  saving,
  onSaveKey
}: {
  verdict: ProviderAvailability;
  selected: boolean;
  keySet: boolean;
  keyValid: boolean | null;
  saving: boolean;
  /** Resolves once the save POST settles (success or failure). The card
   *  clears its draft on success so the raw key never lingers in the
   *  input value. */
  onSaveKey: (key: string) => Promise<unknown>;
}) {
  const [draft, setDraft] = useState("");

  let keyStatus: string | null = null;
  if (keySet) {
    if (keyValid === true) keyStatus = "Key saved and verified.";
    else if (keyValid === false) keyStatus = "Key saved, but Anthropic rejected it.";
    else keyStatus = "Key saved (not yet checked).";
  }

  return (
    <ProviderCard title="Claude" verdict={verdict} selected={selected}>
      <Stack gap={2}>
        <Input
          label="Anthropic API key"
          type="password"
          data-testid="claude-key-input"
          placeholder={keySet ? "Enter a new key to replace the saved one" : "sk-ant-…"}
          helpText="Stored in the macOS Keychain — never written to disk in plain text."
          value={draft}
          onInput={(event) =>
            setDraft((event.currentTarget as HTMLInputElement).value)
          }
        />
        {keyStatus ? (
          <Text tone="tertiary" variant="caption" data-testid="claude-key-status">
            {keyStatus}
          </Text>
        ) : null}
        <Stack direction="horizontal" gap={2}>
          <Button
            variant="primary"
            isLoading={saving}
            disabled={draft.trim().length === 0}
            onClick={() => {
              // Clear the draft once the save resolves so the raw key
              // never sits in the input value (a controlled-component
              // leak the "never render the key" rule is about).
              void onSaveKey(draft.trim()).then(() => setDraft(""));
            }}
          >
            Save key
          </Button>
          {keySet ? (
            <Button
              variant="ghost"
              disabled={saving}
              onClick={() => {
                void onSaveKey("").then(() => setDraft(""));
              }}
            >
              Clear key
            </Button>
          ) : null}
        </Stack>
      </Stack>
    </ProviderCard>
  );
}

/** Apple Intelligence card — affordance depends on the `error_code`. */
function AppleIntelligenceCard({
  verdict,
  selected
}: {
  verdict: ProviderAvailability;
  selected: boolean;
}) {
  const code = verdict.error_code;

  return (
    <ProviderCard title="Apple Intelligence" verdict={verdict} selected={selected}>
      {code === "apple_intelligence_not_enabled" ? (
        <Stack gap={2}>
          <Button
            variant="secondary"
            leadingIcon={<Icon name="settings" />}
            onClick={() => {
              // Best-effort deep link. The guidance Text below is the
              // fallback if the scheme does not resolve on this macOS.
              window.location.href = APPLE_INTELLIGENCE_SETTINGS_URL;
            }}
          >
            Open System Settings
          </Button>
          <Text tone="tertiary" variant="caption">
            Turn on Apple Intelligence in System Settings, then return here.
            If the button does nothing, open System Settings and search for
            &ldquo;Apple Intelligence &amp; Siri&rdquo;.
          </Text>
        </Stack>
      ) : null}
      {code === "model_not_ready" ? (
        <Text tone="tertiary" variant="caption">
          Apple Intelligence is enabled, but the on-device model is still
          downloading. This usually takes 1–30 minutes — leave the Mac
          awake and check back.
        </Text>
      ) : null}
      {code === "device_not_eligible" || code === "bridge_missing" ? (
        <Text tone="tertiary" variant="caption">
          {code === "device_not_eligible"
            ? "This Mac does not support Apple Intelligence."
            : "The Apple Intelligence bridge is missing from this build."}
        </Text>
      ) : null}
    </ProviderCard>
  );
}

/** Ollama card — purely a status surface; the detail string already
 *  carries the `ollama serve` hint when unreachable. */
function OllamaCard({
  verdict,
  selected
}: {
  verdict: ProviderAvailability;
  selected: boolean;
}) {
  return <ProviderCard title="Ollama" verdict={verdict} selected={selected} />;
}

function SettingsSkeleton() {
  return (
    <div className={styles.loadingRow} data-testid="settings-loading">
      <Spinner label="Loading AI settings" size={24} />
      <Text tone="secondary">Loading AI settings…</Text>
    </div>
  );
}

export function SettingsView() {
  const { data, loading, error, saving, refetch, save } = useAiSettings();
  const aiSettings = data.value;

  // afm is the one provider that can be un-selectable: when the device
  // cannot run it at all, picking it would persist a dead choice.
  const afmSelectable =
    aiSettings === undefined ||
    !(
      aiSettings.availability.afm.error_code === "device_not_eligible" ||
      aiSettings.availability.afm.error_code === "bridge_missing"
    );

  const handlePickProvider = (provider: string) => {
    if (!aiSettings) return;
    if (provider === aiSettings.provider) return;
    if (provider === "afm" && !afmSelectable) return;
    save({ provider })
      .then(() => {
        showToast({ title: `Provider set to ${provider}.`, kind: "success" });
      })
      .catch((caught) => {
        showToast({
          title: "Could not switch provider.",
          description: caught instanceof Error ? caught.message : undefined,
          kind: "error"
        });
      });
  };

  // Returns the save promise so ClaudeCard can clear its draft on
  // success. On failure the promise rejects — the card keeps the draft
  // so the user can retry without re-typing the key.
  const handleSaveKey = (key: string): Promise<unknown> => {
    // Empty string is the explicit "clear my key" path.
    return save({ anthropic_key: key }).then(
      (next) => {
        if (key === "") {
          showToast({ title: "Claude API key cleared.", kind: "info" });
        } else if (next.key_valid === false) {
          showToast({
            title: "Key saved, but Anthropic rejected it.",
            kind: "warning"
          });
        } else {
          showToast({ title: "Claude API key saved.", kind: "success" });
        }
        return next;
      },
      (caught) => {
        showToast({
          title: "Could not save the API key.",
          description: caught instanceof Error ? caught.message : undefined,
          kind: "error"
        });
        // Re-throw so the card's `.then(clear)` does not fire on failure.
        throw caught;
      }
    );
  };

  return (
    <Stack className={styles.container} gap={6}>
      <header className={styles.header}>
        <div className={styles.headerCopy}>
          <span className={styles.eyebrow}>Settings</span>
          <h1 className={styles.heading}>AI provider.</h1>
          <Text tone="secondary">
            Choose which model answers your questions. Carrel can run on
            Claude (cloud), Ollama (local), or Apple Intelligence
            (on-device). &ldquo;Automatic&rdquo; picks the best available;
            &ldquo;Off&rdquo; disables AI entirely.
          </Text>
        </div>
      </header>

      {loading.value && !aiSettings ? <SettingsSkeleton /> : null}

      {error.value && !aiSettings ? (
        <Card padding="md">
          <Stack gap={3}>
            <Text tone="secondary">Could not load AI settings.</Text>
            <Stack direction="horizontal" gap={2}>
              <Button variant="secondary" onClick={() => void refetch()}>
                Try again
              </Button>
            </Stack>
          </Stack>
        </Card>
      ) : null}

      {aiSettings ? (
        <Stack gap={5}>
          <Stack gap={2}>
            <Text variant="h3" weight="semibold">
              Active provider
            </Text>
            <Tabs
              ariaLabel="AI provider"
              items={PICKER_TABS.map((tab) => ({
                ...tab,
                disabled: tab.id === "afm" && !afmSelectable
              }))}
              value={aiSettings.provider}
              onChange={handlePickProvider}
            />
          </Stack>

          <Stack gap={3}>
            <ClaudeCard
              verdict={aiSettings.availability.claude}
              selected={aiSettings.provider === "claude"}
              keySet={aiSettings.key_set}
              keyValid={aiSettings.key_valid}
              saving={saving.value}
              onSaveKey={handleSaveKey}
            />
            <OllamaCard
              verdict={aiSettings.availability.ollama}
              selected={aiSettings.provider === "ollama"}
            />
            <AppleIntelligenceCard
              verdict={aiSettings.availability.afm}
              selected={aiSettings.provider === "afm"}
            />
          </Stack>
        </Stack>
      ) : null}
    </Stack>
  );
}
