/*
 * Map tutor/router error codes to user-facing messages. Source codes come
 * from services/tutor.py (grounded_tutor_*, claude_call_failed, empty_retrieval)
 * and ai/router.py + ai/ollama.py (http_<code>, timeout, connection_error,
 * missing_api_key, and SDK class names for anything unmapped).
 *
 * Voice rules per DESIGN.md:
 * - No em dashes.
 * - No filler / hedge words.
 * - Say what happened, then what the reader can do.
 */

const MESSAGES: Record<string, { title: string; action?: string }> = {
  http_429: {
    title: "The AI service is rate-limited right now.",
    action: "Wait a few seconds and try again.",
  },
  http_401: {
    title: "The Anthropic API key is missing or invalid.",
    action: "Check ANTHROPIC_API_KEY in your .env.",
  },
  http_403: {
    title: "The Anthropic API key was rejected.",
    action: "Confirm the key has permission for the selected model.",
  },
  http_500: {
    title: "The AI service is having trouble.",
    action: "Try again in a moment.",
  },
  http_502: {
    title: "The AI service is unreachable.",
    action: "Try again in a moment.",
  },
  http_503: {
    title: "The AI service is temporarily unavailable.",
    action: "Try again in a moment.",
  },
  timeout: {
    title: "The AI request timed out.",
    action: "Try again, or switch to a faster provider in your .env.",
  },
  connection_error: {
    title: "Can't reach the AI service.",
    action: "Check your network connection.",
  },
  missing_api_key: {
    title: "Grounded tutoring needs an API key.",
    action: "Set ANTHROPIC_API_KEY in your .env or switch EINSTEIN_AI_PROVIDER to ollama.",
  },
  grounded_tutor_disabled: {
    title: "Grounded tutoring is turned off.",
    action: "Set EINSTEIN_AI_PROVIDER to claude or ollama in your .env.",
  },
  grounded_tutor_unavailable: {
    title: "Grounded tutoring isn't available right now.",
    action: "Check your API key or provider settings.",
  },
  claude_call_failed: {
    title: "The AI request failed.",
    action: "Try again.",
  },
  empty_retrieval: {
    title: "No matching passages in your library for this question.",
    action: "Try a different phrasing, or add the source material to Library first.",
  },
};

export interface FriendlyError {
  title: string;
  action?: string;
  code: string;
}

export function friendlyErrorFor(code: string | undefined | null): FriendlyError | null {
  if (!code) return null;
  const mapped = MESSAGES[code];
  if (mapped) return { ...mapped, code };
  // Fallback: generic HTTP bucket if we recognize the prefix but not the code.
  if (code.startsWith("http_")) {
    return {
      title: "The AI service returned an error.",
      action: "Try again, and check the log if this persists.",
      code,
    };
  }
  return {
    title: "The AI request didn't complete.",
    action: "Try again.",
    code,
  };
}
