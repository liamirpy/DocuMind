import hashlib
import json
import os
import re
import shutil
import tempfile
import unicodedata
from pathlib import Path
from typing import Any, BinaryIO

from fastapi import UploadFile

_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
_SAFE_OUTPUT_FOLDER_RE = re.compile(r"[^A-Za-z0-9._-]+")
_MAX_OUTPUT_FOLDER_LENGTH = 100
_WINDOWS_RESERVED_OUTPUT_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


def safe_filename(filename: str | None) -> str:
    candidate = Path(filename or "document.pdf").name
    candidate = _SAFE_FILENAME_RE.sub("_", candidate).strip("._")
    return candidate or "document.pdf"


def safe_output_folder(value: str) -> str:
    """Return a single safe output-directory name.

    The value is a name, not a path. Path separators and traversal tokens are
    rejected so callers can never escape the configured output root.
    """

    normalized = unicodedata.normalize("NFKC", value).strip()
    if not normalized:
        raise ValueError("Output folder name cannot be empty.")
    if normalized in {".", ".."} or "/" in normalized or "\\" in normalized:
        raise ValueError("Output folder must be a name, not a path.")

    candidate = _SAFE_OUTPUT_FOLDER_RE.sub("_", normalized).strip("._-")
    candidate = candidate[:_MAX_OUTPUT_FOLDER_LENGTH].rstrip("._-")
    if not candidate or candidate in {".", ".."}:
        raise ValueError("Output folder name contains no usable characters.")
    if candidate.upper() in _WINDOWS_RESERVED_OUTPUT_NAMES:
        raise ValueError("Output folder name is reserved by Windows.")
    return candidate


def validate_output_folder(value: str) -> str:
    """Validate that a URL path component is already in canonical safe form."""

    candidate = safe_output_folder(value)
    if candidate != value:
        raise ValueError("Invalid output folder name.")
    return candidate


async def save_upload_to_temp(
    upload: UploadFile,
    *,
    max_bytes: int,
) -> tuple[Path, str, int]:
    suffix = Path(upload.filename or "document.pdf").suffix.lower() or ".pdf"
    fd, temporary_name = tempfile.mkstemp(prefix="pdf-agent-", suffix=suffix)
    os.close(fd)
    path = Path(temporary_name)
    digest = hashlib.sha256()
    size = 0

    try:
        with path.open("wb") as output:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    raise ValueError(f"Upload exceeds the {max_bytes} byte limit.")
                digest.update(chunk)
                output.write(chunk)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()

    return path, digest.hexdigest(), size


def copy_stream_and_hash(
    source: BinaryIO,
    destination: Path,
    *,
    max_bytes: int,
) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as output:
        while chunk := source.read(1024 * 1024):
            size += len(chunk)
            if size > max_bytes:
                destination.unlink(missing_ok=True)
                raise ValueError(f"Input exceeds the {max_bytes} byte limit.")
            digest.update(chunk)
            output.write(chunk)
    return digest.hexdigest(), size


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    temporary.replace(path)


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def recreate_directory(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def join_url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}/{path.lstrip('/')}"


def relative_posix(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()
