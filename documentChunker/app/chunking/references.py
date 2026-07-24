from __future__ import annotations

from typing import Any

from app.chunking.common import clean_text, sha256_text, unique_nonempty
from app.chunking.config import ChunkingConfig
from app.chunking.models import IngestionContext, ReferenceRecord
from app.input_package.reader import InputPackage


class ReferenceProcessor:
    """Keep bibliography entries as separate structured records, not RAG chunks."""

    def __init__(self, *, config: ChunkingConfig) -> None:
        self.config = config

    def process(
        self,
        *,
        package: InputPackage,
        context: IngestionContext,
    ) -> list[ReferenceRecord]:
        if not self.config.references.enabled:
            return []

        records: list[ReferenceRecord] = []
        for ordinal, reference in enumerate(package.canonical.content.references, start=1):
            authors = self._authors(reference.authors)
            title = clean_text(reference.title) or None
            year = clean_text(reference.year) or None
            doi = clean_text(reference.doi) or None
            raw_text = clean_text(reference.raw) or None

            if not raw_text:
                raw_text = self._fallback_raw(
                    title=title,
                    authors=authors,
                    year=year,
                    doi=doi,
                )

            source_reference_id = clean_text(reference.id) or None
            identity_text = raw_text or "|".join(
                [source_reference_id or "", title or "", year or "", doi or ""]
            )
            reference_id = sha256_text(
                "|".join(
                    [
                        context.user_id,
                        context.document_id,
                        source_reference_id or str(ordinal),
                        identity_text,
                    ]
                )
            )

            retrieval_text = None
            if self.config.references.generate_retrieval_text:
                retrieval_text = self._retrieval_text(
                    title=title,
                    authors=authors,
                    year=year,
                    doi=doi,
                    raw_text=raw_text,
                )

            records.append(
                ReferenceRecord(
                    user_id=context.user_id,
                    document_id=context.document_id,
                    source_document_id=package.canonical.document_id,
                    reference_id=reference_id,
                    reference_ordinal=ordinal,
                    source_reference_id=source_reference_id,
                    title=(title if self.config.references.include_structured_metadata else None),
                    authors=(authors if self.config.references.include_structured_metadata else []),
                    year=(year if self.config.references.include_structured_metadata else None),
                    doi=(doi if self.config.references.include_structured_metadata else None),
                    raw_text=(raw_text if self.config.references.include_raw_text else None),
                    retrieval_enabled=self.config.references.retrieval_enabled,
                    retrieval_text=retrieval_text,
                    metadata={
                        "coords": reference.coords,
                        "canonical_extra": reference.model_extra or {},
                    },
                )
            )

        return records

    @staticmethod
    def _authors(values: list[Any]) -> list[str]:
        authors: list[str] = []
        for value in values:
            if isinstance(value, str):
                text = clean_text(value)
            elif isinstance(value, dict):
                text = ReferenceProcessor._author_from_dict(value)
            else:
                text = clean_text(value)
            if text:
                authors.append(text)
        return list(dict.fromkeys(authors))

    @staticmethod
    def _author_from_dict(value: dict[str, Any]) -> str:
        direct = clean_text(value.get("name") or value.get("text") or value.get("full_name"))
        if direct:
            return direct
        given = clean_text(value.get("given") or value.get("first") or value.get("forename"))
        family = clean_text(value.get("family") or value.get("last") or value.get("surname"))
        return clean_text(" ".join(part for part in (given, family) if part))

    @staticmethod
    def _fallback_raw(
        *,
        title: str | None,
        authors: list[str],
        year: str | None,
        doi: str | None,
    ) -> str | None:
        parts = []
        if authors:
            parts.append(", ".join(authors))
        if title:
            parts.append(title)
        if year:
            parts.append(year)
        if doi:
            parts.append(f"DOI: {doi}")
        value = ". ".join(parts)
        return value or None

    @staticmethod
    def _retrieval_text(
        *,
        title: str | None,
        authors: list[str],
        year: str | None,
        doi: str | None,
        raw_text: str | None,
    ) -> str:
        lines = ["Reference record"]
        if title:
            lines.append(f"Title: {title}")
        if authors:
            lines.append(f"Authors: {'; '.join(authors)}")
        if year:
            lines.append(f"Year: {year}")
        if doi:
            lines.append(f"DOI: {doi}")
        if raw_text:
            lines.append(f"Citation: {raw_text}")
        return "\n".join(unique_nonempty(lines))
