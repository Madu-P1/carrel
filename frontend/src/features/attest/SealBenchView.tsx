import { useRef, useState } from "preact/hooks";

import { AttestationRecord } from "./AttestationRecord";
import { coerceCertificate, verifySeal, type Certificate } from "./certificate";
import styles from "./attest.module.css";

/**
 * The Seal Bench: hand this machine a sealed record from ANY Cachet surface --
 * the app, the loopback daemon, the CLI, the companion -- and it tells you,
 * offline, whether the seal is intact, then reads the record as an exhibit.
 *
 * This is the connector the north star describes made into a room: the
 * certificate is the artifact that binds every surface, and checking one
 * requires no backend, no network, and no trust in whoever handed it over.
 * The three outcomes mirror the kernel's own honesty: an intact seal is
 * stated plainly, a broken seal is a loud oxblood finding, and anything that
 * is not a certificate is refused with the reason.
 */

type BenchState =
  | { kind: "empty" }
  | { kind: "not_certificate"; reason: string }
  | { kind: "checked"; cert: Certificate; intact: boolean };

export function SealBenchView() {
  const [state, setState] = useState<BenchState>({ kind: "empty" });
  const [raw, setRaw] = useState("");
  const fileRef = useRef<HTMLInputElement | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  async function checkText(text: string) {
    if (!text.trim()) {
      setState({ kind: "empty" });
      return;
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch {
      setState({ kind: "not_certificate", reason: "Not a certificate: the text is not JSON." });
      return;
    }
    const { cert, reason } = coerceCertificate(parsed);
    if (!cert) {
      setState({ kind: "not_certificate", reason });
      return;
    }
    setState({ kind: "checked", cert, intact: await verifySeal(cert) });
  }

  function onType(text: string) {
    // The textarea echoes instantly; the parse + digest settles 140ms behind
    // the last keystroke so typing into a large pasted record never stutters.
    setRaw(text);
    if (debounceRef.current !== null) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      debounceRef.current = null;
      void checkText(text);
    }, 140);
  }

  async function onFile(files: FileList | null | undefined) {
    const file = files && files[0];
    if (!file) return;
    const text = await file.text();
    setRaw(text);
    await checkText(text);
    if (fileRef.current) fileRef.current.value = "";
  }

  return (
    <section className={styles.bench}>
      <header className={styles.benchHead}>
        <h1 className={styles.benchTitle}>The Seal Bench</h1>
        <p className={styles.benchLede}>
          Hand this machine a sealed Cachet record, from the app, the daemon, the
          command line, or the companion, and it checks the seal right here.
          Nothing is sent anywhere.
        </p>
      </header>

      <div className={styles.benchIntake}>
        <textarea
          className={styles.benchArea}
          value={raw}
          placeholder="Paste a certificate (the JSON a Cachet surface issued)"
          aria-label="Certificate to check"
          spellcheck={false}
          onInput={(e) => onType((e.target as HTMLTextAreaElement).value)}
        />
        <label className={styles.benchFile}>
          <input
            ref={fileRef}
            type="file"
            accept=".json,application/json"
            className={styles.benchFileInput}
            onChange={(e) => void onFile((e.target as HTMLInputElement).files)}
          />
          Or open a certificate file
        </label>
      </div>

      {state.kind === "not_certificate" ? (
        <p className={styles.benchRefusal} role="status">
          {state.reason}
        </p>
      ) : null}

      {state.kind === "checked" ? (
        <div className={styles.benchResult}>
          <p
            className={[
              styles.sealVerdict,
              state.intact ? styles.sealIntact : styles.sealBroken,
            ].join(" ")}
            role="status"
          >
            {state.intact
              ? "Seal intact. This record is exactly as the kernel issued it."
              : "Seal broken. This record was changed after it was issued; nothing below can be relied on."}
          </p>
          {state.intact ? <AttestationRecord cert={state.cert} /> : null}
        </div>
      ) : null}
    </section>
  );
}
