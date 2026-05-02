import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = REPO_ROOT / "docs" / "prompts" / "catalog.json"


def test_prompt_catalog_validator_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "script" / "validate_prompts.py")],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_prompt_catalog_covers_roadmap_categories() -> None:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    categories = {prompt["category"] for prompt in catalog["prompts"]}

    assert {
        "ui_audit",
        "ux_flow",
        "frontend_perf",
        "backend_api",
        "database",
        "accessibility",
        "metrics",
        "ci",
        "code_review",
        "tests",
        "usability_analysis",
    } <= categories
