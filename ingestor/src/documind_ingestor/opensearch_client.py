
from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from opensearchpy import OpenSearch, helpers

from documind_ingestor.output_models import OpenSearchChunkDocument

_INDEX_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


class OpenSearchIngestionError(RuntimeError):
    """Raised when OpenSearch validation or bulk ingestion fails."""


@dataclass(frozen=True)
class IngestionResult:
    index: str
    indexed: int
    deleted_stale: int
    previous_document_chunks: int
    refreshed: bool


def build_opensearch_client(
    *,
    url: str,
    username: str | None = None,
    password: str | None = None,
    verify_certs: bool = False,
    ca_certs: Path | None = None,
    timeout_seconds: float = 60.0,
) -> OpenSearch:
    """Build a low-level OpenSearch client from one HTTP(S) URL."""

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("OpenSearch URL must look like http://host:9200 or https://host:9200")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("OpenSearch URL must not contain a path, query string, or fragment")
    if (username is None) != (password is None):
        raise ValueError("Provide both OpenSearch username and password, or neither")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")

    use_ssl = parsed.scheme == "https"
    host = {
        "host": parsed.hostname,
        "port": parsed.port or (443 if use_ssl else 80),
        "scheme": parsed.scheme,
    }
    kwargs: dict[str, Any] = {
        "hosts": [host],
        "use_ssl": use_ssl,
        "verify_certs": verify_certs,
        "ssl_show_warn": verify_certs,
        "timeout": timeout_seconds,
        "max_retries": 3,
        "retry_on_timeout": True,
    }
    if username is not None and password is not None:
        kwargs["http_auth"] = (username, password)
    if ca_certs is not None:
        kwargs["ca_certs"] = str(ca_certs)
    return OpenSearch(**kwargs)


def install_index_template(
    client: OpenSearch,
    *,
    name: str,
    body: dict[str, Any],
    request_timeout_seconds: float = 120.0,
) -> None:
    """Create or update a composable OpenSearch index template."""

    if not name.strip():
        raise ValueError("OpenSearch template name must not be empty")
    if request_timeout_seconds <= 0:
        raise ValueError("request_timeout_seconds must be positive")
    client.indices.put_index_template(
        name=name,
        body=body,
        request_timeout=request_timeout_seconds,
    )


class OpenSearchChunkIngestor:
    """Validate an index, bulk-upsert chunks, then remove stale chunks safely."""

    def __init__(
        self,
        *,
        client: OpenSearch,
        index: str,
        expected_embedding_dimensions: int = 1024,
        batch_size: int = 250,
        request_timeout_seconds: float = 120.0,
    ) -> None:
        _validate_index_name(index)
        if expected_embedding_dimensions < 1:
            raise ValueError("expected_embedding_dimensions must be positive")
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        if request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be positive")

        self.client = client
        self.index = index
        self.expected_embedding_dimensions = expected_embedding_dimensions
        self.batch_size = batch_size
        self.request_timeout_seconds = request_timeout_seconds

    def ingest(
        self,
        documents: list[OpenSearchChunkDocument],
        *,
        user_id: str,
        document_id: str,
        replace_document: bool = True,
        refresh: bool = True,
    ) -> IngestionResult:
        """Upsert a complete document and delete stale old chunks only after success."""

        self._verify_documents(documents, user_id=user_id, document_id=document_id)
        self.ensure_compatible_index()

        new_ids = {document.chunk_id for document in documents}
        old_ids = (
            self._existing_chunk_ids(user_id=user_id, document_id=document_id)
            if replace_document
            else set()
        )

        indexed = self._run_bulk(
            self._index_actions(documents),
            operation_name="index",
        )

        stale_ids = old_ids - new_ids
        deleted = self._run_bulk(
            self._delete_actions(stale_ids),
            operation_name="delete stale",
            ignored_statuses=(404,),
        )

        if refresh:
            self.client.indices.refresh(
                index=self.index,
                request_timeout=self.request_timeout_seconds,
            )

        return IngestionResult(
            index=self.index,
            indexed=indexed,
            deleted_stale=deleted,
            previous_document_chunks=len(old_ids),
            refreshed=refresh,
        )

    def ensure_compatible_index(self) -> None:
        """Create the index through its template if needed, then verify the key mapping."""

        created = False
        if not self.client.indices.exists(index=self.index):
            self.client.indices.create(
                index=self.index,
                request_timeout=self.request_timeout_seconds,
            )
            created = True

        mapping_response = self.client.indices.get_mapping(
            index=self.index,
            request_timeout=self.request_timeout_seconds,
        )
        settings_response = self.client.indices.get_settings(
            index=self.index,
            flat_settings=True,
            request_timeout=self.request_timeout_seconds,
        )
        try:
            index_mapping = mapping_response[self.index].get("mappings", {})
            index_settings = settings_response[self.index].get("settings", {})
            self._verify_mapping(index_mapping)
            self._verify_settings(index_settings)
        except OpenSearchIngestionError:
            if created:
                self.client.indices.delete(
                    index=self.index,
                    ignore=[404],
                    request_timeout=self.request_timeout_seconds,
                )
            raise

    def _verify_settings(self, settings: dict[str, Any]) -> None:
        knn_enabled = settings.get("index.knn")
        if knn_enabled is None:
            index_settings = settings.get("index", {})
            if isinstance(index_settings, dict):
                knn_enabled = index_settings.get("knn")
        if str(knn_enabled).lower() != "true":
            raise OpenSearchIngestionError(
                f"Index {self.index!r} does not have index.knn=true. "
                "Install the DocuMind index template before creating the index."
            )

    def _verify_mapping(self, mappings: dict[str, Any]) -> None:
        if mappings.get("dynamic") != "strict":
            raise OpenSearchIngestionError(
                f"Index {self.index!r} is not using dynamic=strict. "
                "Install the DocuMind index template before creating the index."
            )

        properties = mappings.get("properties")
        if not isinstance(properties, dict):
            raise OpenSearchIngestionError(f"Index {self.index!r} has no field mappings")

        expected_types = {
            "user_id": "keyword",
            "document_id": "keyword",
            "chunk_id": "keyword",
            "chunk_index": "integer",
            "content": "text",
            "retrieval_text": "text",
            "embedding": "knn_vector",
        }
        for field, expected_type in expected_types.items():
            actual = properties.get(field, {}).get("type")
            if actual != expected_type:
                raise OpenSearchIngestionError(
                    f"Index {self.index!r} field {field!r} has type {actual!r}; "
                    f"expected {expected_type!r}"
                )

        actual_dimensions = properties["embedding"].get("dimension")
        if actual_dimensions != self.expected_embedding_dimensions:
            raise OpenSearchIngestionError(
                f"Index {self.index!r} embedding dimension is {actual_dimensions!r}; "
                f"expected {self.expected_embedding_dimensions}"
            )

    def _verify_documents(
        self,
        documents: list[OpenSearchChunkDocument],
        *,
        user_id: str,
        document_id: str,
    ) -> None:
        seen_ids: set[str] = set()
        for document in documents:
            if document.user_id != user_id or document.document_id != document_id:
                raise ValueError(
                    f"Chunk {document.chunk_id} belongs to "
                    f"({document.user_id}, {document.document_id}), not "
                    f"({user_id}, {document_id})"
                )
            if document.chunk_id in seen_ids:
                raise ValueError(f"Duplicate chunk_id in ingestion batch: {document.chunk_id}")
            seen_ids.add(document.chunk_id)

    def _existing_chunk_ids(self, *, user_id: str, document_id: str) -> set[str]:
        query = {
            "_source": False,
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"user_id": user_id}},
                        {"term": {"document_id": document_id}},
                    ]
                }
            },
        }
        return {
            hit["_id"]
            for hit in helpers.scan(
                self.client,
                index=self.index,
                query=query,
                size=self.batch_size,
                scroll="2m",
                request_timeout=self.request_timeout_seconds,
            )
        }

    def _index_actions(
        self,
        documents: Iterable[OpenSearchChunkDocument],
    ) -> Iterator[dict[str, Any]]:
        for document in documents:
            yield {
                "_op_type": "index",
                "_index": self.index,
                "_id": document.chunk_id,
                "_source": document.source(),
            }

    def _delete_actions(self, chunk_ids: Iterable[str]) -> Iterator[dict[str, Any]]:
        for chunk_id in chunk_ids:
            yield {
                "_op_type": "delete",
                "_index": self.index,
                "_id": chunk_id,
            }

    def _run_bulk(
        self,
        actions: Iterable[dict[str, Any]],
        *,
        operation_name: str,
        ignored_statuses: tuple[int, ...] = (),
    ) -> int:
        success_count = 0
        failures: list[str] = []
        for ok, item in helpers.streaming_bulk(
            self.client,
            actions,
            chunk_size=self.batch_size,
            max_retries=3,
            initial_backoff=1,
            max_backoff=8,
            raise_on_error=False,
            raise_on_exception=True,
            yield_ok=True,
            ignore_status=ignored_statuses,
            request_timeout=self.request_timeout_seconds,
        ):
            if ok:
                success_count += 1
                continue
            if len(failures) < 5:
                failures.append(_format_bulk_failure(item))

        if failures:
            detail = "; ".join(failures)
            raise OpenSearchIngestionError(
                f"OpenSearch bulk {operation_name} failed. First errors: {detail}"
            )
        return success_count


def _format_bulk_failure(item: dict[str, Any]) -> str:
    operation, payload = next(iter(item.items()))
    status = payload.get("status")
    error = payload.get("error")
    document_id = payload.get("_id")
    return f"operation={operation}, _id={document_id}, status={status}, error={error}"


def _validate_index_name(index: str) -> None:
    if not _INDEX_NAME.fullmatch(index):
        raise ValueError(
            "OpenSearch index names must be lowercase and contain only letters, digits, "
            "dots, underscores, or hyphens"
        )
    if index.startswith(("_", "-", "+")) or index in {".", ".."}:
        raise ValueError(f"Invalid OpenSearch index name: {index!r}")
    if len(index.encode("utf-8")) > 255:
        raise ValueError("OpenSearch index name must be at most 255 bytes")
