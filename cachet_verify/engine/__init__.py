"""The kernel's engine internals (ADR-0014 step 3: Carrel adopts the kernel).

These modules moved here from ``services/legal``, ``services/retrieval``, and
``ai`` so that ``cachet_verify`` is self-contained: importing the kernel pulls
nothing from the app. The old paths remain as ``sys.modules`` alias shims until
every caller migrates; the modules themselves live here, once.
"""
