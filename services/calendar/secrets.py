from __future__ import annotations

import platform
import subprocess
from dataclasses import dataclass
from typing import Protocol


class CalendarSecretStore(Protocol):
    def store_url(self, feed_id: str, raw_url: str) -> str:
        ...

    def get_url(self, reference: str) -> str | None:
        ...

    def delete_url(self, reference: str) -> None:
        ...


@dataclass(frozen=True)
class CalendarSecretStoreError(Exception):
    reason: str


class MemoryCalendarSecretStore:
    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    def store_url(self, feed_id: str, raw_url: str) -> str:
        reference = f"memory:calendar-feed:{feed_id}"
        self._values[reference] = raw_url
        return reference

    def get_url(self, reference: str) -> str | None:
        return self._values.get(reference)

    def delete_url(self, reference: str) -> None:
        self._values.pop(reference, None)


class FallbackCalendarSecretStore:
    """Try the platform store, then keep running with process memory.

    Keychain can be unavailable in headless CI, locked desktop sessions, or
    unsigned local builds. The fallback keeps raw feed URLs out of SQLite even
    when the OS credential service is not reachable.
    """

    def __init__(
        self,
        primary: CalendarSecretStore,
        fallback: CalendarSecretStore,
    ) -> None:
        self._primary = primary
        self._fallback = fallback

    def store_url(self, feed_id: str, raw_url: str) -> str:
        try:
            return self._primary.store_url(feed_id, raw_url)
        except CalendarSecretStoreError:
            return self._fallback.store_url(feed_id, raw_url)

    def get_url(self, reference: str) -> str | None:
        value = self._primary.get_url(reference)
        return value if value is not None else self._fallback.get_url(reference)

    def delete_url(self, reference: str) -> None:
        self._primary.delete_url(reference)
        self._fallback.delete_url(reference)


class MacOSKeychainCalendarSecretStore:
    _SERVICE_PREFIX = "carrel.calendar.feed"

    def store_url(self, feed_id: str, raw_url: str) -> str:
        service = self._service(feed_id)
        self._run_security(
            [
                "add-generic-password",
                "-a",
                feed_id,
                "-s",
                service,
                "-w",
                raw_url,
                "-U",
            ]
        )
        return f"keychain:{service}:{feed_id}"

    def get_url(self, reference: str) -> str | None:
        parsed = self._parse_reference(reference)
        if parsed is None:
            return None
        service, account = parsed
        try:
            result = self._run_security(
                ["find-generic-password", "-a", account, "-s", service, "-w"]
            )
        except CalendarSecretStoreError:
            return None
        value = result.stdout.strip()
        return value or None

    def delete_url(self, reference: str) -> None:
        parsed = self._parse_reference(reference)
        if parsed is None:
            return
        service, account = parsed
        try:
            self._run_security(["delete-generic-password", "-a", account, "-s", service])
        except CalendarSecretStoreError:
            return

    def _service(self, feed_id: str) -> str:
        return f"{self._SERVICE_PREFIX}.{feed_id}"

    def _parse_reference(self, reference: str) -> tuple[str, str] | None:
        if not reference.startswith("keychain:"):
            return None
        _, service, account = reference.split(":", 2)
        if not service or not account:
            return None
        return service, account

    def _run_security(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                ["security", *args],
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise CalendarSecretStoreError(exc.__class__.__name__) from exc


_MEMORY_STORE = MemoryCalendarSecretStore()
_STORE: CalendarSecretStore | None = None


def default_secret_store() -> CalendarSecretStore:
    global _STORE
    if _STORE is None:
        _STORE = (
            FallbackCalendarSecretStore(MacOSKeychainCalendarSecretStore(), _MEMORY_STORE)
            if platform.system() == "Darwin"
            else _MEMORY_STORE
        )
    return _STORE


def set_default_secret_store_for_testing(store: CalendarSecretStore | None) -> None:
    global _STORE
    _STORE = store
