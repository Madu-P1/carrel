from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_TRACKED_PREFIXES = (
    "data/uploads/",
    "data/job-uploads/",
    "data/logs/",
    "data/backups/",
)
FORBIDDEN_TRACKED_SUFFIXES = (
    ".db",
    ".db-shm",
    ".db-wal",
    ".log",
)
ALLOWED_TRACKED_DATA_FILES = {
    "data/benchmarks/baseline.json",
}


class RepositoryHygieneTests(unittest.TestCase):
    def test_no_private_data_artifacts_are_tracked(self) -> None:
        result = subprocess.run(
            ["git", "ls-files", "data"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        tracked = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        forbidden = [
            path
            for path in tracked
            if path not in ALLOWED_TRACKED_DATA_FILES
            and (
                path.startswith(FORBIDDEN_TRACKED_PREFIXES)
                or path.endswith(FORBIDDEN_TRACKED_SUFFIXES)
            )
        ]

        self.assertEqual(
            [],
            forbidden,
            "Private data artifacts must not be tracked in git.",
        )

    def test_bundled_macos_resources_do_not_reference_source_maps(self) -> None:
        result = subprocess.run(
            ["git", "grep", "-n", "sourceMappingURL", "--", "macos-app/Resources"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        matches = [line for line in result.stdout.splitlines() if line.strip()]

        self.assertEqual(
            [],
            matches,
            "Production macOS resources must not ship source map references.",
        )


if __name__ == "__main__":
    unittest.main()
