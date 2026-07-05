import { useEffect, useRef, useState } from "preact/hooks";

import { CachetMark } from "@/cachet/CachetMark";
import { enterRoom } from "@/cachet/roomMotion";

import specimenCert from "./__fixtures__/specimen-cert.json";
import { AttestationRecord } from "./AttestationRecord";
import { coerceCertificate, verifySeal, type Certificate } from "./certificate";
import styles from "./attest.module.css";

/**
 * The Seal Bench (handoff §9): two columns — the intake (a mono textarea, a
 * file drop, and one-click specimens) beside the verdict. Hand this machine a
 * sealed record from ANY Cachet surface — the app, the loopback daemon, the
 * CLI, the companion — and it tells you, offline, whether the seal is intact,
 * then reads the record as an exhibit. No backend, no network, no trust in
 * whoever handed it over.
 *
 * The three outcomes mirror the kernel's own honesty: SEAL INTACT is stated
 * plainly (ink border, never a celebration), SEAL BROKEN is the loud danger
 * finding, and NOT A CERTIFICATE is refused with the reason.
 */

type BenchState =
  | { kind: "empty" }
  | { kind: "not_certificate"; reason: string }
  | { kind: "checked"; cert: Certificate; intact: boolean };

/** The sealed specimen, verbatim from the bundled fixture. */
function sealedSpecimen(): string {
  return JSON.stringify(specimenCert, null, 2);
}

/** A tampered specimen: the sealed fixture with one claim's state flipped
 *  AFTER sealing, so the fingerprint no longer matches the body. An honest
 *  demonstration of what the bench catches — a doctored record. */
function tamperedSpecimen(): string {
  const cert = JSON.parse(JSON.stringify(specimenCert)) as Record<string, unknown>;
  const claims = cert.claims;
  if (Array.isArray(claims) && claims.length > 0 && typeof claims[0] === "object") {
    (claims[0] as Record<string, unknown>).state = "verified";
  }
  return JSON.stringify(cert, null, 2);
}

export function SealBenchView() {
  const [state, setState] = useState<BenchState>({ kind: "empty" });
  const [raw, setRaw] = useState("");
  const fileRef = useRef<HTMLInputElement | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const resultRef = useRef<HTMLDivElement | null>(null);

  // The ruling settles in when a check lands (user-triggered, WAAPI,
  // reduced-motion aware) -- the exhibit arrives, it does not pop.
  const checkedFingerprint = state.kind === "checked" ? state.cert.fingerprint : null;
  useEffect(() => {
    if (checkedFingerprint !== null) enterRoom(resultRef.current);
  }, [checkedFingerprint]);

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

  /** A pending keystroke debounce would re-check STALE text after an explicit
   *  load renders its verdict (verdict and visible input disagreeing); cancel
   *  it whenever a load takes over. */
  function cancelPendingCheck() {
    if (debounceRef.current !== null) {
      clearTimeout(debounceRef.current);
      debounceRef.current = null;
    }
  }

  async function loadSpecimen(text: string) {
    cancelPendingCheck();
    setRaw(text);
    await checkText(text);
  }

  async function onFile(files: FileList | null | undefined) {
    const file = files && files[0];
    if (!file) return;
    cancelPendingCheck();
    const text = await file.text();
    setRaw(text);
    await checkText(text);
    if (fileRef.current) fileRef.current.value = "";
  }

  return (
    <section className={styles.bench}>
      <div className={styles.benchGrid}>
        <div className={styles.benchIntake}>
          <p className={styles.benchLede}>
            Paste a Cachet certificate. Its seal is checked here in the browser, offline, with no
            backend and no trust required.
          </p>
          <textarea
            className={styles.benchArea}
            value={raw}
            placeholder="Paste certificate JSON."
            aria-label="Certificate to check"
            spellcheck={false}
            onInput={(e) => onType((e.target as HTMLTextAreaElement).value)}
          />
          <div className={styles.benchActions}>
            <button
              type="button"
              className={styles.benchSample}
              onClick={() => void loadSpecimen(sealedSpecimen())}
            >
              Load a sealed specimen
            </button>
            <button
              type="button"
              className={styles.benchSample}
              onClick={() => void loadSpecimen(tamperedSpecimen())}
            >
              Load a tampered specimen
            </button>
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
        </div>

        <div className={styles.benchVerdictCol}>
          {state.kind === "empty" ? (
            <div className={styles.benchIdle}>
              <CachetMark size={40} className={styles.benchIdleMark} title="" />
              <div>The verdict on the certificate appears here.</div>
            </div>
          ) : null}

          {state.kind === "not_certificate" ? (
            <div className={styles.benchInvalid} role="status">
              <div className={styles.benchVerdictLabel}>NOT A CERTIFICATE</div>
              <p className={styles.benchInvalidReason}>{state.reason}</p>
            </div>
          ) : null}

          {state.kind === "checked" ? (
            <div className={styles.benchResult} ref={resultRef}>
              <div
                className={[
                  styles.benchPanel,
                  state.intact ? styles.benchPanelIntact : styles.benchPanelBroken
                ].join(" ")}
                role="status"
              >
                <div className={styles.benchVerdictLabel}>
                  {state.intact ? "SEAL INTACT" : "SEAL BROKEN"}
                </div>
                <p className={styles.benchVerdictHead}>
                  {state.intact
                    ? "The record matches its fingerprint."
                    : "The body was edited after sealing."}
                </p>
                <p className={styles.benchVerdictBody}>
                  {state.intact
                    ? "This record is exactly as the kernel issued it. Refusals in this record carry the same weight as confirmations."
                    : "The certificate body no longer matches its fingerprint. Treat every verdict inside as unverified. Request the original certificate from its issuer."}
                </p>
              </div>
              {state.intact ? <AttestationRecord cert={state.cert} /> : null}
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}
