"""PR-1 (T1 recall tier, ADR-0012): the offline model-load harness.

The T1 NLI selector (later PRs) must never download weights at runtime on a Cachet
path. This proves the shared loader fails LOUD on a cold cache instead of reaching
the network: an uncached model raises a clear error and opens no socket. The tier
itself stays dark/off; this only exercises the offline-load contract.
"""

from __future__ import annotations

import os
import socket
import unittest
from unittest import mock

from services.legal._offline_model import enforce_offline_env, load_sequence_classifier


def _forbid_sockets():
    """Patch socket.socket so any real connection attempt fails loudly."""

    def _raise(*_args, **_kwargs):
        raise AssertionError("the T1 model loader attempted to open a real socket")

    return mock.patch.object(socket, "socket", _raise)


class OfflineModelHarnessTests(unittest.TestCase):
    def test_uncached_model_fails_loud_without_a_socket(self) -> None:
        # A cold cache must raise the clear offline error, never an AssertionError
        # (which would mean a socket was attempted) and never a silent download.
        with _forbid_sockets():
            with self.assertRaises(RuntimeError) as ctx:
                load_sequence_classifier("cachet-nonexistent/fake-nli-model-xyz")
        msg = str(ctx.exception).lower()
        self.assertIn("local cache", msg)
        self.assertIn("network", msg)

    def test_enforce_offline_env_forces_flags_even_if_preset_off(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"HF_HUB_OFFLINE": "0", "TRANSFORMERS_OFFLINE": "0"},
            clear=False,
        ):
            enforce_offline_env()
            self.assertEqual("1", os.environ["HF_HUB_OFFLINE"])
            self.assertEqual("1", os.environ["TRANSFORMERS_OFFLINE"])


if __name__ == "__main__":
    unittest.main()
