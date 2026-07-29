from __future__ import annotations

import json
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any

from documind_ingestor.opensearch_client import (
    OpenSearchChunkIngestor,
    OpenSearchIngestionError,
    build_opensearch_client,
    install_index_template,
)
from documind_ingestor.transform import (
    DocumentMetadata,
    build_opensearch_documents,
    discover_canonical_document,
    load_chunking_output,
    metadata_from_canonical,
)


@dataclass(slots=True)
class _LockEntry:
    lock: Lock = field(default_factory=Lock)
    users: int = 0


_LOCKS_GUARD = Lock()
_DOCUMENT_LOCKS: dict[tuple[str, str, str, str], _LockEntry] = {}


@contextmanager
def _document_ingestion_lock(key: tuple[str, str, str, str]):
    """Serialise writes for the same OpenSearch document while allowing other documents."""

    with _LOCKS_GUARD:
        entry = _DOCUMENT_LOCKS.setdefault(key, _LockEntry())
        entry.users += 1
    entry.lock.acquire()
    try:
        yield
    finally:
        entry.lock.release()
        with _LOCKS_GUARD:
            entry.users -= 1
            if entry.users == 0:
                _DOCUMENT_LOCKS.pop(key, None)


@dataclass(slots=True)
class IngestionConfig:
    """Complete configuration for one ingestion operation."""

    input_path: Path | None
    input_filename: str = "chunks.json"
    allowed_input_root: Path | None = None
    url: str = "http://localhost:9200"
    index: str = "documind-chunks-v1"
    username: str | None = None
    password: str | None = None
    verify_certs: bool = False
    ca_certs: Path | None = None
    expected_embedding_dimensions: int = 1024
    batch_size: int = 250
    request_timeout_seconds: float = 120.0
    wait_timeout_seconds: float = 120.0
    wait_interval_seconds: float = 2.0
    install_template: bool = False
    template_name: str = "documind-chunks-template"
    template_file: Path | None = None
    allow_missing_embeddings: bool = False
    replace_document: bool = True
    refresh: bool = True
    canonical_json: Path | None = None
    metadata: DocumentMetadata = field(default_factory=DocumentMetadata)
    preview_output: Path | None = None
    dry_run: bool = False


def resolve_chunks_json(input_path: Path | None, *, input_filename: str) -> Path:
    """Resolve a file or directory input to an existing chunks JSON file."""

    if input_path is None:
        raise ValueError(
            "No input was provided. Pass a chunks.json file or directory, or set "
            "INPUT_FILE or INPUT_DIR."
        )
    if not input_filename or Path(input_filename).name != input_filename:
        raise ValueError("INPUT_FILENAME must be a filename, not a path")

    path = input_path.expanduser()
    if path.is_dir() or (not path.exists() and path.suffix.lower() != ".json"):
        path = path / input_filename

    if not path.is_file():
        raise ValueError(f"Input chunks file does not exist or is not a file: {path}")
    return path


def load_template(path: Path | None) -> dict[str, Any]:
    """Load and validate an OpenSearch index template JSON object."""

    if path is None:
        raise ValueError(
            "Template installation is enabled but OPENSEARCH_TEMPLATE_FILE/--template-file "
            "was not provided"
        )
    if not path.is_file():
        raise ValueError(f"OpenSearch template file does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"OpenSearch template is not valid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"OpenSearch template must be a JSON object: {path}")
    return payload


def wait_for_opensearch(
    client: Any,
    *,
    url: str,
    wait_timeout_seconds: float,
    wait_interval_seconds: float,
    request_timeout_seconds: float,
) -> dict[str, Any]:
    """Wait until OpenSearch responds or the configured deadline expires."""

    if wait_timeout_seconds < 0:
        raise ValueError("wait_timeout_seconds must be zero or positive")
    if wait_interval_seconds <= 0:
        raise ValueError("wait_interval_seconds must be positive")

    deadline = time.monotonic() + wait_timeout_seconds
    last_error: Exception | None = None
    while True:
        try:
            return client.info(request_timeout=request_timeout_seconds)
        except Exception as exc:  # OpenSearch exposes several transport exception types.
            last_error = exc
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(wait_interval_seconds, remaining))

    raise OpenSearchIngestionError(
        f"OpenSearch at {url} did not become reachable within "
        f"{wait_timeout_seconds:g} seconds: {last_error}"
    )


def ingest_chunks(config: IngestionConfig) -> dict[str, Any]:
    """Validate, transform, and optionally ingest one DocuMind chunks file."""

    chunks_json = resolve_chunks_json(
        config.input_path,
        input_filename=config.input_filename,
    )
    output = load_chunking_output(chunks_json)
    canonical, canonical_path = discover_canonical_document(
        output,
        explicit_path=config.canonical_json,
        chunks_json_path=chunks_json,
        allowed_root=config.allowed_input_root,
    )
    metadata = metadata_from_canonical(canonical).merged_with(config.metadata)
    documents = build_opensearch_documents(
        output,
        metadata=metadata,
        expected_embedding_dimensions=config.expected_embedding_dimensions,
        require_embeddings=not config.allow_missing_embeddings,
    )

    if config.preview_output is not None:
        config.preview_output.parent.mkdir(parents=True, exist_ok=True)
        config.preview_output.write_text(
            json.dumps(
                [document.source() for document in documents],
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

    vectors = sum(document.embedding is not None for document in documents)
    common_payload: dict[str, Any] = {
        "input_file": str(chunks_json),
        "user_id": output.user_id,
        "document_id": output.document_id,
        "chunks": len(documents),
        "vectors": vectors,
        "references_skipped": len(output.references),
        "canonical_file": str(canonical_path) if canonical_path is not None else None,
    }

    if config.dry_run:
        return {
            "status": "validated",
            **common_payload,
            "dry_run": True,
        }

    lock_key = (config.url, config.index, output.user_id, output.document_id)
    with _document_ingestion_lock(lock_key):
        client = build_opensearch_client(
            url=config.url,
            username=config.username,
            password=config.password,
            verify_certs=config.verify_certs,
            ca_certs=config.ca_certs,
            timeout_seconds=config.request_timeout_seconds,
        )
        try:
            info = wait_for_opensearch(
                client,
                url=config.url,
                wait_timeout_seconds=config.wait_timeout_seconds,
                wait_interval_seconds=config.wait_interval_seconds,
                request_timeout_seconds=config.request_timeout_seconds,
            )
            version = info.get("version", {}).get("number", "unknown")

            template_installed = False
            if config.install_template:
                template = load_template(config.template_file)
                install_index_template(
                    client,
                    name=config.template_name,
                    body=template,
                    request_timeout_seconds=config.request_timeout_seconds,
                )
                template_installed = True

            result = OpenSearchChunkIngestor(
                client=client,
                index=config.index,
                expected_embedding_dimensions=config.expected_embedding_dimensions,
                batch_size=config.batch_size,
                request_timeout_seconds=config.request_timeout_seconds,
            ).ingest(
                documents,
                user_id=output.user_id,
                document_id=output.document_id,
                replace_document=config.replace_document,
                refresh=config.refresh,
            )
        finally:
            client.close()

    return {
        "status": "done",
        **common_payload,
        "opensearch_url": config.url,
        "opensearch_version": version,
        "index": result.index,
        "indexed": result.indexed,
        "deleted_stale": result.deleted_stale,
        "previous_document_chunks": result.previous_document_chunks,
        "refreshed": result.refreshed,
        "template_installed": template_installed,
    }
