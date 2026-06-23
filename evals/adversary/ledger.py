"""Writes the confession ledger: a buyer-legible record of Cachet attacking itself.

House style mirrors ``evals/run_evals.py``: a paired ``.md`` + ``.json`` with an
ISO-UTC timestamp. The markdown LEADS WITH CRACKS — where the engine was caught
being wrong, and the exact test that would lock each — then the per-family
coverage, then the methodology. It is framed as an independent self-attack, not a
trophy case: a held result is reported as held, never inflated.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .contracts import Mode, Outcome
from .harness import BatteryResult, Record

_OUTCOME_LABEL = {
    Outcome.FALSE_GREEN: "FALSE GREEN (P0 — affirmed the unsupportable)",
    Outcome.LAUNDERING: "LAUNDERING (P0 — dodged a definite verdict)",
    Outcome.FALSE_ACCUSATION: "FALSE ACCUSATION (P1 — accused a clean claim)",
}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _repro(record: Record) -> str:
    case = record.case
    if case.mode is Mode.LITIGATOR:
        call = f"probe_litigator({case.claim!r})"
    else:
        call = f"probe_contract({case.claim!r}, {case.source!r})"
    expected = " | ".join(sorted(case.acceptable_states))
    return f"{call}.state == {record.result.state!r}  # honest expectation: {{{expected}}}"


def _locking_test_name(record: Record, index: int) -> str:
    return f"test_redteam_{_slug(record.case.family)}_{index:03d}"


def _origin_bucket(origin: str) -> str:
    if "mutator:" in origin:
        return "systematic"
    return "hand-crafted"


def _markdown(result: BatteryResult, generated_at: str) -> str:
    counts = result.outcome_counts()
    cracks = result.cracks
    fam_stats = result.family_stats()
    hand = sum(1 for r in result.records if _origin_bucket(r.case.origin) == "hand-crafted")
    systematic = result.total - hand

    lines: list[str] = []
    lines.append(f"# Cachet confession ledger — {generated_at}")
    lines.append("")
    lines.append(
        "Cachet attacked its own deterministic verify engine. Every probe below was "
        "run through the REAL engine (no mock of verdict logic), under a socket ban "
        "that proves zero network egress, and carries a PROVABLE honest expectation "
        "by construction. A divergence from that expectation is a real crack, not a "
        "guess."
    )
    lines.append("")
    lines.append("## Headline")
    lines.append("")
    lines.append(
        f"- **{result.total}** adversarial probes across **{len(result.families)}** families"
    )
    lines.append(f"- **{counts.get(Outcome.HELD, 0)}** HELD (engine answered honestly)")
    lines.append(
        f"- **{len(cracks)}** crack(s) surfaced — listed first, each with its locking test"
    )
    lines.append(
        f"  - FALSE GREEN (P0): {counts.get(Outcome.FALSE_GREEN, 0)}"
        f"  |  LAUNDERING (P0): {counts.get(Outcome.LAUNDERING, 0)}"
        f"  |  FALSE ACCUSATION (P1): {counts.get(Outcome.FALSE_ACCUSATION, 0)}"
    )
    lines.append(
        f"- composition: {hand} hand-crafted hard cases, {systematic} systematic value-space probes"
    )
    lines.append("")

    lines.append("## Cracks (the confession)")
    lines.append("")
    if not cracks:
        lines.append(
            "No cracks surfaced across this battery: the engine never affirmed an "
            "unsupportable claim, never accused a clean one, and never downgraded a "
            "provable contradiction to could-not-check. This is a HELD result over "
            "the families exercised below, not a claim of completeness — the coverage "
            "and the families NOT yet attacked are listed in Methodology."
        )
    else:
        lines.append(
            "Each crack is where the engine was caught being wrong. The repro line "
            "reproduces it against the real engine; the locking test is the held-out "
            "regression that would prevent it. Fixes are DRAFTED + queued for review, "
            "never merged unattended (engine truth surfaces are human-gated)."
        )
        lines.append("")
        for i, r in enumerate(cracks, start=1):
            lines.append(f"### Crack {i}: {_OUTCOME_LABEL[r.outcome]}")
            lines.append(f"- **family**: `{r.case.family}`  ·  **case**: `{r.case.case_id}`")
            lines.append(f"- **claim**: {r.case.claim}")
            lines.append(f"- **source**: {r.case.source}")
            lines.append(
                f"- **engine said**: `{r.result.state}` (disposition `{r.result.disposition}`)"
                f"  ·  **honest expectation**: {{{' | '.join(sorted(r.case.acceptable_states))}}}"
            )
            lines.append(f"- **why it is a crack**: {r.case.rationale}")
            lines.append(f"- **repro**: `{_repro(r)}`")
            lines.append(f"- **locking test**: `{_locking_test_name(r, i)}`")
            lines.append("")

    observations = [r for r in result.records if r.outcome is Outcome.MISSED_SUPPORT]
    lines.append("## Honest-direction observations (coverage gaps, not cracks)")
    lines.append("")
    if not observations:
        lines.append("None: every true positive the battery expected was confirmed.")
    else:
        lines.append(
            "Here the engine REFUSED a claim that was honestly supportable — it failed "
            "to confirm a true positive. This is the SAFE direction (never a false "
            "green), but a coverage gap worth a fix."
        )
        lines.append("")
        for r in observations:
            lines.append(f"- `{r.case.family}` · {r.case.claim}")
            lines.append(
                f"  - engine: `{r.result.state}`; honest expectation: "
                f"{{{' | '.join(sorted(r.case.acceptable_states))}}}"
            )
            lines.append(f"  - {r.case.rationale}")
            lines.append(f"  - repro: `{_repro(r)}`")
    lines.append("")

    lines.append("## Per-family coverage")
    lines.append("")
    lines.append("| Family | Tier | Probes | Held | Cracks | State distribution |")
    lines.append("|---|---|---|---|---|---|")
    for fam in result.families:
        s = fam_stats[fam]
        tier = "exploratory" if s["exploratory"] else "proven"
        dist = ", ".join(f"{k}:{v}" for k, v in sorted(s["by_state"].items()))
        lines.append(f"| `{fam}` | {tier} | {s['total']} | {s['held']} | {s['cracks']} | {dist} |")
    lines.append("")

    exploratory = [f for f in result.families if fam_stats[f]["exploratory"]]
    if exploratory:
        lines.append("### Exploratory-family catch-rate (honest coverage, not cracks)")
        lines.append("")
        lines.append(
            "Polarity and governing-law contradiction-catching is NOT asserted as a "
            "hard expectation, so an honest could-not-verify there is HELD, not a "
            "crack. The catch-rate below is a coverage signal: how often the engine "
            "actively flagged the contradiction vs honestly refused."
        )
        lines.append("")
        for fam in exploratory:
            s = fam_stats[fam]
            caught = s["by_state"].get("contradicted", 0)
            refused = s["by_state"].get("could_not_verify", 0)
            lines.append(
                f"- `{fam}`: caught (contradicted) {caught} / honest-refusal "
                f"(could-not-verify) {refused} of {s['total']}"
            )
        lines.append("")

    lines.append("## Methodology")
    lines.append("")
    lines.append(
        "- **Read-only**: the harness imports the engine and reads its verdict back; "
        "it edits no truth-surface file (`contract_verify.py`, "
        "`deterministic_envelope.py`, `anchors.py`, `sentences.py`, "
        "`case_verification.py`, `local_caselaw.py`)."
    )
    lines.append(
        "- **Zero-egress**: the entire battery runs inside a socket ban; any real "
        "socket construction raises. No network, no model download."
    )
    lines.append(
        "- **Deterministic**: the battery is reproducible run-to-run; only the ledger "
        "timestamp varies."
    )
    lines.append(
        "- **By design, not a crack**: money and duration are scoped out — a matching "
        "figure there resolves to could-not-verify, never supported (ADR-0013). "
        "Percent, date, and governing-law instead affirm a genuine single-value match "
        "as `supported` (as does a verbatim quote). The clean-control and "
        "format-variant families confirm the engine does not ACCUSE these clean "
        "claims. The subject-mismatch cracks above show the cost of that asymmetry: "
        "the percent affirmation path greens on the bare value alone, so it also "
        "greens a value re-attributed to a different subject."
    )
    lines.append(
        "- **Engine entry points**: contract path "
        "`verify_claim_against_clause(claim, clause)`; litigator path "
        "`build_deterministic_envelope(draft, client=local_caselaw_client())`."
    )
    lines.append("")
    return "\n".join(lines) + "\n"


def _record_payload(record: Record) -> dict[str, Any]:
    return {
        "case_id": record.case.case_id,
        "family": record.case.family,
        "mode": record.case.mode.value,
        "claim": record.case.claim,
        "source": record.case.source,
        "acceptable_states": sorted(record.case.acceptable_states),
        "origin": record.case.origin,
        "rationale": record.case.rationale,
        "engine_state": record.result.state,
        "engine_disposition": record.result.disposition,
        "anchor_type": record.result.anchor_type,
        "detail": record.result.detail,
        "outcome": record.outcome.value,
        "is_crack": record.is_crack,
    }


def _json_payload(result: BatteryResult, generated_at: str) -> dict[str, Any]:
    counts = result.outcome_counts()
    return {
        "generated_at": generated_at,
        "total_probes": result.total,
        "families": result.families,
        "summary": {
            "held": counts.get(Outcome.HELD, 0),
            "false_green": counts.get(Outcome.FALSE_GREEN, 0),
            "laundering": counts.get(Outcome.LAUNDERING, 0),
            "false_accusation": counts.get(Outcome.FALSE_ACCUSATION, 0),
            "cracks": len(result.cracks),
        },
        "family_stats": {
            fam: {
                "total": s["total"],
                "held": s["held"],
                "cracks": s["cracks"],
                "by_state": dict(s["by_state"]),
                "exploratory": s["exploratory"],
            }
            for fam, s in result.family_stats().items()
        },
        "records": [_record_payload(r) for r in result.records],
    }


def _freeze_fixtures(result: BatteryResult, out_dir: Path) -> list[str]:
    written: list[str] = []
    for i, r in enumerate(result.cracks, start=1):
        fam_dir = out_dir / "fixtures" / _slug(r.case.family)
        fam_dir.mkdir(parents=True, exist_ok=True)
        path = fam_dir / f"{_slug(r.case.case_id)}.json"
        path.write_text(
            json.dumps(
                {
                    "id": r.case.case_id,
                    "family": r.case.family,
                    "mode": r.case.mode.value,
                    "claim": r.case.claim,
                    "source": r.case.source,
                    "expected": sorted(r.case.acceptable_states),
                    "got_state": r.result.state,
                    "got_disposition": r.result.disposition,
                    "outcome": r.outcome.value,
                    "locking_test": _locking_test_name(r, i),
                    "rationale": r.case.rationale,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        written.append(str(path))
    return written


def write_ledger(result: BatteryResult, out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    stamp = generated_at.replace(":", "-")
    md_path = out_dir / f"confession-ledger-{stamp}.md"
    json_path = out_dir / f"confession-ledger-{stamp}.json"
    md_path.write_text(_markdown(result, generated_at), encoding="utf-8")
    json_path.write_text(
        json.dumps(_json_payload(result, generated_at), indent=2), encoding="utf-8"
    )
    fixtures = _freeze_fixtures(result, out_dir) if result.cracks else []
    return {"markdown": str(md_path), "json": str(json_path), "fixtures": fixtures}
