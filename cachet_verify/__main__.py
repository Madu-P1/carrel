"""The kernel as a shell command: the CI-gate primitive.

    python -m cachet_verify --claim "The fund totals $360 million." \\
        --source-file contract.txt
    python -m cachet_verify --draft-file summary.txt --source-file a.txt \\
        --source-file b.txt --certificate cert.json --exhibit

Exit codes are the gate: 0 = verified, 1 = altered, 2 = could_not_check,
3 = usage error (bad flags, unreadable/unwritable paths), 4 = internal error.
A verdict code (0/1/2) is emitted ONLY by a completed engine run; every
failure of the tool itself lands on 3 or 4, never on a verdict, so a CI
pipeline keying on $? can never mistake a crash or a disk error for a
caught fabrication (mythos batchC-20260702).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from .adapter import attest_draft, verify_claim
from .certificate import issue_certificate, render_exhibit

_EXIT = {"verified": 0, "altered": 1, "could_not_check": 2}


class _GateParser(argparse.ArgumentParser):
    """argparse exits 2 on usage errors, which collides with the
    could_not_check verdict code. Usage errors are 3 per the documented
    table (mythos batchC-20260702)."""

    def error(self, message: str) -> None:  # noqa: A002 (argparse contract)
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        raise SystemExit(3)


def main(argv: list[str] | None = None) -> int:
    parser = _GateParser(prog="python -m cachet_verify", description=__doc__)
    what = parser.add_mutually_exclusive_group(required=True)
    what.add_argument("--claim", help="one claim to attest")
    what.add_argument("--draft-file", help="path to a draft; every statement is attested")
    what.add_argument(
        "--conformance",
        nargs="?",
        const="",
        metavar="CORPUS_JSONL",
        help="run the conformance floors (optionally against a custom corpus)",
    )
    parser.add_argument(
        "--source-file",
        action="append",
        default=[],
        help="path to a source document (repeatable)",
    )
    parser.add_argument("--source", action="append", default=[], help="a source as a literal")
    parser.add_argument("--json", action="store_true", help="print the raw attestation JSON")
    parser.add_argument("--exhibit", action="store_true", help="print the filing-grade exhibit")
    parser.add_argument("--certificate", help="write the sealed certificate JSON here")
    args = parser.parse_args(argv)

    if args.conformance is not None:
        from .adapter import verify_claim as _vc
        from .conformance import DEFAULT_CORPUS, load_corpus, run_conformance

        corpus_path = args.conformance or DEFAULT_CORPUS
        report = run_conformance(lambda c, s: _vc(c, s).state, load_corpus(corpus_path))
        print(f"cases: {report.total}")
        print(f"conformant: {report.conformant}")
        print(f"catch: {report.altered_caught}/{report.altered_total}")
        print(f"faithful confirmed: {report.faithful_confirmed}/{report.faithful_total}")
        print(f"refusals: {report.uncheckable_refused}/{report.uncheckable_total}")
        for v in report.violations:
            print(f"VIOLATION: {v}", file=sys.stderr)
        return 0 if report.conformant else 1

    sources: list[str] = list(args.source)
    for path in args.source_file:
        try:
            with open(path, encoding="utf-8") as f:
                sources.append(f.read())
        except OSError as e:
            print(f"cannot read source {path}: {e}", file=sys.stderr)
            return 3

    if args.draft_file:
        try:
            with open(args.draft_file, encoding="utf-8") as f:
                draft = f.read()
        except OSError as e:
            print(f"cannot read draft {args.draft_file}: {e}", file=sys.stderr)
            return 3
    else:
        draft = args.claim

    if args.claim is not None and not (args.exhibit or args.certificate):
        attestation = verify_claim(draft, sources)
        if args.json:
            print(
                json.dumps(
                    {
                        "state": attestation.state,
                        "checks": [
                            {
                                "state": c.state,
                                "provenance": c.provenance,
                                "detail": c.detail,
                                "subject": c.subject,
                            }
                            for c in attestation.checks
                        ],
                    },
                    indent=2,
                )
            )
        else:
            print(attestation.state.upper())
            for c in attestation.checks:
                print(f"- [{c.state}] {c.detail}")
        return _EXIT[attestation.state]

    draft_attestation = attest_draft(draft, sources)
    cert = issue_certificate(
        draft, sources, draft_attestation, datetime.now(timezone.utc).isoformat()
    )
    if args.certificate:
        try:
            with open(args.certificate, "w", encoding="utf-8") as f:
                json.dump(cert, f, indent=2, ensure_ascii=False)
        except OSError as e:
            # An I/O failure must never masquerade as a verdict (exit 1 was
            # the uncaught-exception default, colliding with "altered").
            print(f"cannot write certificate {args.certificate}: {e}", file=sys.stderr)
            return 3
        print(f"certificate written to {args.certificate}", file=sys.stderr)
    if args.exhibit:
        print(render_exhibit(cert))
    elif args.json:
        print(json.dumps(cert, indent=2, ensure_ascii=False))
    else:
        print(cert["state"].upper())
        for claim in cert["claims"]:
            print(f"- [{claim['state']}] {claim['claim'][:80]}")
    return _EXIT[cert["state"]]


def _entry() -> int:
    try:
        return main()
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001 -- the last-resort gate guard
        import traceback

        traceback.print_exc()
        return 4


if __name__ == "__main__":
    raise SystemExit(_entry())
