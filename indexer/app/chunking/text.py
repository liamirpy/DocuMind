from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import groupby

from app.canonical.models import CanonicalDocument, CanonicalParagraph
from app.chunking.common import (
    is_reference_section,
    make_chunk_id,
    page_range,
    path_text,
    sha256_text,
)
from app.chunking.config import ChunkingConfig, WindowConfig
from app.chunking.models import ChunkRecord, IngestionContext
from app.chunking.provenance import details_for_source_locations, paragraph_source_locations
from app.chunking.token_counter import TokenCounter

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


@dataclass(frozen=True)
class _TextUnit:
    text: str
    paragraph_id: str
    section_id: str
    section_path: tuple[str, ...]
    page_start: int | None
    page_end: int | None
    source_locations: tuple[dict[str, object], ...]


@dataclass(frozen=True)
class _ChildDraft:
    chunk_id: str
    source_ids: list[str]
    content: str
    retrieval_text: str
    content_token_count: int
    token_count: int
    content_hash: str
    pages: tuple[int | None, int | None]
    details: dict[str, object]


class HierarchicalTextChunker:
    """Create parent chunks and linked child chunks from canonical paragraphs."""

    def __init__(self, *, config: ChunkingConfig, token_counter: TokenCounter) -> None:
        self.config = config
        self.token_counter = token_counter

    def chunk(
        self,
        *,
        canonical: CanonicalDocument,
        context: IngestionContext,
        start_ordinal: int = 1,
    ) -> list[ChunkRecord]:
        paragraphs = sorted(canonical.content.paragraphs, key=lambda value: value.order)
        if (
            self.config.references.enabled
            and self.config.references.exclude_reference_sections_from_text_chunks
        ):
            section_labels = {
                section.id: tuple([*section.path, section.title or section.heading or ""])
                for section in canonical.content.sections
            }
            paragraphs = [
                paragraph
                for paragraph in paragraphs
                if not is_reference_section(
                    paragraph.section_path or section_labels.get(paragraph.section_id, ()),
                    self.config.references.section_names,
                )
            ]
        title = canonical.metadata.title
        locations_by_paragraph = paragraph_source_locations(canonical)
        records: list[ChunkRecord] = []
        next_ordinal = start_ordinal

        for section_id, paragraph_group in groupby(
            paragraphs,
            key=lambda value: value.section_id,
        ):
            section_paragraphs = list(paragraph_group)
            if not section_paragraphs:
                continue

            section_path = tuple(section_paragraphs[0].section_path)
            smallest_body_limit = self._smallest_enabled_body_limit(
                title=title,
                section_path=section_path,
            )
            units = self._paragraphs_to_units(
                section_paragraphs,
                max_unit_tokens=smallest_body_limit,
                locations_by_paragraph=locations_by_paragraph,
            )
            if not units:
                continue

            if self.config.text.parent.enabled:
                parent_records, next_ordinal = self._chunk_with_parents(
                    canonical=canonical,
                    context=context,
                    title=title,
                    section_id=section_id,
                    section_path=section_path,
                    units=units,
                    start_ordinal=next_ordinal,
                )
                records.extend(parent_records)
            elif self.config.text.child.enabled:
                child_records, next_ordinal = self._chunk_children_without_parents(
                    canonical=canonical,
                    context=context,
                    title=title,
                    section_id=section_id,
                    section_path=section_path,
                    units=units,
                    start_ordinal=next_ordinal,
                )
                records.extend(child_records)

        return records

    def _chunk_with_parents(
        self,
        *,
        canonical: CanonicalDocument,
        context: IngestionContext,
        title: str | None,
        section_id: str,
        section_path: tuple[str, ...],
        units: list[_TextUnit],
        start_ordinal: int,
    ) -> tuple[list[ChunkRecord], int]:
        parent_window = self.config.text.parent
        parent_body_target, parent_body_max = self._body_limits(
            window=parent_window,
            title=title,
            section_path=section_path,
            source_type="paragraph",
            chunk_role="parent",
        )
        parent_windows = self._pack_units(
            units,
            target_tokens=parent_body_target,
            max_tokens=parent_body_max,
            overlap_tokens=parent_window.overlap_tokens,
        )

        records: list[ChunkRecord] = []
        next_ordinal = start_ordinal

        for parent_units in parent_windows:
            parent_content = self._join_units(parent_units)
            parent_retrieval_text = self._build_retrieval_text(
                title=title,
                section_path=section_path,
                source_type="paragraph",
                chunk_role="parent",
                content=parent_content,
            )
            parent_content_hash = sha256_text(parent_retrieval_text)
            parent_source_ids = self._source_ids(parent_units)
            parent_chunk_id = make_chunk_id(
                user_id=context.user_id,
                document_id=context.document_id,
                source_type="paragraph",
                chunk_role="parent",
                source_ids=parent_source_ids,
                section_id=section_id,
                parent_chunk_id=None,
                content_hash=parent_content_hash,
                chunker_version=self.config.chunker_version,
            )

            child_drafts: list[_ChildDraft] = []
            if self.config.text.child.enabled:
                child_drafts = self._make_child_drafts(
                    context=context,
                    title=title,
                    section_id=section_id,
                    section_path=section_path,
                    parent_chunk_id=parent_chunk_id,
                    units=parent_units,
                )

            parent_page_start, parent_page_end = page_range(
                page for unit in parent_units for page in (unit.page_start, unit.page_end)
            )
            parent_token_count = self.token_counter.count(parent_retrieval_text)
            parent_record = ChunkRecord(
                user_id=context.user_id,
                document_id=context.document_id,
                source_document_id=canonical.document_id,
                chunk_id=parent_chunk_id,
                chunk_ordinal=next_ordinal,
                chunk_role="parent",
                source_type="paragraph",
                parent_chunk_id=None,
                child_chunk_ids=[draft.chunk_id for draft in child_drafts],
                retrieval_enabled=self.config.text.parent_retrieval_enabled,
                source_ids=parent_source_ids,
                title=title,
                section_id=section_id,
                section_path=path_text(section_path),
                section_path_parts=list(section_path),
                page_start=parent_page_start,
                page_end=parent_page_end,
                details=self._details_for_units(parent_units),
                text=parent_content,
                content=parent_content,
                retrieval_text=parent_retrieval_text,
                content_token_count=self.token_counter.count(parent_content),
                token_count=parent_token_count,
                configured_max_tokens=parent_window.max_tokens,
                oversized=False,
                warnings=[],
                content_hash=parent_content_hash,
                chunker_version=self.config.chunker_version,
                tokenizer_name=self.token_counter.name,
                metadata={
                    "paragraph_count": len(parent_source_ids),
                    "hierarchy": "parent",
                },
            )
            records.append(parent_record)
            next_ordinal += 1

            for draft in child_drafts:
                records.append(
                    ChunkRecord(
                        user_id=context.user_id,
                        document_id=context.document_id,
                        source_document_id=canonical.document_id,
                        chunk_id=draft.chunk_id,
                        chunk_ordinal=next_ordinal,
                        chunk_role="child",
                        source_type="paragraph",
                        parent_chunk_id=parent_chunk_id,
                        child_chunk_ids=[],
                        retrieval_enabled=self.config.text.child_retrieval_enabled,
                        source_ids=draft.source_ids,
                        title=title,
                        section_id=section_id,
                        section_path=path_text(section_path),
                        section_path_parts=list(section_path),
                        page_start=draft.pages[0],
                        page_end=draft.pages[1],
                        details=draft.details,
                        text=draft.content,
                        content=draft.content,
                        retrieval_text=draft.retrieval_text,
                        content_token_count=draft.content_token_count,
                        token_count=draft.token_count,
                        configured_max_tokens=self.config.text.child.max_tokens,
                        oversized=False,
                        warnings=[],
                        content_hash=draft.content_hash,
                        chunker_version=self.config.chunker_version,
                        tokenizer_name=self.token_counter.name,
                        metadata={
                            "paragraph_count": len(draft.source_ids),
                            "hierarchy": "child",
                        },
                    )
                )
                next_ordinal += 1

        return records, next_ordinal

    def _chunk_children_without_parents(
        self,
        *,
        canonical: CanonicalDocument,
        context: IngestionContext,
        title: str | None,
        section_id: str,
        section_path: tuple[str, ...],
        units: list[_TextUnit],
        start_ordinal: int,
    ) -> tuple[list[ChunkRecord], int]:
        child_window = self.config.text.child
        body_target, body_max = self._body_limits(
            window=child_window,
            title=title,
            section_path=section_path,
            source_type="paragraph",
            chunk_role="child",
        )
        windows = self._pack_units(
            units,
            target_tokens=body_target,
            max_tokens=body_max,
            overlap_tokens=child_window.overlap_tokens,
        )
        records: list[ChunkRecord] = []
        next_ordinal = start_ordinal

        for window in windows:
            content = self._join_units(window)
            retrieval_text = self._build_retrieval_text(
                title=title,
                section_path=section_path,
                source_type="paragraph",
                chunk_role="child",
                content=content,
            )
            content_hash = sha256_text(retrieval_text)
            source_ids = self._source_ids(window)
            chunk_id = make_chunk_id(
                user_id=context.user_id,
                document_id=context.document_id,
                source_type="paragraph",
                chunk_role="child",
                source_ids=source_ids,
                section_id=section_id,
                parent_chunk_id=None,
                content_hash=content_hash,
                chunker_version=self.config.chunker_version,
            )
            page_start, page_end = page_range(
                page for unit in window for page in (unit.page_start, unit.page_end)
            )
            records.append(
                ChunkRecord(
                    user_id=context.user_id,
                    document_id=context.document_id,
                    source_document_id=canonical.document_id,
                    chunk_id=chunk_id,
                    chunk_ordinal=next_ordinal,
                    chunk_role="child",
                    source_type="paragraph",
                    parent_chunk_id=None,
                    child_chunk_ids=[],
                    retrieval_enabled=self.config.text.child_retrieval_enabled,
                    source_ids=source_ids,
                    title=title,
                    section_id=section_id,
                    section_path=path_text(section_path),
                    section_path_parts=list(section_path),
                    page_start=page_start,
                    page_end=page_end,
                    details=self._details_for_units(window),
                    text=content,
                    content=content,
                    retrieval_text=retrieval_text,
                    content_token_count=self.token_counter.count(content),
                    token_count=self.token_counter.count(retrieval_text),
                    configured_max_tokens=child_window.max_tokens,
                    oversized=False,
                    warnings=[],
                    content_hash=content_hash,
                    chunker_version=self.config.chunker_version,
                    tokenizer_name=self.token_counter.name,
                    metadata={"paragraph_count": len(source_ids), "hierarchy": "child"},
                )
            )
            next_ordinal += 1

        return records, next_ordinal

    def _make_child_drafts(
        self,
        *,
        context: IngestionContext,
        title: str | None,
        section_id: str,
        section_path: tuple[str, ...],
        parent_chunk_id: str,
        units: list[_TextUnit],
    ) -> list[_ChildDraft]:
        child_window = self.config.text.child
        body_target, body_max = self._body_limits(
            window=child_window,
            title=title,
            section_path=section_path,
            source_type="paragraph",
            chunk_role="child",
        )
        windows = self._pack_units(
            units,
            target_tokens=body_target,
            max_tokens=body_max,
            overlap_tokens=child_window.overlap_tokens,
        )
        drafts: list[_ChildDraft] = []
        for window in windows:
            content = self._join_units(window)
            retrieval_text = self._build_retrieval_text(
                title=title,
                section_path=section_path,
                source_type="paragraph",
                chunk_role="child",
                content=content,
            )
            content_hash = sha256_text(retrieval_text)
            source_ids = self._source_ids(window)
            chunk_id = make_chunk_id(
                user_id=context.user_id,
                document_id=context.document_id,
                source_type="paragraph",
                chunk_role="child",
                source_ids=source_ids,
                section_id=section_id,
                parent_chunk_id=parent_chunk_id,
                content_hash=content_hash,
                chunker_version=self.config.chunker_version,
            )
            drafts.append(
                _ChildDraft(
                    chunk_id=chunk_id,
                    source_ids=source_ids,
                    content=content,
                    retrieval_text=retrieval_text,
                    content_token_count=self.token_counter.count(content),
                    token_count=self.token_counter.count(retrieval_text),
                    content_hash=content_hash,
                    pages=page_range(
                        page for unit in window for page in (unit.page_start, unit.page_end)
                    ),
                    details=self._details_for_units(window),
                )
            )
        return drafts

    def _smallest_enabled_body_limit(
        self,
        *,
        title: str | None,
        section_path: tuple[str, ...],
    ) -> int:
        limits: list[int] = []
        if self.config.text.parent.enabled:
            _, parent_max = self._body_limits(
                window=self.config.text.parent,
                title=title,
                section_path=section_path,
                source_type="paragraph",
                chunk_role="parent",
            )
            limits.append(parent_max)
        if self.config.text.child.enabled:
            _, child_max = self._body_limits(
                window=self.config.text.child,
                title=title,
                section_path=section_path,
                source_type="paragraph",
                chunk_role="child",
            )
            limits.append(child_max)
        if not limits:
            raise ValueError("No enabled text chunk window")
        return min(limits)

    def _body_limits(
        self,
        *,
        window: WindowConfig,
        title: str | None,
        section_path: tuple[str, ...],
        source_type: str,
        chunk_role: str,
    ) -> tuple[int, int]:
        empty_retrieval_text = self._build_retrieval_text(
            title=title,
            section_path=section_path,
            source_type=source_type,
            chunk_role=chunk_role,
            content="",
        )
        overhead_tokens = self.token_counter.count(empty_retrieval_text)
        body_max = window.max_tokens - overhead_tokens
        if body_max < 1:
            raise ValueError(
                f"The {chunk_role} retrieval metadata uses {overhead_tokens} tokens, "
                f"but max_tokens={window.max_tokens}. Increase max_tokens or shorten the title "
                "or section path."
            )
        return max(1, window.target_tokens - overhead_tokens), body_max

    def _paragraphs_to_units(
        self,
        paragraphs: list[CanonicalParagraph],
        *,
        max_unit_tokens: int,
        locations_by_paragraph: dict[str, tuple[dict[str, object], ...]],
    ) -> list[_TextUnit]:
        units: list[_TextUnit] = []
        for paragraph in paragraphs:
            for sentence in self._split_sentences(paragraph.text):
                for piece in self.token_counter.split(sentence, max_unit_tokens):
                    cleaned = piece.strip()
                    if not cleaned:
                        continue
                    units.append(
                        _TextUnit(
                            text=cleaned,
                            paragraph_id=paragraph.id,
                            section_id=paragraph.section_id,
                            section_path=tuple(paragraph.section_path),
                            page_start=paragraph.page_start,
                            page_end=paragraph.page_end,
                            source_locations=locations_by_paragraph.get(paragraph.id, ()),
                        )
                    )
        return units

    def _pack_units(
        self,
        units: list[_TextUnit],
        *,
        target_tokens: int,
        max_tokens: int,
        overlap_tokens: int,
    ) -> list[list[_TextUnit]]:
        windows: list[list[_TextUnit]] = []
        start = 0

        while start < len(units):
            end = start
            selected: list[_TextUnit] = []

            while end < len(units):
                candidate = [*selected, units[end]]
                candidate_tokens = self.token_counter.count(self._join_units(candidate))
                if candidate_tokens > max_tokens and selected:
                    break
                if candidate_tokens > max_tokens:
                    raise RuntimeError(
                        f"A text unit has {candidate_tokens} tokens, above body max {max_tokens}."
                    )
                selected = candidate
                end += 1
                if candidate_tokens >= target_tokens:
                    break

            if not selected:
                break

            windows.append(selected)
            if end >= len(units):
                break

            next_start = end
            if overlap_tokens > 0:
                overlap_start = end
                while overlap_start > start:
                    candidate = units[overlap_start - 1 : end]
                    candidate_tokens = self.token_counter.count(self._join_units(candidate))
                    if candidate_tokens > overlap_tokens:
                        break
                    overlap_start -= 1
                if start < overlap_start < end:
                    next_start = overlap_start

            if next_start <= start:
                raise RuntimeError("Chunk overlap did not advance; check overlap configuration")
            start = next_start

        return windows

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        cleaned = " ".join(text.split())
        if not cleaned:
            return []
        sentences = [item.strip() for item in _SENTENCE_BOUNDARY.split(cleaned) if item.strip()]
        return sentences or [cleaned]

    @staticmethod
    def _source_ids(units: list[_TextUnit]) -> list[str]:
        return list(dict.fromkeys(unit.paragraph_id for unit in units))

    @staticmethod
    def _details_for_units(units: list[_TextUnit]) -> dict[str, object]:
        return details_for_source_locations(
            [location for unit in units for location in unit.source_locations]
        )

    @staticmethod
    def _join_units(units: list[_TextUnit]) -> str:
        parts: list[str] = []
        previous_paragraph_id: str | None = None
        for unit in units:
            separator = "\n\n" if previous_paragraph_id not in (None, unit.paragraph_id) else " "
            if not parts:
                separator = ""
            parts.append(f"{separator}{unit.text}")
            previous_paragraph_id = unit.paragraph_id
        return "".join(parts).strip()

    @staticmethod
    def _build_retrieval_text(
        *,
        title: str | None,
        section_path: tuple[str, ...],
        source_type: str,
        chunk_role: str,
        content: str,
    ) -> str:
        parts: list[str] = []
        if title and title.strip():
            parts.append(f"Document: {title.strip()}")
        if section_path:
            parts.append(f"Section: {' > '.join(section_path)}")
        parts.append(f"Source type: {source_type}")
        parts.append(f"Chunk role: {chunk_role}")
        return "\n".join(parts) + f"\n\nContent:\n{content.strip()}"
