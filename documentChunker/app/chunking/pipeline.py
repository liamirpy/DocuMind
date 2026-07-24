from __future__ import annotations

from collections import Counter

from app.chunking.config import ChunkingConfig
from app.chunking.elements import SpecialElementChunker
from app.chunking.models import ChunkCounts, ChunkingOutput, IngestionContext
from app.chunking.references import ReferenceProcessor
from app.chunking.text import HierarchicalTextChunker
from app.chunking.token_counter import RegexTokenCounter, TokenCounter
from app.input_package.reader import InputPackage


class DirectoryChunkingPipeline:
    """Coordinate directory assets, hierarchical text, elements, and references."""

    def __init__(
        self,
        *,
        config: ChunkingConfig | None = None,
        token_counter: TokenCounter | None = None,
    ) -> None:
        self.config = config or ChunkingConfig()
        self.token_counter = token_counter or RegexTokenCounter()
        self.text_chunker = HierarchicalTextChunker(
            config=self.config,
            token_counter=self.token_counter,
        )
        self.element_chunker = SpecialElementChunker(
            config=self.config,
            token_counter=self.token_counter,
        )
        self.reference_processor = ReferenceProcessor(config=self.config)

    def run(
        self,
        *,
        package: InputPackage,
        context: IngestionContext,
    ) -> ChunkingOutput:
        canonical = package.canonical
        text_chunks = self.text_chunker.chunk(
            canonical=canonical,
            context=context,
            start_ordinal=1,
        )
        element_chunks = self.element_chunker.chunk(
            package=package,
            context=context,
            start_ordinal=len(text_chunks) + 1,
        )
        chunks = [*text_chunks, *element_chunks]
        references = self.reference_processor.process(package=package, context=context)

        roles = Counter(chunk.chunk_role for chunk in chunks)
        sources = Counter(chunk.source_type for chunk in chunks)
        counts = ChunkCounts(
            total=len(chunks),
            parent=roles["parent"],
            child=roles["child"],
            standalone=roles["standalone"],
            paragraph=sources["paragraph"],
            table=sources["table"],
            figure=sources["figure"],
            formula=sources["formula"],
            references=len(references),
            oversized=sum(1 for chunk in chunks if chunk.oversized),
        )

        return ChunkingOutput(
            user_id=context.user_id,
            document_id=context.document_id,
            source_document_id=canonical.document_id,
            canonical_schema_version=canonical.schema_version,
            input_directory=str(package.root),
            chunker_version=self.config.chunker_version,
            tokenizer_name=self.token_counter.name,
            config=self.config.model_dump(mode="json"),
            counts=counts,
            chunks=chunks,
            references=references,
        )


# Backward-friendly alias for users of the previous package name.
CanonicalChunkingPipeline = DirectoryChunkingPipeline
