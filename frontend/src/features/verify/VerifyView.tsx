import { useEffect, useState } from "preact/hooks";

import { Button, Spinner, Stack, Text } from "@/design-system";

import { useVerify } from "./useVerify";
import { VerifyResults } from "./VerifyResults";
import styles from "./VerifyView.module.css";

const SAMPLE_DRAFT =
  "The Supreme Court held in 576 U.S. 644 that same-sex couples have a fundamental right to marry. " +
  "This ruling extended the equal-protection clause to marriage recognition across all states.";

/**
 * Carrel's verify surface: a composer (header + draft field + Verify button) above
 * the verdict column. The verification machine lives in `useVerify` and the verdict
 * render in `VerifyResults`, so this is a thin facade — the same two pieces the
 * Cachet lectern composes with its own sheet. `briefId` opens a saved brief
 * (re-hydrate, no re-verify); the live flow leaves it null.
 */
export function VerifyView({ briefId }: { briefId?: string | null } = {}) {
  const [draft, setDraft] = useState("");
  const engine = useVerify({ briefId });

  // Opening a saved brief hydrates the draft in the engine; seed the editable
  // composer from it so the reopened text is shown and can be re-verified.
  useEffect(() => {
    if (engine.hydratedDraft !== null) setDraft(engine.hydratedDraft);
  }, [engine.hydratedDraft]);

  return (
    <div className={[styles.root, styles.verifyScope].join(" ")}>
      <header className={styles.header}>
        <h1 className={styles.title}>Verify your draft.</h1>
        <Text className={styles.subtitle}>
          Paste a brief, memo, or claim. Every statement is checked against the sources you provide,
          and any cited cases are checked for existence and holding.
        </Text>
      </header>

      <div className={styles.draftField}>
        <label className={styles.draftLabel} htmlFor="verify-draft-input">
          Draft
        </label>
        <textarea
          id="verify-draft-input"
          className={styles.draftInput}
          value={draft}
          placeholder={SAMPLE_DRAFT}
          onInput={(e) => setDraft((e.target as HTMLTextAreaElement).value)}
          disabled={engine.loading || engine.hydrating}
        />
      </div>

      <div className={styles.actionsRow}>
        <Button
          onClick={() => void engine.verify(draft)}
          disabled={engine.loading || engine.hydrating || !draft.trim()}
          type="button"
        >
          {engine.loading ? (
            <Stack direction="horizontal" align="center" gap={2}>
              <Spinner size={16} />
              <span>Verifying…</span>
            </Stack>
          ) : (
            "Verify the draft"
          )}
        </Button>
      </div>

      <VerifyResults engine={engine} draft={draft} />
    </div>
  );
}
