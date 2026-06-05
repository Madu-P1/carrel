"""Phase 9: the zero-egress proof behind the airplane-mode demo.

Forbids any real socket, then runs both deterministic surfaces end to end and
asserts the catch still fires. If any step tried to reach the network, opening
the socket would raise. This is the structural test that backs the live
network-monitor demonstration.
"""

from __future__ import annotations

import hashlib
import math
import os
import shutil
import socket
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import db
from services.ingestion.persistence import embed_and_index_nodes, insert_typed_nodes
from services.ingestion.typed_walker import TypedNode
from services.legal.deterministic_envelope import build_deterministic_envelope
from services.legal.local_caselaw import local_caselaw_client
from services.verify import verify_draft_stream

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_SOURCE = REPO_ROOT / "migrations"


def _forbid_sockets():
    """Patch socket.socket so any real connection attempt fails loudly."""

    def _raise(*_args, **_kwargs):
        raise AssertionError("the deterministic verify path attempted to open a real socket")

    return mock.patch.object(socket, "socket", _raise)


class _DeterministicEmbedder:
    dim = 384

    def _vec(self, text: str) -> list[float]:
        tokens = [t.lower() for t in text.split() if t]
        if not tokens:
            return [0.0] * self.dim
        accum = [0.0] * self.dim
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            for i in range(self.dim):
                accum[i] += ((digest[i % len(digest)] / 255.0) * 2.0) - 1.0
        norm = math.sqrt(sum(v * v for v in accum)) or 1.0
        return [v / norm for v in accum]

    def embed_passages(self, texts):
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)


class LitigatorZeroEgressTests(unittest.TestCase):
    def test_litigator_opener_opens_no_real_socket(self) -> None:
        client = local_caselaw_client()
        with (
            mock.patch.dict(os.environ, {"COURTLISTENER_API_TOKEN": "local"}, clear=False),
            _forbid_sockets(),
        ):
            env = build_deterministic_envelope(
                "As held in 999 U.S. 999, the rule applies.", client=client
            )
        verdict = env["claims"][0]["case_verdicts"][0]["verdicts"][0]
        self.assertFalse(verdict["exists"])  # the catch fired, offline
        self.assertEqual("deterministic", env["provider"])

    def test_litigator_opener_no_injected_client_opens_no_real_socket(self) -> None:
        # The production path (services.verify.verify_draft) injects NO client. The
        # engine must therefore be offline BY CONSTRUCTION, not contingent on an env
        # flag. Token present (the demo sentinel) so the courtlistener token guard
        # passes; if the engine fell through to a real one-shot client this draft
        # would POST to courtlistener.com. CACHET_LOCAL_CASELAW is explicitly absent
        # so this proves the floor, not the flag.
        with mock.patch.dict(os.environ, {"COURTLISTENER_API_TOKEN": "local"}, clear=False):
            os.environ.pop("CACHET_LOCAL_CASELAW", None)
            with _forbid_sockets():
                env = build_deterministic_envelope("As held in 999 U.S. 999, the rule applies.")
        verdict = env["claims"][0]["case_verdicts"][0]["verdicts"][0]
        self.assertFalse(verdict["exists"])  # caught offline with no client injected
        self.assertEqual("deterministic", env["provider"])


class StreamZeroEgressTests(unittest.TestCase):
    """The demo UI's ONLY verify entrypoint is the stream (VerifyView -> POST
    /api/verify/stream -> verify_draft_stream). With the deterministic flag on it
    must be offline by construction, exactly like the non-stream path. The prior
    zero-egress tests covered only build_deterministic_envelope, never the stream,
    so a real cite through the live UI POSTed the draft to courtlistener.com."""

    def test_stream_is_offline_when_deterministic_flag_on(self) -> None:
        import sqlite3

        conn = sqlite3.connect(":memory:")
        events: list = []
        with mock.patch.dict(
            os.environ,
            {"CACHET_DETERMINISTIC_VERIFY": "1", "COURTLISTENER_API_TOKEN": "local"},
            clear=False,
        ):
            os.environ.pop("CACHET_LOCAL_CASELAW", None)
            with _forbid_sockets():
                for event in verify_draft_stream(
                    conn,
                    "As held in 999 U.S. 999, the rule applies.",
                    log_study_event=lambda *a, **k: None,
                    fetch_recent_events=lambda *a, **k: [],
                ):
                    events.append(event)
        conn.close()
        results = [e for e in events if e.get("type") == "result"]
        self.assertTrue(results, "stream emitted no result event")
        verify = results[-1]["verify"]
        # The deterministic engine ran (not the LLM path), offline, through the
        # exact entrypoint the GUI uses.
        self.assertEqual("deterministic", verify.get("provider"))
        self.assertTrue(verify.get("claim_verdicts"), "no verdicts from the stream engine")


class ContractZeroEgressTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original = (db.BASE_DIR, db.DATA_DIR, db.UPLOAD_DIR, db.DB_PATH, db.SCHEMA_PATH)
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        data_dir = root / "data"
        (data_dir / "uploads").mkdir(parents=True, exist_ok=True)
        (root / "schema.sql").write_text("-- test\n", encoding="utf-8")
        shutil.copytree(MIGRATIONS_SOURCE, root / "migrations", dirs_exist_ok=True)
        db.configure_paths(
            base_dir=root,
            data_dir=data_dir,
            upload_dir=data_dir / "uploads",
            db_path=data_dir / "test.db",
            schema_path=root / "schema.sql",
        )
        self._conn = db.get_db()
        db.apply_migrations(self._conn)
        self._embedder = _DeterministicEmbedder()
        self._conn.execute(
            "INSERT INTO documents (id, filename, file_type, status, source_kind, subject_name) "
            "VALUES ('c1', 'msa.pdf', 'pdf', 'ready', 'upload', 'Agreement')"
        )
        nodes = [
            TypedNode(
                node_type="body",
                heading_path="Agreement",
                page=1,
                char_start=0,
                char_end=60,
                verbatim_text="The aggregate liability shall not exceed $500,000.",
                parent_block_id=None,
                reading_order=0,
            )
        ]
        ids = insert_typed_nodes(self._conn, "c1", nodes)
        embed_and_index_nodes(self._conn, nodes, ids, embedder=self._embedder)
        self._conn.commit()

    def tearDown(self) -> None:
        self._conn.close()
        self._tmp.cleanup()
        db.configure_paths(
            base_dir=self._original[0],
            data_dir=self._original[1],
            upload_dir=self._original[2],
            db_path=self._original[3],
            schema_path=self._original[4],
        )

    def test_contract_close_opens_no_real_socket(self) -> None:
        with _forbid_sockets():
            env = build_deterministic_envelope(
                "The aggregate liability is capped at $1,000,000.",
                conn=self._conn,
                doc_ids=["c1"],
                embedder=self._embedder,
            )
        self.assertEqual(
            "parametric_contradiction", env["claims"][0]["contract_verdict"]["disposition"]
        )

    def test_stream_contract_close_with_empty_doc_ids_is_offline(self) -> None:
        # Demo-faithful: the UI sends NO doc_ids. The full-library fallback must scope
        # to the ingested contract so the $1,000,000-vs-$500,000 contradiction fires
        # through the STREAM (the entrypoint the GUI calls), offline. default_embedder
        # is patched to the in-process embedder so no fastembed weights are fetched;
        # the socket ban proves nothing else egresses either.
        import services.retrieval.nodes_vector as nodes_vector

        with (
            mock.patch.dict(
                os.environ,
                {"CACHET_DETERMINISTIC_VERIFY": "1", "COURTLISTENER_API_TOKEN": "local"},
                clear=False,
            ),
            mock.patch.object(nodes_vector, "default_embedder", lambda: self._embedder),
            _forbid_sockets(),
        ):
            events = list(
                verify_draft_stream(
                    self._conn,
                    "The aggregate liability is capped at $1,000,000.",
                    log_study_event=lambda *a, **k: None,
                    fetch_recent_events=lambda *a, **k: [],
                )
            )
        results = [e for e in events if e.get("type") == "result"]
        self.assertTrue(results, "stream emitted no result event")
        cards = results[-1]["verify"].get("claim_verdicts") or []
        self.assertTrue(cards, "no verdicts from the contract stream")
        # The contradiction fired via the fallback (empty doc_ids), offline.
        self.assertEqual("unsupported", cards[0]["verdict"])


if __name__ == "__main__":
    unittest.main()
