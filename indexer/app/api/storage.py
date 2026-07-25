from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4


class StorageConfigurationError(RuntimeError):
    """Raised when a required mounted directory is unavailable or unusable."""


def verify_readable_directory(path: Path, *, label: str) -> None:
    """Verify that a mounted input directory exists and can be listed."""

    if not path.exists():
        raise StorageConfigurationError(f"{label} does not exist: {path}")
    if not path.is_dir():
        raise StorageConfigurationError(f"{label} is not a directory: {path}")
    if not os.access(path, os.R_OK | os.X_OK):
        raise StorageConfigurationError(f"{label} is not readable: {path}")

    try:
        next(path.iterdir(), None)
    except OSError as exc:
        raise StorageConfigurationError(f"{label} cannot be listed: {path}: {exc}") from exc


def verify_writable_directory(path: Path, *, label: str) -> None:
    """Create a directory and prove that the running process can write to it."""

    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise StorageConfigurationError(f"{label} cannot be created: {path}: {exc}") from exc

    if not path.is_dir():
        raise StorageConfigurationError(f"{label} is not a directory: {path}")

    probe = path / f".documind-write-probe-{uuid4().hex}"
    try:
        probe.write_text("ok\n", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        probe.unlink(missing_ok=True)
        raise StorageConfigurationError(
            f"{label} is not writable: {path}. "
            "The Docker init-permissions service should prepare this mount automatically. "
            "Check `docker compose logs init-permissions` if this persists."
        ) from exc
