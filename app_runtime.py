import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dotenv is in requirements.txt
    load_dotenv = None  # type: ignore[assignment]


def _load_env_file() -> None:
    """Load .env from the repo root if present.

    The .env lives next to this file (repo root) and is the canonical home
    for ANTHROPIC_API_KEY, EINSTEIN_AI_PROVIDER, OLLAMA_* overrides, etc.
    Previously the backend only saw whatever the invoking shell had
    exported, which meant users dropping keys in .env got silently ignored
    and the app fell back to auto-selection heuristics instead of their
    explicit choice. Loading at import time fixes that for any process
    that imports app_runtime (which main.py does before touching AI).
    override=False keeps real process env ahead of .env so ops tools
    (systemd, launchd, Docker) still win.
    """
    if load_dotenv is None:
        return
    env_path = Path(__file__).resolve().parent / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=False)


_load_env_file()


@dataclass(frozen=True)
class RuntimePaths:
    base_dir: Path
    data_dir: Path
    upload_dir: Path
    db_path: Path
    schema_path: Path
    log_dir: Path
    benchmark_dir: Path


def _env_path(name: str) -> Path | None:
    value = os.getenv(name, "").strip()
    if not value:
        return None
    return Path(value).expanduser().resolve()


def _default_base_dir() -> Path:
    return Path(__file__).resolve().parent


def resolve_runtime_paths(base_dir: Path | None = None) -> RuntimePaths:
    resolved_base = (_env_path("EINSTEIN_BASE_DIR") or base_dir or _default_base_dir()).resolve()
    data_dir = (_env_path("EINSTEIN_DATA_DIR") or (resolved_base / "data")).resolve()
    upload_dir = (_env_path("EINSTEIN_UPLOAD_DIR") or (data_dir / "uploads")).resolve()
    db_path = (_env_path("EINSTEIN_DB_PATH") or (data_dir / "einstein_tutor.db")).resolve()
    schema_path = (_env_path("EINSTEIN_SCHEMA_PATH") or (resolved_base / "schema.sql")).resolve()
    log_dir = (_env_path("EINSTEIN_LOG_DIR") or (data_dir / "logs")).resolve()
    benchmark_dir = (_env_path("EINSTEIN_BENCHMARK_DIR") or (data_dir / "benchmarks")).resolve()
    return RuntimePaths(
        base_dir=resolved_base,
        data_dir=data_dir,
        upload_dir=upload_dir,
        db_path=db_path,
        schema_path=schema_path,
        log_dir=log_dir,
        benchmark_dir=benchmark_dir,
    )
