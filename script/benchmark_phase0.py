"""DEPRECATED: remove during Phase 1 cleanup after callers switch to `python -m benchmarks.phase0`."""

from benchmarks.phase0 import main_cli


if __name__ == "__main__":
    raise SystemExit(main_cli())
