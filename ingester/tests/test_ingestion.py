from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from documind_ingestor.opensearch_client import (
    OpenSearchChunkIngestor,
    OpenSearchIngestionError,
)
from documind_ingestor.transform import (
    build_opensearch_documents,
    discover_canonical_document,
    load_chunking_output,
    metadata_from_canonical,
)

ROOT = Path(__file__).resolve().parents[1]
CHUNKS_PATH = ROOT / "examples" / "chunks.json"
TEMPLATE_PATH = ROOT / "templates" / "documind-chunks-template.json"


def _documents():
    output = load_chunking_output(CHUNKS_PATH)
    canonical, _ = discover_canonical_document(output, chunks_json_path=CHUNKS_PATH)
    metadata = metadata_from_canonical(canonical)
    documents = build_opensearch_documents(
        output,
        metadata=metadata,
        expected_embedding_dimensions=32,
    )
    return output, documents


def _mapping() -> dict[str, Any]:
    template = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    mapping = template["template"]["mappings"]
    mapping["properties"]["embedding"]["dimension"] = 32
    return mapping


def test_transform_emits_only_strict_mapping_fields() -> None:
    output, documents = _documents()
    properties = _mapping()["properties"]

    assert len(documents) == output.counts.total
    for document in documents:
        source = document.source()
        assert set(source) <= set(properties)
        assert "chunk_ordinal" not in source
        assert "title" not in source
        assert "text" not in source
        assert "metadata" not in source

    parent = next(document for document in documents if document.chunk_role == "parent")
    child = next(document for document in documents if document.retrieval_enabled)
    assert parent.chunk_index == 1
    assert parent.document_title == "A Small Retrieval Paper"
    assert parent.document_authors == ["A. Researcher"]
    assert parent.section_path == ["Introduction"]
    assert parent.section_path_text == "Introduction"
    assert parent.embedding is None
    assert "embedding" not in parent.source()
    assert child.embedding is not None
    assert len(child.embedding) == 32
    assert child.embedding_model == "development-hash-v1"


def test_transform_rejects_vector_dimension_mismatch() -> None:
    output = load_chunking_output(CHUNKS_PATH)
    with pytest.raises(ValueError, match="mapping expects 1024"):
        build_opensearch_documents(output, expected_embedding_dimensions=1024)


def test_transform_rejects_missing_retrieval_embedding() -> None:
    output = load_chunking_output(CHUNKS_PATH)
    target = next(chunk for chunk in output.chunks if chunk.retrieval_enabled)
    target.embedding = None
    target.embedding_dimensions = None
    target.embedding_status = "disabled"

    with pytest.raises(ValueError, match="has no embedding"):
        build_opensearch_documents(output, expected_embedding_dimensions=32)


class _FakeIndices:
    def __init__(self, mapping: dict[str, Any]) -> None:
        self.mapping = mapping
        self.refreshed = False

    def exists(self, **_: Any) -> bool:
        return True

    def get_mapping(self, *, index: str, **_: Any) -> dict[str, Any]:
        return {index: {"mappings": self.mapping}}

    def get_settings(self, *, index: str, **_: Any) -> dict[str, Any]:
        return {index: {"settings": {"index.knn": "true"}}}

    def refresh(self, **_: Any) -> None:
        self.refreshed = True


class _FakeClient:
    def __init__(self, mapping: dict[str, Any]) -> None:
        self.indices = _FakeIndices(mapping)


def test_ingestor_upserts_before_deleting_stale_chunks(monkeypatch) -> None:
    output, documents = _documents()
    client = _FakeClient(_mapping())
    calls: list[list[dict[str, Any]]] = []
    existing_id = documents[0].chunk_id
    stale_id = "a" * 64

    def fake_scan(*_: Any, **__: Any):
        yield {"_id": existing_id}
        yield {"_id": stale_id}

    def fake_streaming_bulk(_: Any, actions, **__: Any):
        materialized = list(actions)
        calls.append(materialized)
        for action in materialized:
            operation = action["_op_type"]
            yield True, {operation: {"_id": action["_id"], "status": 200}}

    monkeypatch.setattr("documind_ingestor.opensearch_client.helpers.scan", fake_scan)
    monkeypatch.setattr(
        "documind_ingestor.opensearch_client.helpers.streaming_bulk",
        fake_streaming_bulk,
    )

    ingestor = OpenSearchChunkIngestor(
        client=client,
        index="documind-chunks-v1",
        expected_embedding_dimensions=32,
    )
    result = ingestor.ingest(
        documents,
        user_id=output.user_id,
        document_id=output.document_id,
    )

    assert len(calls) == 2
    assert all(action["_op_type"] == "index" for action in calls[0])
    assert calls[1] == [{"_op_type": "delete", "_index": "documind-chunks-v1", "_id": stale_id}]
    assert result.indexed == len(documents)
    assert result.deleted_stale == 1
    assert result.previous_document_chunks == 2
    assert client.indices.refreshed is True


def test_ingestor_does_not_delete_stale_chunks_after_bulk_failure(monkeypatch) -> None:
    output, documents = _documents()
    client = _FakeClient(_mapping())
    bulk_calls = 0

    def fake_scan(*_: Any, **__: Any):
        yield {"_id": "b" * 64}

    def fake_streaming_bulk(_: Any, actions, **__: Any):
        nonlocal bulk_calls
        bulk_calls += 1
        action = next(iter(actions))
        yield (
            False,
            {
                "index": {
                    "_id": action["_id"],
                    "status": 400,
                    "error": {"type": "mapper_parsing_exception"},
                }
            },
        )

    monkeypatch.setattr("documind_ingestor.opensearch_client.helpers.scan", fake_scan)
    monkeypatch.setattr(
        "documind_ingestor.opensearch_client.helpers.streaming_bulk",
        fake_streaming_bulk,
    )

    ingestor = OpenSearchChunkIngestor(
        client=client,
        index="documind-chunks-v1",
        expected_embedding_dimensions=32,
    )
    with pytest.raises(OpenSearchIngestionError, match="bulk index failed"):
        ingestor.ingest(
            documents,
            user_id=output.user_id,
            document_id=output.document_id,
        )

    assert bulk_calls == 1
    assert client.indices.refreshed is False
