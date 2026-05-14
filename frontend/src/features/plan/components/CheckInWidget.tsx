import { useState } from "preact/hooks";

import { Stack, Text, toast } from "@/design-system";

import { planApi } from "../api/planApi";
import styles from "./CheckInWidget.module.css";

/**
 * Quick stress + energy check-in. Coach Phase 2.B UI.
 *
 * Two 1..5 scales. Pick one for each, hit "Log it". POST flows to
 * /api/plan/check-in, the coach reads recent rows on the next plan
 * refresh, and a high-stress signal collapses the routine 60-min
 * review block into a 25-min Pomodoro.
 *
 * Always visible on the Plan view in v1. We considered tying this to
 * the "Schedule it" moment but the session-start signal is fragile
 * (users don't always start sessions through Carrel) and we don't
 * want to lose the data. An ambient widget is the simplest reliable
 * collection point.
 */
export function CheckInWidget() {
  const [stress, setStress] = useState<number | null>(null);
  const [energy, setEnergy] = useState<number | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const canSubmit = stress !== null && energy !== null && !submitting;

  const handleSubmit = async () => {
    if (stress === null || energy === null || submitting) return;
    setSubmitting(true);
    try {
      await planApi.checkIn({ stress_level: stress, energy_level: energy });
      toast.success("Logged", "Coach is listening.");
      setStress(null);
      setEnergy(null);
    } catch (err) {
      toast.error("Could not log check-in", (err as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section
      className={styles.widget}
      aria-label="Stress and energy check-in"
    >
      <Stack gap={2}>
        <Stack direction="horizontal" gap={2} align="center">
          <span className={styles.eyebrow}>Check in</span>
        </Stack>
        <Text tone="secondary">
          How are you feeling right now? Coach uses this to size your
          next study block.
        </Text>
        <div className={styles.scales}>
          <Scale
            label="Stress"
            value={stress}
            onChange={setStress}
            lowHint="calm"
            highHint="slammed"
          />
          <Scale
            label="Energy"
            value={energy}
            onChange={setEnergy}
            lowHint="drained"
            highHint="sharp"
          />
        </div>
        <div className={styles.actions}>
          <button
            type="button"
            className={styles.submit}
            disabled={!canSubmit}
            onClick={handleSubmit}
          >
            {submitting ? "Logging…" : "Log it"}
          </button>
        </div>
      </Stack>
    </section>
  );
}

interface ScaleProps {
  label: string;
  value: number | null;
  onChange: (n: number) => void;
  lowHint: string;
  highHint: string;
}

/**
 * A 1..5 radio row. Native radios under the hood so keyboard nav
 * (arrow keys) and screen readers Just Work. Visual treatment is a
 * row of pill buttons; the radios themselves are sr-only.
 */
function Scale({ label, value, onChange, lowHint, highHint }: ScaleProps) {
  const name = `check-in-${label.toLowerCase()}`;
  return (
    <fieldset className={styles.scale}>
      <legend className={styles.scaleLabel}>{label}</legend>
      <div className={styles.scaleRow} role="radiogroup" aria-label={label}>
        {[1, 2, 3, 4, 5].map((n) => {
          const checked = value === n;
          const id = `${name}-${n}`;
          return (
            <label
              key={n}
              htmlFor={id}
              className={
                checked ? `${styles.pill} ${styles.pillChecked}` : styles.pill
              }
            >
              <input
                type="radio"
                id={id}
                name={name}
                value={n}
                checked={checked}
                onChange={() => onChange(n)}
                className={styles.srOnly}
              />
              {n}
            </label>
          );
        })}
      </div>
      <div className={styles.hints}>
        <span>1 = {lowHint}</span>
        <span>5 = {highHint}</span>
      </div>
    </fieldset>
  );
}
