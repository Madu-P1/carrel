"""Shared finding shape for the vendored self-contradiction detectors.

Copied verbatim (only the needed symbols) from
``services/legal/structural_integrity.py`` so the kernel stays self-contained:
the freeze bundles ``cachet_verify`` only, never ``services``. The disposition
vocabulary maps onto the product's 3-state tray:

* ``FLAGGED`` - a real, confident defect (the catch).
* ``COULD_NOT_CHECK`` - an honest gap.

There is deliberately no ``verified`` disposition: a check that passes is
silent, which holds the no-green-badge stance.
"""

from __future__ import annotations

from dataclasses import dataclass

# Disposition constants (never bare string literals at call sites: a typo would
# silently misroute a loud catch into an unrecognized state).
FLAGGED = "flagged"
COULD_NOT_CHECK = "could_not_check"


@dataclass(frozen=True)
class StructuralFinding:
    kind: str
    disposition: str  # FLAGGED | COULD_NOT_CHECK
    detail: str
    span: str
    start: int
    end: int
    target: str | None = None
