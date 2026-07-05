"""Strangler-fig alias (ADR-0014 step 3): this module moved into the kernel at
``cachet_verify.engine.citations_eyecite``. The ``sys.modules`` swap below makes
this import path THE same module object, so existing imports and test
monkeypatches keep working unchanged. Delete this shim when no importer
remains."""

import sys

from cachet_verify.engine import citations_eyecite as _module

sys.modules[__name__] = _module
