# Input contract

The indexer reads an **already-generated PDF output directory**. It never modifies that directory.

Expected layout:

```text
pdf-output/
├── canonical_document.json
├── figures/
│   ├── figure_001.caption.txt
│   ├── figure_001.description.json
│   └── figure_001.png
├── tables/
│   ├── table_001.caption.txt
│   ├── table_001.description.json
│   ├── table_001.md
│   └── table_001.csv
├── formulas/
│   ├── formula_001.description.json
│   ├── formula_001.tex
│   └── formula_001.txt
├── latex/
└── source/
```

The exact folders may vary. Asset paths inside `canonical_document.json` are used first; the
standard paths above are also inferred as a fallback when
`package_assets.infer_standard_sidecar_paths` is enabled.

## Canonical root

Required root fields:

```json
{
  "schema_version": "1.x",
  "document_id": "canonical-document-id",
  "content": {
    "sections": [],
    "paragraphs": [],
    "figures": [],
    "tables": [],
    "formulas": [],
    "references": []
  }
}
```

## Paragraph fields

Fields used for hierarchical text chunking:

```json
{
  "id": "para_00001",
  "section_id": "sec_001",
  "section_path": ["Methods", "VR System"],
  "order": 1,
  "text": "Paragraph text",
  "page_start": 1,
  "page_end": 1
}
```

Paragraphs under a configured reference-section name are excluded from parent/child chunks.
The structured `content.references` entries are emitted separately.

## Figure, table, and formula descriptions

A sidecar description JSON can contain:

```json
{
  "text": "Detailed LLM description",
  "summary": "Short summary",
  "element_type": "figure",
  "source": "ollama_vision",
  "provider": "ollama",
  "model": "qwen2.5vl:3b",
  "confidence": 0.95,
  "warnings": [],
  "details": {
    "visible_text": ["Registration", "Pre-test"],
    "key_observations": ["The process has four stages"]
  }
}
```

The indexer preserves `text`, `summary`, and `details` as explicit output fields and includes
all semantic detail values in `retrieval_text`. Provider/model/confidence metadata is kept in
`metadata.description_provenance`, not mixed into retrieval text.

## Asset precedence

With the default configuration:

```json
{
  "package_assets": {
    "prefer_sidecar_files": true,
    "infer_standard_sidecar_paths": true
  }
}
```

non-empty sidecar files take precedence over duplicate canonical fields. Canonical values are
used as fallback when a sidecar is absent or empty.
