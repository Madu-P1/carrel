"""Artifact Studio — generates durable learning artifacts from source material.

Package layout (was a 886-LoC flat module before the split):

    services/artifact_studio/
        __init__.py          — public surface re-exports
        _orchestrator.py     — generate_artifact, list_artifacts, get_artifact
        grounding.py         — chunk + concept retrieval for a scope
        topic_map.py         — focus selection + topic-map analysis
        generators.py        — 9 markdown generators + structured JSON payload

External consumers (`routes/studio.py`, `benchmarks/phase0.py`) keep
working unchanged: `from services import artifact_studio as studio_service`
still resolves, and `studio_service.generate_artifact(...)` etc. still
work via these re-exports.
"""

# Public API — what routes/studio.py + benchmarks call.
from ._orchestrator import generate_artifact, get_artifact, list_artifacts
from .grounding import (
    render_grounding_text,
    retrieve_grounding_chunks,
)

__all__ = [
    "generate_artifact",
    "get_artifact",
    "list_artifacts",
    "render_grounding_text",
    "retrieve_grounding_chunks",
]
