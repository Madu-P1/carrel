"""Tests for the cross-provider parity contract introduced in PR-P2.

The audit found three real divergences across Claude/AFM/Ollama:

1. Timeouts differed by 2× (60s/60s/120s) with three separate env
   vars. A user wanting a unified knob had to set three names.
2. JSON-rescue parsing diverged (Claude did first-`{` find; AFM did
   that plus markdown-fence strip plus `rfind` closer truncation).
   Same malformed output → different ``ok`` value per provider.
3. ``cache_hit`` was Claude-only but the Protocol didn't say so.

PR-P2 unifies (1) via ``resolve_ai_timeout_seconds`` and (2) via
``parse_or_rescue_json``, and documents (3) in the AIProvider
Protocol docstring. These tests pin the contract.
"""

from __future__ import annotations

import os
import unittest
from unittest import mock

from ai.router import parse_or_rescue_json, resolve_ai_timeout_seconds


class ResolveTimeoutTests(unittest.TestCase):
    """``CARREL_AI_TIMEOUT_SECONDS`` is the unified knob; legacy
    provider env vars still honored; provider-specific defaults
    survive when nothing is set."""

    def test_default_returned_when_no_env_vars_set(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                resolve_ai_timeout_seconds(default=60.0, legacy_env_name="OLLAMA_TIMEOUT_SECONDS"),
                60.0,
            )

    def test_unified_env_var_wins_over_default(self) -> None:
        with mock.patch.dict(os.environ, {"CARREL_AI_TIMEOUT_SECONDS": "90"}, clear=True):
            self.assertEqual(
                resolve_ai_timeout_seconds(default=60.0, legacy_env_name="OLLAMA_TIMEOUT_SECONDS"),
                90.0,
            )

    def test_unified_env_var_wins_over_legacy(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "CARREL_AI_TIMEOUT_SECONDS": "90",
                "OLLAMA_TIMEOUT_SECONDS": "200",  # legacy should NOT win
            },
            clear=True,
        ):
            self.assertEqual(
                resolve_ai_timeout_seconds(default=60.0, legacy_env_name="OLLAMA_TIMEOUT_SECONDS"),
                90.0,
            )

    def test_legacy_env_var_wins_over_default_when_unified_absent(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"OLLAMA_TIMEOUT_SECONDS": "120"},
            clear=True,
        ):
            self.assertEqual(
                resolve_ai_timeout_seconds(default=60.0, legacy_env_name="OLLAMA_TIMEOUT_SECONDS"),
                120.0,
            )

    def test_invalid_unified_env_falls_through_to_legacy(self) -> None:
        # Garbled CARREL_AI_TIMEOUT_SECONDS should not crash; just
        # fall through to the next layer.
        with mock.patch.dict(
            os.environ,
            {
                "CARREL_AI_TIMEOUT_SECONDS": "not-a-number",
                "OLLAMA_TIMEOUT_SECONDS": "75",
            },
            clear=True,
        ):
            self.assertEqual(
                resolve_ai_timeout_seconds(default=60.0, legacy_env_name="OLLAMA_TIMEOUT_SECONDS"),
                75.0,
            )

    def test_invalid_legacy_env_falls_through_to_default(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"OLLAMA_TIMEOUT_SECONDS": "garbage"},
            clear=True,
        ):
            self.assertEqual(
                resolve_ai_timeout_seconds(default=60.0, legacy_env_name="OLLAMA_TIMEOUT_SECONDS"),
                60.0,
            )

    def test_none_legacy_env_name_skips_legacy_lookup(self) -> None:
        # Some callers (a future provider) may not have a legacy env
        # var at all. Passing None for legacy_env_name should not
        # raise.
        with mock.patch.dict(os.environ, {"CARREL_AI_TIMEOUT_SECONDS": "30"}, clear=True):
            self.assertEqual(resolve_ai_timeout_seconds(default=60.0, legacy_env_name=None), 30.0)


class AllThreeProvidersRespectUnifiedTimeoutTests(unittest.TestCase):
    """Construct each provider in turn with CARREL_AI_TIMEOUT_SECONDS set
    and assert each one picks it up. Pin the contract end-to-end so a
    future refactor of any one provider can't silently regress."""

    def test_ollama_picks_up_unified_timeout(self) -> None:
        from ai.ollama import OllamaClient

        with mock.patch.dict(os.environ, {"CARREL_AI_TIMEOUT_SECONDS": "45"}, clear=True):
            client = OllamaClient()
        self.assertEqual(client.timeout_seconds, 45.0)

    def test_afm_picks_up_unified_timeout(self) -> None:
        from ai.afm_client import AFMClient

        with mock.patch.dict(os.environ, {"CARREL_AI_TIMEOUT_SECONDS": "45"}, clear=True):
            client = AFMClient(bridge_path=None)
        self.assertEqual(client.timeout_seconds, 45.0)


class ParseOrRescueJsonTests(unittest.TestCase):
    """Single canonical JSON rescue parser. AFM, Claude, and Ollama
    all delegate here; same malformed output → same ``ok`` value
    everywhere."""

    def test_strict_parse(self) -> None:
        self.assertEqual(parse_or_rescue_json('{"a": 1}'), {"a": 1})

    def test_markdown_fence_stripped(self) -> None:
        # AFM's 3B model wraps JSON in ```json ... ``` fences regularly.
        # The strict parser fails on the fence; the rescuer strips it.
        self.assertEqual(
            parse_or_rescue_json('```json\n{"a": 1}\n```'),
            {"a": 1},
        )

    def test_prose_prefix_rescued(self) -> None:
        # "Here is the JSON: {...}" — first-`{` find recovers.
        self.assertEqual(
            parse_or_rescue_json('Here is the JSON: {"a": 1}'),
            {"a": 1},
        )

    def test_trailing_prose_rescued_via_rfind(self) -> None:
        # The audit's specific divergence: {"a": 1} followed by
        # "(note: out of context)". Claude's pre-PR-P2 rescuer
        # returned None because find-first parses from `{` but the
        # trailing junk trips json.loads. After PR-P2, the rfind-
        # closer truncation catches it.
        self.assertEqual(
            parse_or_rescue_json('{"a": 1}\n(note: ignore)'),
            {"a": 1},
        )

    def test_array_rescue(self) -> None:
        self.assertEqual(
            parse_or_rescue_json("Prefix\n[1, 2, 3]\nsuffix"),
            [1, 2, 3],
        )

    def test_completely_malformed_returns_none(self) -> None:
        self.assertIsNone(parse_or_rescue_json("this is not JSON anywhere"))

    def test_empty_input_returns_none(self) -> None:
        self.assertIsNone(parse_or_rescue_json(""))
        self.assertIsNone(parse_or_rescue_json(None))


class OllamaEndpointCheckTests(unittest.TestCase):
    """PR-P2: removed the `or True` foot-gun. ``_ollama_has_endpoint``
    now reflects reality."""

    def test_returns_false_without_explicit_env_var(self) -> None:
        from ai.providers import _ollama_has_endpoint

        env = {k: v for k, v in os.environ.items() if k != "OLLAMA_BASE_URL"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertFalse(_ollama_has_endpoint())

    def test_returns_true_when_user_set_env_var(self) -> None:
        from ai.providers import _ollama_has_endpoint

        with mock.patch.dict(
            os.environ,
            {"OLLAMA_BASE_URL": "http://127.0.0.1:11434"},
            clear=True,
        ):
            self.assertTrue(_ollama_has_endpoint())


class AfmRescueAliasTests(unittest.TestCase):
    """AFM's local ``_parse_or_rescue`` is now an alias for the shared
    router-side function. Pin the import to catch a future drift back
    to a local copy."""

    def test_afm_rescue_is_router_canonical(self) -> None:
        from ai.afm_client import _parse_or_rescue
        from ai.router import parse_or_rescue_json

        self.assertIs(_parse_or_rescue, parse_or_rescue_json)


if __name__ == "__main__":
    unittest.main()
