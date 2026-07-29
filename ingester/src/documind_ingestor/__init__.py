"""Standalone adapter that loads DocuMind indexer output into OpenSearch."""

from documind_ingestor.opensearch_client import (
    IngestionResult,
    OpenSearchChunkIngestor,
    OpenSearchIngestionError,
    build_opensearch_client,
)
from documind_ingestor.service import IngestionConfig, ingest_chunks
from documind_ingestor.transform import (
    DocumentMetadata,
    build_opensearch_documents,
    discover_canonical_document,
    load_chunking_output,
    metadata_from_canonical,
)

__all__ = [
    "DocumentMetadata",
    "IngestionConfig",
    "IngestionResult",
    "OpenSearchChunkIngestor",
    "OpenSearchIngestionError",
    "build_opensearch_client",
    "build_opensearch_documents",
    "discover_canonical_document",
    "load_chunking_output",
    "ingest_chunks",
    "metadata_from_canonical",
]
