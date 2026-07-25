from __future__ import annotations

import json
import shutil

from app.chunking.config import (
    ChunkingConfig,
    HierarchicalTextConfig,
    SpecialElementConfig,
    WindowConfig,
)
from app.chunking.models import IngestionContext
from app.chunking.pipeline import DirectoryChunkingPipeline
from app.input_package.reader import load_input_package


def small_config() -> ChunkingConfig:
    return ChunkingConfig(
        text=HierarchicalTextConfig(
            parent=WindowConfig(
                target_tokens=105,
                max_tokens=130,
                overlap_tokens=0,
            ),
            child=WindowConfig(
                target_tokens=50,
                max_tokens=72,
                overlap_tokens=15,
            ),
        ),
        special_elements=SpecialElementConfig(enabled=False),
    )


def run_pipeline(sample_directory):
    package = load_input_package(sample_directory)
    output = DirectoryChunkingPipeline(config=small_config()).run(
        package=package,
        context=IngestionContext(user_id="user_123", document_id="doc_456"),
    )
    return package, output


def test_parent_child_links_are_bidirectional(sample_directory) -> None:
    _, output = run_pipeline(sample_directory)

    parents = [chunk for chunk in output.chunks if chunk.chunk_role == "parent"]
    children = [chunk for chunk in output.chunks if chunk.chunk_role == "child"]
    child_by_id = {child.chunk_id: child for child in children}

    assert parents
    assert children
    for parent in parents:
        assert parent.child_chunk_ids
        assert parent.retrieval_enabled is False
        for child_id in parent.child_chunk_ids:
            assert child_by_id[child_id].parent_chunk_id == parent.chunk_id
            assert child_by_id[child_id].retrieval_enabled is True


def test_text_chunks_respect_limits_sections_and_reference_exclusion(sample_directory) -> None:
    package, output = run_pipeline(sample_directory)

    paragraph_to_section = {
        paragraph.id: paragraph.section_id for paragraph in package.canonical.content.paragraphs
    }
    paragraph_chunks = [chunk for chunk in output.chunks if chunk.source_type == "paragraph"]
    assert paragraph_chunks
    assert all("para_00005" not in chunk.source_ids for chunk in paragraph_chunks)
    assert all(chunk.section_path != "References" for chunk in paragraph_chunks)

    for chunk in paragraph_chunks:
        assert chunk.token_count <= chunk.configured_max_tokens
        source_sections = {paragraph_to_section[source_id] for source_id in chunk.source_ids}
        assert source_sections == {chunk.section_id}
        assert chunk.text == chunk.content
        assert "Section:" in chunk.retrieval_text


def test_child_overlap_reuses_complete_sentence(sample_directory) -> None:
    _, output = run_pipeline(sample_directory)

    introduction_children = [
        chunk
        for chunk in output.chunks
        if chunk.chunk_role == "child" and chunk.section_id == "sec_001"
    ]
    assert len(introduction_children) >= 2

    first_sentences = {
        sentence.strip()
        for sentence in introduction_children[0].content.split(".")
        if sentence.strip()
    }
    next_start = introduction_children[1].content.split(".", maxsplit=1)[0].strip()
    assert next_start in first_sentences


def test_chunk_ids_are_deterministic(sample_directory) -> None:
    package = load_input_package(sample_directory)
    pipeline = DirectoryChunkingPipeline(config=small_config())
    context = IngestionContext(user_id="user_123", document_id="doc_456")

    first = pipeline.run(package=package, context=context)
    second = pipeline.run(package=package, context=context)

    assert [chunk.chunk_id for chunk in first.chunks] == [chunk.chunk_id for chunk in second.chunks]


def test_text_block_bounding_boxes_are_preserved_in_chunk_details(
    sample_directory,
    tmp_path,
) -> None:
    copied = tmp_path / "pdf-output"
    shutil.copytree(sample_directory, copied)

    canonical_path = copied / "canonical_document.json"
    data = json.loads(canonical_path.read_text(encoding="utf-8"))
    paragraph = data["content"]["paragraphs"][0]
    data["content"]["text_blocks"] = [
        {
            "id": "#/texts/3",
            "index": 4,
            "label": "text",
            "text": paragraph["text"],
            "paragraph_id": paragraph["id"],
            "provenance": [
                {
                    "page_no": 1,
                    "bbox": {
                        "l": 105.693,
                        "t": 757.012488,
                        "r": 136.873758,
                        "b": 750.561538,
                        "coord_origin": "BOTTOMLEFT",
                    },
                    "charspan": [0, 8],
                }
            ],
        }
    ]
    canonical_path.write_text(json.dumps(data), encoding="utf-8")

    _, output = run_pipeline(copied)
    paragraph_chunks = [chunk for chunk in output.chunks if paragraph["id"] in chunk.source_ids]

    assert paragraph_chunks
    for chunk in paragraph_chunks:
        locations = chunk.details["source_locations"]
        assert locations[0]["source_block_id"] == "#/texts/3"
        assert locations[0]["page"] == 1
        assert locations[0]["bbox"]["coord_origin"] == "BOTTOMLEFT"
        assert locations[0]["charspan"] == [0, 8]
