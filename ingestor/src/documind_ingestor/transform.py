from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from documind_ingestor.input_models import CanonicalDocument, ChunkingOutput
from documind_ingestor.output_models import OpenSearchChunkDocument


class DocumentMetadata(BaseModel):
    """Document-level metadata used to enrich every indexed chunk."""

    model_config = ConfigDict(extra="forbid")

    document_public_id: str | None = None
    document_title: str | None = None
    document_authors: list[str] = Field(default_factory=list)
    original_filename: str | None = None
    file_type: str | None = None
    language: str | None = None

    def merged_with(self, override: DocumentMetadata) -> DocumentMetadata:
        """Return a copy where non-empty values from `override` win."""

        return DocumentMetadata(
            document_public_id=override.document_public_id or self.document_public_id,
            document_title=override.document_title or self.document_title,
            document_authors=override.document_authors or self.document_authors,
            original_filename=override.original_filename or self.original_filename,
            file_type=override.file_type or self.file_type,
            language=override.language or self.language,
        )


def load_chunking_output(path: Path) -> ChunkingOutput:
    """Read and strictly validate one DocuMind `chunks.json` file."""

    try:
        return ChunkingOutput.model_validate_json(path.read_bytes())
    except OSError as exc:
        raise ValueError(f"Unable to read chunks JSON {path}: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 - preserve a concise CLI-facing error
        raise ValueError(f"Invalid chunks JSON {path}: {exc}") from exc


def load_canonical_document(path: Path) -> CanonicalDocument:
    """Read an optional canonical document for filename/author/language enrichment."""

    try:
        return CanonicalDocument.model_validate_json(path.read_bytes())
    except OSError as exc:
        raise ValueError(f"Unable to read canonical JSON {path}: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Invalid canonical JSON {path}: {exc}") from exc


def discover_canonical_document(
    output: ChunkingOutput,
    *,
    explicit_path: Path | None = None,
    chunks_json_path: Path | None = None,
    allowed_root: Path | None = None,
) -> tuple[CanonicalDocument | None, Path | None]:
    """Load an explicit canonical file or discover it from common indexer layouts."""

    if explicit_path is not None:
        normalized_explicit = explicit_path.resolve(strict=False)
        if allowed_root is not None:
            normalized_root = allowed_root.resolve(strict=False)
            try:
                normalized_explicit.relative_to(normalized_root)
            except ValueError as exc:
                raise ValueError(
                    f"Canonical JSON must be inside {normalized_root}: {normalized_explicit}"
                ) from exc
        return load_canonical_document(normalized_explicit), normalized_explicit

    candidates: list[Path] = []
    if output.input_directory:
        recorded = Path(output.input_directory)
        candidates.append(recorded / "canonical_document.json")
        if chunks_json_path is not None and not recorded.is_absolute():
            candidates.append(chunks_json_path.parent / recorded / "canonical_document.json")
    if chunks_json_path is not None:
        candidates.append(chunks_json_path.parent / "canonical_document.json")

    normalized_root = allowed_root.resolve(strict=False) if allowed_root is not None else None
    seen: set[Path] = set()
    for candidate in candidates:
        normalized = candidate.resolve(strict=False)
        if normalized in seen:
            continue
        seen.add(normalized)
        if normalized_root is not None:
            try:
                normalized.relative_to(normalized_root)
            except ValueError:
                continue
        if normalized.is_file():
            return load_canonical_document(normalized), normalized
    return None, None


def metadata_from_canonical(canonical: CanonicalDocument | None) -> DocumentMetadata:
    if canonical is None:
        return DocumentMetadata()

    filename = (
        _clean_optional(canonical.metadata.source_filename)
        or _clean_optional(canonical.document.filename)
        or _basename(canonical.document.source_pdf)
    )
    return DocumentMetadata(
        document_title=_clean_optional(canonical.metadata.title),
        document_authors=_normalize_authors(canonical.metadata.authors),
        original_filename=filename,
        file_type=_infer_file_type(filename),
        language=_clean_optional(canonical.metadata.language),
    )


def build_opensearch_documents(
    output: ChunkingOutput,
    *,
    metadata: DocumentMetadata | None = None,
    expected_embedding_dimensions: int = 1024,
    require_embeddings: bool = True,
    indexed_at: datetime | None = None,
) -> list[OpenSearchChunkDocument]:
    """Convert validated chunk records into the exact strict-mapping representation."""

    if expected_embedding_dimensions < 1:
        raise ValueError("expected_embedding_dimensions must be positive")

    if output.counts.total != len(output.chunks):
        raise ValueError(
            f"chunks JSON count mismatch: counts.total={output.counts.total}, "
            f"actual chunks={len(output.chunks)}"
        )
    if not output.chunks:
        raise ValueError(
            "chunks JSON contains no chunks; refusing a potentially destructive replacement"
        )

    metadata = metadata or DocumentMetadata()
    indexed_at = indexed_at or datetime.now(UTC)
    document_public_id = metadata.document_public_id or output.document_id
    file_type = metadata.file_type or _infer_file_type(metadata.original_filename) or "pdf"

    seen_ids: set[str] = set()
    documents: list[OpenSearchChunkDocument] = []
    for chunk in output.chunks:
        _validate_chunk_identity(output, chunk.user_id, chunk.document_id, chunk.source_document_id)
        if chunk.chunk_id in seen_ids:
            raise ValueError(f"Duplicate chunk_id in chunks JSON: {chunk.chunk_id}")
        seen_ids.add(chunk.chunk_id)

        embedding = chunk.embedding
        if embedding is not None and len(embedding) != expected_embedding_dimensions:
            raise ValueError(
                f"Chunk {chunk.chunk_id} has {len(embedding)} embedding values, but the "
                f"OpenSearch mapping expects {expected_embedding_dimensions}"
            )
        if (
            chunk.embedding_dimensions is not None
            and embedding is not None
            and chunk.embedding_dimensions != len(embedding)
        ):
            raise ValueError(
                f"Chunk {chunk.chunk_id} declares embedding_dimensions="
                f"{chunk.embedding_dimensions}, but contains {len(embedding)} values"
            )
        if chunk.embedding_status == "embedded" and embedding is None:
            raise ValueError(
                f"Chunk {chunk.chunk_id} says embedding_status=embedded but has no vector"
            )
        if require_embeddings and chunk.retrieval_enabled and embedding is None:
            raise ValueError(
                f"Retrieval-enabled chunk {chunk.chunk_id} has no embedding. "
                "Generate embeddings first or use --allow-missing-embeddings."
            )

        embedding_model = None
        embedding_dimensions = None
        if embedding is not None:
            embedding_model = chunk.embedding_model or output.embedding.model
            embedding_dimensions = len(embedding)
            if not embedding_model:
                raise ValueError(f"Chunk {chunk.chunk_id} has an embedding but no model name")

        document = OpenSearchChunkDocument(
            user_id=chunk.user_id,
            document_id=chunk.document_id,
            document_public_id=document_public_id,
            source_document_id=chunk.source_document_id,
            chunk_id=chunk.chunk_id,
            chunk_index=chunk.chunk_ordinal,
            source_type=chunk.source_type,
            chunk_role=chunk.chunk_role,
            parent_chunk_id=chunk.parent_chunk_id,
            child_chunk_ids=chunk.child_chunk_ids,
            source_ids=chunk.source_ids,
            retrieval_enabled=chunk.retrieval_enabled,
            oversized=chunk.oversized,
            document_title=metadata.document_title or chunk.title,
            document_authors=metadata.document_authors,
            original_filename=metadata.original_filename,
            file_type=file_type,
            language=metadata.language,
            section_id=chunk.section_id,
            section_path=chunk.section_path_parts,
            section_path_text=chunk.section_path or None,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            content=chunk.content,
            retrieval_text=chunk.retrieval_text,
            caption=chunk.caption,
            summary=chunk.summary,
            element_text=chunk.text,
            table_text=chunk.table_text,
            formula_text=chunk.formula_text,
            formula_latex=chunk.formula_latex,
            details=chunk.details,
            warnings=chunk.warnings,
            token_count=chunk.token_count,
            content_hash=chunk.content_hash,
            canonical_schema_version=output.canonical_schema_version,
            chunks_schema_version=output.output_schema_version,
            chunker_version=chunk.chunker_version,
            tokenizer_name=chunk.tokenizer_name,
            embedding_model=embedding_model,
            embedding_dimensions=embedding_dimensions,
            indexed_at=indexed_at,
            embedding=embedding,
        )
        documents.append(document)

    return documents


def _validate_chunk_identity(
    output: ChunkingOutput,
    user_id: str,
    document_id: str,
    source_document_id: str,
) -> None:
    expected = (output.user_id, output.document_id, output.source_document_id)
    actual = (user_id, document_id, source_document_id)
    if actual != expected:
        raise ValueError(
            "Chunk identity does not match the chunks JSON root: "
            f"expected={expected!r}, actual={actual!r}"
        )


def _normalize_authors(values: list[Any]) -> list[str]:
    authors: list[str] = []
    for value in values:
        rendered = _render_author(value)
        if rendered and rendered not in authors:
            authors.append(rendered)
    return authors


def _render_author(value: Any) -> str | None:
    if isinstance(value, str):
        return _clean_optional(value)
    if not isinstance(value, dict):
        return _clean_optional(str(value)) if value is not None else None

    for key in ("name", "full_name", "display_name", "raw"):
        rendered = _clean_optional(value.get(key))
        if rendered:
            return rendered

    parts = [
        _clean_optional(value.get(key))
        for key in ("first", "first_name", "given", "middle", "last", "last_name", "family")
    ]
    compact = " ".join(dict.fromkeys(part for part in parts if part))
    if compact:
        return compact

    # Keep unusual but valid canonical author structures searchable rather than dropping them.
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _clean_optional(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(str(value).split()).strip()
    return cleaned or None


def _basename(value: str | None) -> str | None:
    cleaned = _clean_optional(value)
    return Path(cleaned).name if cleaned else None


def _infer_file_type(filename: str | None) -> str | None:
    if not filename:
        return None
    suffix = Path(filename).suffix.lower().lstrip(".")
    return suffix or None
