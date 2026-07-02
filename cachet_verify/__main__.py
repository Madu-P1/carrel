"""The kernel as a shell command: the CI-gate primitive.

    python -m cachet_verify --claim "The fund totals $360 million." \\
        --source-file contract.txt
    python -m cachet_verify --draft-file summary.txt --source-file a.txt \\
        --source-file b.txt --certificate cert.json --exhibit

Exit codes are the gate: 0 = verified, 1 = altered, 2 = could_not_check,
3 = usage error. A CI pipeline can therefore refuse to ship AI output whose
attestation is anything but verified -- or, more honestly for most pipelines,
refuse only on 1 (altered) and route 2 (could_not_check) to a human.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from .adapter import attest_draft, verify_claim
from .certificate import issue_certificate, render_exhibit

_EXIT = {"verified": 0, "altered": 1, "could_not_check": 2}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m cachet_verify", description=__doc__)
    what = parser.add_mutually_exclusive_group(required=True)
    what.add_argument("--claim", help="one claim to attest")
    what.add_argument("--draft-file", help="path to a draft; every statement is attested")
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
        with open(args.certificate, "w", encoding="utf-8") as f:
            json.dump(cert, f, indent=2, ensure_ascii=False)
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


if __name__ == "__main__":
    raise SystemExit(main())
