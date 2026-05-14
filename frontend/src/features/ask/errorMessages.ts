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
    title: "The model is rate-limited right now.",
    action: "Wait a few seconds, then ask again.",
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
    title: "The model server is having trouble.",
    action: "Wait a moment, then ask again.",
  },
  http_502: {
    title: "The model server is unreachable.",
    action: "Wait a moment, then ask again.",
  },
  http_503: {
    title: "The model server is temporarily unavailable.",
    action: "Wait a moment, then ask again.",
  },
  timeout: {
    title: "The request timed out.",
    action: "Ask again, or switch to a faster provider in your .env.",
  },
  connection_error: {
    title: "Can't reach the model server.",
    action: "Check your network connection.",
  },
  missing_api_key: {
    title: "Grounded tutoring needs an API key.",
    action: "Set ANTHROPIC_API_KEY in your .env, or switch CARREL_AI_PROVIDER to ollama.",
  },
  ollama_no_api_key: {
    title: "Ollama Cloud needs a free API key.",
    action: "Create one at ollama.com/settings/keys, then set OLLAMA_API_KEY in your .env.",
  },
  grounded_tutor_disabled: {
    title: "Grounded tutoring is turned off.",
    action: "Set CARREL_AI_PROVIDER to claude or ollama in your .env.",
  },
  grounded_tutor_unavailable: {
    title: "Grounded tutoring isn't available right now.",
    action: "Check your API key or provider settings.",
  },
  claude_call_failed: {
    title: "The model request failed.",
    action: "Ask the question again.",
  },
  empty_retrieval: {
    title: "No matching passages in your library for this question.",
    action: "Rephrase, broaden the scope, or import the missing source first.",
  },
  weak_coverage: {
    title: "I can't find this cleanly in the current scope.",
    action: "Broaden the scope, sharpen the query, or skim the nearest passages below.",
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
      title: "The model server returned an error.",
      action: "Ask again, and check the log if this persists.",
      code,
    };
  }
  return {
    title: "The model request didn't complete.",
    action: "Ask the question again.",
    code,
  };
}
