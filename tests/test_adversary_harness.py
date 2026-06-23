"""Tests for the adversarial discovery harness (evals/adversary).

These pin the harness's correctness so its confession ledger is trustworthy:
  - the read-only probe maps the REAL engine's dispositions to honest states;
  - the disposition->state map agrees with script/cachet-acceptance.py;
  - the classifier is total and labels each outcome correctly;
  - the battery's structural invariants hold (no false accusations, no laundering,
    and the documented single-value subject-binding false greens are present);
  - the whole battery is zero-egress (runs under a socket ban);
  - the ledger writer emits md + json + crack fixtures.
"""

from __future__ import annotations

import importlib.util
import json
import socket
import tempfile
import unittest
from pathlib import Path

from evals.adversary.contracts import (
    CONTRADICTED,
    COULD_NOT_VERIFY,
    STATE_BY_DISPOSITION,
    SUPPORTED,
    AttackCase,
    Mode,
    Outcome,
    ProbeResult,
    classify,
    state_for_disposition,
)
from evals.adversary.engine_probe import forbid_sockets, probe_contract, probe_litigator
from evals.adversary.families import all_cases
from evals.adversary.harness import BatteryResult, Record, run_battery
from evals.adversary.ledger import write_ledger

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _case(acceptable: set[str], claim: str = "x", source: str = "y") -> AttackCase:
    return AttackCase(
        case_id="t",
        family="f",
        mode=Mode.CONTRACT,
        claim=claim,
        source=source,
        acceptable_states=frozenset(acceptable),
        rationale="r",
    )


def _result(state: str) -> ProbeResult:
    return ProbeResult(
        state=state, disposition="d", anchor_type=None, detail="", mode=Mode.CONTRACT
    )


class StateMappingTests(unittest.TestCase):
    def test_mapping_agrees_with_acceptance_gate(self) -> None:
        # Load script/cachet-acceptance.py as a module and compare _state for every
        # disposition the harness knows. The two must never drift.
        spec = importlib.util.spec_from_file_location(
            "cachet_acceptance", _REPO_ROOT / "script" / "cachet-acceptance.py"
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for disposition, expected in STATE_BY_DISPOSITION.items():
            self.assertEqual(module._state(disposition), expected, disposition)
        # An unknown disposition is the honest could-not-verify default in both.
        self.assertEqual(state_for_disposition("brand_new_disposition"), COULD_NOT_VERIFY)
        self.assertEqual(module._state("brand_new_disposition"), COULD_NOT_VERIFY)


class ProbeTests(unittest.TestCase):
    def test_contract_probe_known_cases(self) -> None:
        with forbid_sockets():
            mismatch = probe_contract(
                "Liability is capped at $1,000,000.",
                "the aggregate liability shall not exceed $500,000",
            )
            scoped = probe_contract(
                "The cap is $500,000.", "liability shall not exceed $500,000 in the aggregate"
            )
            quote = probe_contract(
                'The agreement says it will "survive termination".',
                "These obligations survive termination of this Agreement.",
            )
        self.assertEqual(CONTRADICTED, mismatch.state)
        self.assertEqual(COULD_NOT_VERIFY, scoped.state)  # ADR-0013 never affirms a figure
        self.assertEqual(SUPPORTED, quote.state)  # verbatim quote is the only green

    def test_litigator_probe_known_cases(self) -> None:
        with forbid_sockets():
            real = probe_litigator("Segregation was rejected in 347 U.S. 483.")
            fake = probe_litigator("As held in 999 U.S. 999, the rule applies.")
        self.assertEqual(SUPPORTED, real.state)
        self.assertEqual(COULD_NOT_VERIFY, fake.state)


class ClassifyTests(unittest.TestCase):
    def test_held(self) -> None:
        self.assertIs(Outcome.HELD, classify(_case({COULD_NOT_VERIFY}), _result(COULD_NOT_VERIFY)))

    def test_false_green(self) -> None:
        self.assertIs(Outcome.FALSE_GREEN, classify(_case({COULD_NOT_VERIFY}), _result(SUPPORTED)))

    def test_false_accusation(self) -> None:
        self.assertIs(
            Outcome.FALSE_ACCUSATION, classify(_case({COULD_NOT_VERIFY}), _result(CONTRADICTED))
        )

    def test_laundering(self) -> None:
        # honest answer was a contradiction; the engine dodged to could-not-verify.
        self.assertIs(
            Outcome.LAUNDERING, classify(_case({CONTRADICTED}), _result(COULD_NOT_VERIFY))
        )

    def test_missed_support(self) -> None:
        # honest answer was an affirmation; the engine failed to confirm it (safe).
        self.assertIs(
            Outcome.MISSED_SUPPORT, classify(_case({SUPPORTED}), _result(COULD_NOT_VERIFY))
        )


class FamilyTests(unittest.TestCase):
    def test_cases_are_well_formed_and_unique(self) -> None:
        cases = all_cases()
        self.assertGreater(len(cases), 400)
        ids = [c.case_id for c in cases]
        self.assertEqual(len(ids), len(set(ids)), "case ids must be unique")
        for c in cases:
            self.assertTrue(c.claim and c.source, c.case_id)
            self.assertTrue(c.acceptable_states, c.case_id)


class BatteryInvariantTests(unittest.TestCase):
    result: BatteryResult
    by_id: dict[str, Record]

    @classmethod
    def setUpClass(cls) -> None:
        cls.result = run_battery()
        cls.by_id = {r.case.case_id: r for r in cls.result.records}

    def test_no_false_accusations(self) -> None:
        offenders = [
            r.case.case_id for r in self.result.records if r.outcome is Outcome.FALSE_ACCUSATION
        ]
        self.assertEqual([], offenders, "engine must never accuse a clean claim")

    def test_no_laundering(self) -> None:
        offenders = [r.case.case_id for r in self.result.records if r.outcome is Outcome.LAUNDERING]
        self.assertEqual([], offenders, "engine must never dodge a single-value contradiction")

    def test_single_value_subject_binding_false_green_is_present(self) -> None:
        # The documented open gap: a single-value percent clause affirms a claim that
        # re-attributes the value to a subject absent from the clause. Pinning it here
        # means the day it is fixed, this test flips and the ledger updates.
        percent = self.by_id["subjmismatch.percent_royalty"]
        self.assertIs(Outcome.FALSE_GREEN, percent.outcome)

    def test_money_and_duration_subject_mismatch_hold(self) -> None:
        # Money and duration scope out the identical situation (ADR-0013), so they hold.
        self.assertIs(Outcome.HELD, self.by_id["subjmismatch.money_price"].outcome)
        self.assertIs(Outcome.HELD, self.by_id["subjmismatch.duration_cure"].outcome)

    def test_quote_alteration_never_false_greens(self) -> None:
        for r in self.result.records:
            if r.case.family == "quote-alteration":
                self.assertNotEqual(
                    SUPPORTED, r.result.state, f"fabricated quote affirmed: {r.case.case_id}"
                )


class ZeroEgressTests(unittest.TestCase):
    def test_socket_ban_actually_bans(self) -> None:
        with forbid_sockets():
            with self.assertRaises(AssertionError):
                socket.socket()

    def test_battery_runs_under_socket_ban(self) -> None:
        # run_battery already wraps itself in the ban; this asserts it completes.
        result = run_battery()
        self.assertGreater(result.total, 400)


class LedgerTests(unittest.TestCase):
    def test_writes_md_json_and_fixtures(self) -> None:
        result = run_battery()
        with tempfile.TemporaryDirectory() as tmp:
            paths = write_ledger(result, Path(tmp))
            md = Path(paths["markdown"]).read_text()
            data = json.loads(Path(paths["json"]).read_text())
            self.assertIn("Cachet confession ledger", md)
            self.assertIn("## Cracks (the confession)", md)
            self.assertIn("summary", data)
            self.assertEqual(data["summary"]["false_accusation"], 0)
            self.assertEqual(data["total_probes"], result.total)
            # cracks freeze a fixture each.
            self.assertEqual(len(paths["fixtures"]), len(result.cracks))


if __name__ == "__main__":
    unittest.main()
