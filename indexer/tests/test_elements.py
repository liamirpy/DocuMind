from __future__ import annotations

import json
import shutil

from app.chunking.config import ChunkingConfig, SpecialElementConfig
from app.chunking.models import IngestionContext
from app.chunking.pipeline import DirectoryChunkingPipeline
from app.input_package.reader import load_input_package


def run_pipeline(sample_directory, config: ChunkingConfig | None = None):
    package = load_input_package(sample_directory)
    return DirectoryChunkingPipeline(config=config).run(
        package=package,
        context=IngestionContext(user_id="user_123", document_id="doc_456"),
    )


def test_each_special_element_becomes_one_rich_standalone_chunk(sample_directory) -> None:
    output = run_pipeline(sample_directory)

    special = [chunk for chunk in output.chunks if chunk.chunk_role == "standalone"]
    assert len([chunk for chunk in special if chunk.source_type == "figure"]) == 1
    assert len([chunk for chunk in special if chunk.source_type == "table"]) == 1
    assert len([chunk for chunk in special if chunk.source_type == "formula"]) == 1

    figure = next(chunk for chunk in special if chunk.source_type == "figure")
    assert figure.caption == "VR training workflow"
    assert figure.text == "Registration → Pre-test → VR training → Post-test"
    assert figure.summary == "The figure shows the four stages of the VR training process."
    assert figure.section_path == "Methods > VR System"
    assert "Section: Methods > VR System" in figure.retrieval_text
    assert "Caption: VR training workflow" in figure.retrieval_text
    assert "Summary: The figure shows the four stages" in figure.retrieval_text
    assert "Visible text: Registration; Pre-test; VR training; Post-test" in figure.retrieval_text
    assert figure.metadata["caption_source"] == "figures/figure_001.caption.txt"
    assert figure.metadata["description_source"] == "figures/figure_001.description.json"

    table = next(chunk for chunk in special if chunk.source_type == "table")
    assert table.caption == "Lesion distribution by category"
    assert table.text is not None and table.text.startswith("This table compares")
    assert table.summary is not None
    assert table.table_text is not None and "One Lesion" in table.table_text
    assert "Visible headers: One Lesion; Multiple Lesions" in table.retrieval_text
    assert "Table data:" in table.retrieval_text

    formula = next(chunk for chunk in special if chunk.source_type == "formula")
    assert formula.text is not None and formula.text.startswith("The formula is")
    assert formula.summary is not None and formula.summary.startswith("The formula calculates")
    assert formula.formula_latex is not None and "sum" in formula.formula_latex
    assert formula.formula_text is not None
    assert "Visible structure:" in formula.retrieval_text
    assert (
        "Symbols: Y (output variable); X (input function); F (filter function)"
        in formula.retrieval_text
    )
    assert "Formula LaTeX:" in formula.retrieval_text


def test_empty_description_still_creates_element_chunk(sample_directory, tmp_path) -> None:
    copied = tmp_path / "pdf-output"
    shutil.copytree(sample_directory, copied)
    (copied / "figures" / "figure_001.description.json").write_text("{}\n", encoding="utf-8")

    canonical_path = copied / "canonical_document.json"
    data = json.loads(canonical_path.read_text(encoding="utf-8"))
    data["content"]["figures"][0]["description"] = None
    canonical_path.write_text(json.dumps(data), encoding="utf-8")

    output = run_pipeline(copied)
    figure = next(chunk for chunk in output.chunks if chunk.source_type == "figure")

    assert figure.caption == "VR training workflow"
    assert figure.text is None
    assert figure.summary is None
    assert figure.retrieval_text.startswith("Document: A Small Retrieval Paper")
    assert "Figure: Figure 1" in figure.retrieval_text


def test_oversized_special_element_is_kept_as_one_chunk(sample_directory, tmp_path) -> None:
    copied = tmp_path / "pdf-output"
    shutil.copytree(sample_directory, copied)
    markdown = "| A | B |\n| --- | --- |\n" + "\n".join(
        f"| row-{index} | a very long value for retrieval |" for index in range(100)
    )
    (copied / "tables" / "table_001.md").write_text(markdown, encoding="utf-8")

    config = ChunkingConfig(
        special_elements=SpecialElementConfig(
            max_tokens=80,
            oversize_policy="allow",
        )
    )
    output = run_pipeline(copied, config=config)

    table_chunks = [chunk for chunk in output.chunks if chunk.source_type == "table"]
    assert len(table_chunks) == 1
    assert table_chunks[0].oversized is True
    assert table_chunks[0].token_count > 80
    assert table_chunks[0].warnings
