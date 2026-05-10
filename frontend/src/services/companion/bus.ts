/**
 * companionBus — single source of truth for pushing state into the
 * floating cube companion.
 *
 * Why a bus and not direct calls to `window.nativeCompanion`:
 *   1. Transient states (encouraging, stumped) need to fade back to
 *      the right "ground" state automatically. The ground is
 *      `focused` while a session is running, `idle` otherwise. Each
 *      caller shouldn't have to know that.
 *   2. Overlapping events shouldn't whiplash the cube — a card-again
 *      that lands during a brief celebration shouldn't kill the
 *      celebration. The bus debounces with a "transient lock" timer.
 *   3. Idle / wake from inactivity is global, not feature-local. The
 *      bus owns the inactivity timer once, on app boot.
 *
 * Consumers should not import `window.nativeCompanion` directly —
 * import the bus and use the named verbs.
 */

type CompanionState =
  | "idle"
  | "focused"
  | "thinking"
  | "citeChecking"
  | "encouraging"
  | "stumped"
  | "break"
  | "sleeping";

/** Faces of the cube, used by `pulseFace` (T2.3). The face → domain
 *  mapping is convention, not enforced:
 *    left   → library / SRS background activity
 *    right  → AI background activity in another tab
 *    back   → periodic sync (calendar, telemetry)
 *    top    → session progress milestone
 *    bottom → low-priority background work
 *    front  → reserved (active idle face; do not pulse) */
type CompanionFace = "front" | "back" | "left" | "right" | "top" | "bottom";

interface NativeCompanion {
  setState: (state: CompanionState) => void;
  setAlarm?: (active: boolean) => void;
  /** Animate a single random cell on the named face once. Optional
   *  on the bridge so older Carrel installs (pre-T2.3) don't break
   *  if the bus calls it. (T2.3.) */
  pulseFace?: (face: CompanionFace) => void;
}

function bridge(): NativeCompanion | null {
  const native = (window as unknown as { nativeCompanion?: NativeCompanion }).nativeCompanion;
  return native ?? null;
}

function push(state: CompanionState): void {
  bridge()?.setState(state);
}

let sessionActive = false;
let sleeping = false;
let alarmActive = false;
/** A transient state currently held; cleared by snapToGround when its timer fires. */
let transientTimer: number | null = null;

/** Inactivity → sleeping after this duration. From the spec: 15 minutes. */
const SLEEP_AFTER_MS = 15 * 60 * 1000;
let inactivityTimer: number | null = null;

function ground(): CompanionState {
  if (sleeping) return "sleeping";
  return sessionActive ? "focused" : "idle";
}

function snapToGround(): void {
  transientTimer = null;
  push(ground());
}

function holdTransient(state: CompanionState, durationMs: number): void {
  if (transientTimer !== null) {
    window.clearTimeout(transientTimer);
  }
  push(state);
  transientTimer = window.setTimeout(snapToGround, durationMs);
}

function clearTransient(): void {
  if (transientTimer !== null) {
    window.clearTimeout(transientTimer);
    transientTimer = null;
  }
}

function resetInactivityTimer(): void {
  if (inactivityTimer !== null) window.clearTimeout(inactivityTimer);
  inactivityTimer = window.setTimeout(() => {
    sleeping = true;
    push("sleeping");
  }, SLEEP_AFTER_MS);
}

function wakeFromSleep(): void {
  if (!sleeping) return;
  sleeping = false;
  // Snap to whatever the ground state is now (could be focused if a
  // session was running when we slept).
  snapToGround();
}

export const companion = {
  /** Pomodoro / focus / reading session has started. Cube → focused. */
  sessionStart(): void {
    sessionActive = true;
    clearTransient();
    push("focused");
  },

  /** Session ended — manual end, completion, or interruption. Cube → idle. */
  sessionEnd(): void {
    sessionActive = false;
    clearTransient();
    push("idle");
  },

  /** Tutor is generating a grounded answer. Held until thinkingEnd. */
  thinkingStart(): void {
    if (sleeping) wakeFromSleep();
    clearTransient();
    push("thinking");
  },

  /** Tutor finished — answer arrived or errored. Snap back to ground. */
  thinkingEnd(): void {
    snapToGround();
  },

  /** Verifying citations — distinct face from `thinking`, spec §5. */
  citeCheckingStart(): void {
    if (sleeping) wakeFromSleep();
    clearTransient();
    push("citeChecking");
  },
  citeCheckingEnd(): void {
    snapToGround();
  },

  /** SRS card: user said they recalled it (good / easy / hard). */
  cardGood(): void {
    if (sleeping) wakeFromSleep();
    holdTransient("encouraging", 2000);
  },

  /** SRS card: user got it wrong. Sympathy tilt for ~1s. */
  cardAgain(): void {
    if (sleeping) wakeFromSleep();
    holdTransient("stumped", 1200);
  },

  /** Pomodoro break started. Cube → break (no auto-snap; explicit end). */
  breakStart(): void {
    if (sleeping) wakeFromSleep();
    clearTransient();
    push("break");
  },
  breakEnd(): void {
    snapToGround();
  },

  /** Scheduled study session is now. Cube spins chaotically until
   *  the user taps it (Swift dispatches `carrel:companion-alarm-ack`
   *  on tap so the bus can clear its own flag). Sticky — does not
   *  auto-fade. Calling alarmStart while already alarming is a no-op. */
  alarmStart(): void {
    if (alarmActive) return;
    alarmActive = true;
    bridge()?.setAlarm?.(true);
  },
  alarmStop(): void {
    if (!alarmActive) return;
    alarmActive = false;
    bridge()?.setAlarm?.(false);
  },
  isAlarming(): boolean {
    return alarmActive;
  },

  /**
   * Signal a real background event by pulsing a single cell on the
   * named face. The cube's face → domain mapping is intentional
   * (see `CompanionFace`); pick the face that best represents the
   * signal's domain. (T2.3.)
   *
   * Per-domain examples to inspire wiring:
   *   - companionBus.signal("left")  on "library document indexed"
   *   - companionBus.signal("right") on "AI request started elsewhere"
   *   - companionBus.signal("back")  on "calendar sync ran"
   *   - companionBus.signal("top")   on "session crossed 25% / 50% / 75%"
   *
   * No-op when the bridge isn't installed (older builds, web preview).
   */
  signal(face: CompanionFace): void {
    bridge()?.pulseFace?.(face);
  },

  /**
   * Install global activity listeners that fire wake from sleeping and
   * push the cube into "sleeping" after 15 minutes of inactivity.
   * Idempotent — call once at app boot.
   */
  installIdleWatcher(): void {
    if (inactivityWatcherInstalled) return;
    inactivityWatcherInstalled = true;
    const onActivity = () => {
      if (sleeping) wakeFromSleep();
      resetInactivityTimer();
    };
    // Mousemove can be chatty; throttle by only resetting when the
    // timer is more than 30s into its window. Cheap proxy: re-arm on
    // any keydown / mousedown / wheel; for mousemove, just re-arm —
    // setTimeout reset is O(1).
    window.addEventListener("mousemove", onActivity, { passive: true });
    window.addEventListener("mousedown", onActivity, { passive: true });
    window.addEventListener("keydown", onActivity);
    window.addEventListener("wheel", onActivity, { passive: true });
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) onActivity();
    });
    resetInactivityTimer();
  },
};

let inactivityWatcherInstalled = false;
