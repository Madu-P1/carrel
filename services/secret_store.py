"""Generic process-wide secret store.

A name → value credential store for app secrets that must not land in
SQLite or `.env` — the Claude API key first and foremost.

This is a direct generalization of ``services/calendar/secrets.py``
(the calendar-feed-URL store): same three-class shape
(``MacOSKeychain*`` + ``Fallback*`` + ``Memory*``) and the
``default_*_store()`` singleton + ``set_default_*_store_for_testing()``
seam. Where the calendar store keys by ``feed_id``, this one keys by a
free-form ``name`` (e.g. ``carrel.ai.anthropic-key``).

On macOS the value is held in the login Keychain via the ``security``
CLI. In CI, unsigned local builds, or non-Darwin hosts the Keychain is
unavailable, so a process-memory fallback keeps the secret out of
SQLite while the process runs. The memory fallback is intentionally
non-durable: it is the honest behaviour for an environment that has no
secure credential service.
"""

from __future__ import annotations

import platform
import subprocess
from dataclasses import dataclass
from typing import Protocol


# Fixed Keychain account for every Carrel secret; the per-secret
# identity lives in the service id derived from `name`.
_KEYCHAIN_ACCOUNT = "carrel"


class SecretStore(Protocol):
    def store_secret(self, name: str, value: str) -> None: ...

    def get_secret(self, name: str) -> str | None: ...

    def delete_secret(self, name: str) -> None: ...


@dataclass(frozen=True)
class SecretStoreError(Exception):
    reason: str


class MemorySecretStore:
    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    def store_secret(self, name: str, value: str) -> None:
        self._values[name] = value

    def get_secret(self, name: str) -> str | None:
        return self._values.get(name)

    def delete_secret(self, name: str) -> None:
        self._values.pop(name, None)


class FallbackSecretStore:
    """Try the platform store, then keep running with process memory.

    Keychain can be unavailable in headless CI, locked desktop sessions,
    or unsigned local builds. The fallback keeps secrets out of SQLite
    even when the OS credential service is not reachable.
    """

    def __init__(self, primary: SecretStore, fallback: SecretStore) -> None:
        self._primary = primary
        self._fallback = fallback

    def store_secret(self, name: str, value: str) -> None:
        try:
            self._primary.store_secret(name, value)
        except SecretStoreError:
            self._fallback.store_secret(name, value)

    def get_secret(self, name: str) -> str | None:
        value = self._primary.get_secret(name)
        return value if value is not None else self._fallback.get_secret(name)

    def delete_secret(self, name: str) -> None:
        self._primary.delete_secret(name)
        self._fallback.delete_secret(name)


class MacOSKeychainSecretStore:
    """Login-Keychain backed store via the `security` CLI.

    Service id is the secret `name` verbatim; account is the fixed
    ``carrel`` constant. Mirrors ``MacOSKeychainCalendarSecretStore``.
    """

    def store_secret(self, name: str, value: str) -> None:
        self._run_security(
            [
                "add-generic-password",
                "-a",
                _KEYCHAIN_ACCOUNT,
                "-s",
                name,
                "-w",
                value,
                "-U",
            ]
        )

    def get_secret(self, name: str) -> str | None:
        try:
            result = self._run_security(
                ["find-generic-password", "-a", _KEYCHAIN_ACCOUNT, "-s", name, "-w"]
            )
        except SecretStoreError:
            return None
        value = result.stdout.strip()
        return value or None

    def delete_secret(self, name: str) -> None:
        try:
            self._run_security(["delete-generic-password", "-a", _KEYCHAIN_ACCOUNT, "-s", name])
        except SecretStoreError:
            return

    def _run_security(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                ["security", *args],
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise SecretStoreError(exc.__class__.__name__) from exc


_MEMORY_STORE = MemorySecretStore()
_STORE: SecretStore | None = None


def default_secret_store() -> SecretStore:
    global _STORE
    if _STORE is None:
        _STORE = (
            FallbackSecretStore(MacOSKeychainSecretStore(), _MEMORY_STORE)
            if platform.system() == "Darwin"
            else _MEMORY_STORE
        )
    return _STORE


def set_default_secret_store_for_testing(store: SecretStore | None) -> None:
    global _STORE
    _STORE = store


def store_secret(name: str, value: str) -> None:
    """Persist ``value`` under ``name`` in the active secret store."""
    default_secret_store().store_secret(name, value)


def get_secret(name: str) -> str | None:
    """Return the stored value for ``name``, or ``None`` if unset."""
    return default_secret_store().get_secret(name)


def delete_secret(name: str) -> None:
    """Remove ``name`` from the active secret store. No-op if unset."""
    default_secret_store().delete_secret(name)
