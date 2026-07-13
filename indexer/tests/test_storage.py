from __future__ import annotations

from pathlib import Path

import pytest

from app.api.storage import (
    StorageConfigurationError,
    verify_readable_directory,
    verify_writable_directory,
)


def test_verify_writable_directory_creates_directory_and_cleans_probe(tmp_path: Path) -> None:
    target = tmp_path / "output" / ".jobs"

    verify_writable_directory(target, label="Job-state directory")

    assert target.is_dir()
    assert list(target.iterdir()) == []


def test_verify_readable_directory_rejects_missing_path(tmp_path: Path) -> None:
    with pytest.raises(StorageConfigurationError, match="does not exist"):
        verify_readable_directory(tmp_path / "missing", label="Input root")
