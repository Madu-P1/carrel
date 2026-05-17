import os
import platform
import sys
import unittest

skip_reason = (
    "Set CARREL_RUN_AFM_INTEGRATION=1, run on macOS 26+ Apple Silicon "
    "with Apple Intelligence enabled and en_US primary locale, and "
    "have the bridge built (cd macos-app && swift build)."
)


def _on_macos_26_with_bridge() -> bool:
    if sys.platform != "darwin" or platform.machine() != "arm64":
        return False
    try:
        major = int(platform.mac_ver()[0].split(".")[0])
    except Exception:
        return False
    if major < 26:
        return False
    from ai.native_bridge_paths import AFM_BRIDGE_CANDIDATES, find_binary

    return find_binary(AFM_BRIDGE_CANDIDATES) is not None


@unittest.skipUnless(
    os.getenv("CARREL_RUN_AFM_INTEGRATION") == "1" and _on_macos_26_with_bridge(),
    skip_reason,
)
class AFMRealBridgeTests(unittest.TestCase):
    def test_availability_is_available(self) -> None:
        from ai.afm_client import AFMClient

        client = AFMClient()
        result = client.request_text(
            request_kind="integration.smoke",
            system="Reply in exactly one short sentence.",
            prompt="What is one plus one?",
            max_tokens=32,
        )
        self.assertTrue(
            result.ok,
            msg=f"AFM not available: {result.error_code} / {result.error_message}",
        )

    def test_request_text_returns_real_generation(self) -> None:
        from ai.afm_client import AFMClient

        client = AFMClient()
        result = client.request_text(
            request_kind="integration.text",
            system="Reply in one sentence.",
            prompt="What is mitosis?",
            max_tokens=64,
        )
        self.assertTrue(result.ok, msg=result.error_message)
        self.assertIsNotNone(result.text)
        self.assertGreater(len(result.text), 10)
        self.assertLess(result.latency_ms, 30_000, msg="cold-start cap")

    def test_request_json_with_real_model(self) -> None:
        from ai.afm_client import AFMClient

        client = AFMClient()
        result = client.request_json(
            request_kind="integration.json",
            system='Return JSON: {"answer": <string>}.',
            prompt="What is the capital of France?",
            fallback={"answer": ""},
        )
        self.assertTrue(result.ok)
        self.assertIsInstance(result.json_payload, dict)
        self.assertIn("answer", result.json_payload)
        self.assertGreater(len(result.json_payload["answer"]), 0)


class AFMPerfSmokeTests(unittest.TestCase):
    @unittest.skipUnless(
        os.getenv("CARREL_RUN_AFM_INTEGRATION") == "1" and _on_macos_26_with_bridge(),
        skip_reason,
    )
    def test_warm_call_under_five_seconds(self) -> None:
        from ai.afm_client import AFMClient

        client = AFMClient()
        # Realistic warmup. The 8-token "Hi." warmup the runbook
        # originally specified does not actually warm the AFM weight
        # cache, so the subsequent measure call still pays the
        # cold-cache cost. A 32-token warmup with a real prompt pulls
        # weights into memory cheaply.
        client.request_text(
            request_kind="perf.warmup",
            system="",
            prompt="Briefly describe cell division.",
            max_tokens=32,
        )
        result = client.request_text(
            request_kind="perf.measure",
            system="",
            prompt="Write one short paragraph about cell division.",
            max_tokens=120,
        )
        self.assertTrue(result.ok)
        # Measured envelope on macOS 26.4.1 + M-series after one
        # realistic warmup: 2700-3200ms across cold full-suite runs.
        # 5000ms keeps the perf signal meaningful without flaking on
        # ordinary scheduling noise.
        self.assertLess(
            result.latency_ms,
            5_000,
            msg=f"Warm latency degraded to {result.latency_ms:.0f}ms",
        )


if __name__ == "__main__":
    unittest.main()
