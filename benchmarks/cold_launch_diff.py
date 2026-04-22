import argparse
import json
from pathlib import Path


def load_report(path: str) -> dict:
    data = json.loads(Path(path).read_text())
    if "p50_ms" not in data or "p95_ms" not in data:
        raise ValueError(f"{path} is not a valid cold-launch report")
    return data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", required=True)
    parser.add_argument("--after", required=True)
    parser.add_argument("--budget-p50-ms", type=float, required=True)
    parser.add_argument("--budget-p95-ms", type=float, required=True)
    args = parser.parse_args()

    before = load_report(args.before)
    after = load_report(args.after)

    before_p50 = float(before["p50_ms"])
    before_p95 = float(before["p95_ms"])
    after_p50 = float(after["p50_ms"])
    after_p95 = float(after["p95_ms"])

    print(
        json.dumps(
            {
                "before": {
                    "frontend": before.get("frontend"),
                    "p50_ms": before_p50,
                    "p95_ms": before_p95,
                },
                "after": {
                    "frontend": after.get("frontend"),
                    "p50_ms": after_p50,
                    "p95_ms": after_p95,
                },
                "delta": {
                    "p50_ms": round(after_p50 - before_p50, 2),
                    "p95_ms": round(after_p95 - before_p95, 2),
                },
                "budget": {
                    "p50_ms": args.budget_p50_ms,
                    "p95_ms": args.budget_p95_ms,
                },
            },
            indent=2,
            sort_keys=True,
        )
    )

    if after_p50 > args.budget_p50_ms or after_p95 > args.budget_p95_ms:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
