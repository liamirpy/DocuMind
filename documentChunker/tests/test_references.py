from __future__ import annotations

from app.chunking.config import ChunkingConfig, ReferenceConfig
from app.chunking.models import IngestionContext
from app.chunking.pipeline import DirectoryChunkingPipeline
from app.input_package.reader import load_input_package


def test_references_are_separate_structured_records(sample_directory) -> None:
    package = load_input_package(sample_directory)
    output = DirectoryChunkingPipeline().run(
        package=package,
        context=IngestionContext(user_id="user_123", document_id="doc_456"),
    )

    assert output.counts.references == 2
    assert len(output.references) == 2
    assert all(reference.retrieval_enabled is False for reference in output.references)
    assert all(reference.retrieval_text is None for reference in output.references)

    first = output.references[0]
    assert first.title == "Attention Is All You Need"
    assert first.authors == ["Ashish Vaswani", "Noam Shazeer"]
    assert first.year == "2017"
    assert first.raw_text is not None and "Vaswani" in first.raw_text


def test_reference_retrieval_text_can_be_enabled(sample_directory) -> None:
    package = load_input_package(sample_directory)
    config = ChunkingConfig(
        references=ReferenceConfig(
            retrieval_enabled=True,
            generate_retrieval_text=True,
        )
    )
    output = DirectoryChunkingPipeline(config=config).run(
        package=package,
        context=IngestionContext(user_id="user_123", document_id="doc_456"),
    )

    first = output.references[0]
    assert first.retrieval_enabled is True
    assert first.retrieval_text is not None
    assert "Title: Attention Is All You Need" in first.retrieval_text
