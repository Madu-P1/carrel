import os
from dataclasses import dataclass
from pathlib import Path


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
