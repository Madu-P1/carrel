/**
 * Resolve the build-time CARDS_MODE flag from the raw
 * `VITE_RETRIEVAL_USE_NODES` env value.
 *
 * Defaults on (T12, Phase 4.3): AskView renders the typed-node card
 * list unless the value is exactly the string "false", which is the
 * single opt-out. Any other value, including unset, keeps cards on.
 * The flag stays at the build boundary so a production bundle ships
 * exactly one renderer rather than paying for both code paths.
 */
export function resolveCardsMode(value: string | undefined): boolean {
  return value !== "false";
}
