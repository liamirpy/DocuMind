from __future__ import annotations

from pathlib import Path


class PathResolutionError(ValueError):
    pass


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def resolve_mounted_directory(
    value: str,
    *,
    container_root: Path,
    host_root: Path | None,
    must_exist: bool,
    label: str,
) -> Path:
    """Resolve a request path safely beneath a mounted container root.

    The request may use:
    - a path relative to the configured root;
    - an absolute container path beneath the container root;
    - an absolute host path beneath the host root configured in `.env`.
    """

    raw = Path(value)
    container_root_resolved = container_root.resolve()

    if raw.is_absolute():
        raw_resolved = raw.resolve(strict=False)
        if _is_relative_to(raw_resolved, container_root_resolved):
            candidate = raw_resolved
        elif host_root is not None:
            host_root_resolved = host_root.resolve(strict=False)
            if not _is_relative_to(raw_resolved, host_root_resolved):
                raise PathResolutionError(
                    f"{label} must be beneath {host_root} on the host or "
                    f"{container_root} in the container"
                )
            candidate = container_root_resolved / raw_resolved.relative_to(host_root_resolved)
        else:
            raise PathResolutionError(
                f"Absolute {label} is not beneath the container root {container_root}"
            )
    else:
        candidate = container_root_resolved / raw

    resolved = candidate.resolve(strict=False)
    if not _is_relative_to(resolved, container_root_resolved):
        raise PathResolutionError(f"{label} escapes configured root {container_root}")

    if must_exist:
        if not resolved.exists():
            raise FileNotFoundError(f"{label} does not exist: {resolved}")
        if not resolved.is_dir():
            raise NotADirectoryError(f"{label} is not a directory: {resolved}")

    return resolved


def public_output_file(
    *,
    requested_output_directory: str,
    output_filename: str,
) -> str:
    return str(Path(requested_output_directory) / output_filename)
