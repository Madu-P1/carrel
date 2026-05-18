"""Streaming Claude response helper.

Carrel's grounded-tutor endpoint (``routes/tutor.py::tutor_query``)
returns a fully-resolved, citation-validated envelope synchronously.
That flow is hard to stream because citation validation is a
post-hoc pass over the full response.

This module is the smaller building block: stream Claude tokens for a
prompt, leave citation handling to the existing grounded path. Use it
when you want progressive token delivery to the UI for chat-style
follow-ups, rephrasing, or expansion. Do not use it for "the answer
the student trusts": that still flows through the grounded endpoint.

Imported pattern: Next.js ``examples/with-ai-sdk`` family. Stream
deltas over SSE; the client concatenates. See
``packages/next/src/server/stream-utils/`` in the Next.js source for
the inspiration.
"""

from __future__ import annotations

import os
from typing import Iterator, Optional

from anthropic import Anthropic

DEFAULT_MAX_TOKENS = 1600


def stream_claude_text(
    *,
    system: str,
    prompt: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Iterator[str]:
    """Yield text deltas from Claude as they arrive.

    Each yielded string is a delta, not a cumulative answer. Callers
    are responsible for concatenation. Raises on API errors instead of
    falling back silently (Carrel's "no silent AI fallbacks" rule).

    Parameters
    ----------
    system, prompt
        The Claude system message and user message.
    max_tokens
        Cap on output tokens. Inherits Carrel's default of 1600.
    model
        Optional model override. Defaults to the router's balanced
        model (matches what the non-streaming path picks).
    api_key
        Optional explicit key. Falls back to the ``ANTHROPIC_API_KEY``
        environment variable, which the Anthropic SDK reads natively.
    """
    if model is None:
        # Lazy import to avoid a circular through ai.router on cold start.
        from ai.router import get_default_router

        model = get_default_router().balanced_model

    if api_key is None and not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Streaming requires a Claude "
            "API key. AFM and Ollama streaming variants are a separate "
            "follow-up; see ai/streaming.py docstring."
        )

    client_kwargs: dict[str, str] = {}
    if api_key is not None:
        client_kwargs["api_key"] = api_key
    client = Anthropic(**client_kwargs)

    with client.messages.stream(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for delta in stream.text_stream:
            if delta:
                yield delta
