from app.parsers.docling import parse_docling_document


def test_docling_parser_flags_empty_table_structure():
    document = {
        "texts": [
            {"self_ref": "#/texts/0", "label": "caption", "text": "Table 1. Results"},
            {
                "self_ref": "#/texts/1",
                "label": "formula",
                "orig": "E = mc2",
                "text": "E = mc^2",
                "prov": [{"page_no": 1}],
            },
        ],
        "tables": [
            {
                "self_ref": "#/tables/0",
                "captions": [{"$ref": "#/texts/0"}],
                "prov": [{"page_no": 1}],
                "data": {"table_cells": [], "num_rows": 0, "num_cols": 0},
            }
        ],
        "pictures": [],
    }

    parsed = parse_docling_document(document)

    assert parsed["counts"]["formulas"] == 1
    assert parsed["counts"]["tables_empty_structure"] == 1
    assert parsed["tables"][0]["captions"] == ["Table 1. Results"]
    assert parsed["tables"][0]["structure_status"] == "empty_structure"
    assert parsed["quality_flags"][0]["type"] == "table_empty_structure"


def test_docling_parser_accepts_structured_table():
    document = {
        "texts": [],
        "tables": [
            {
                "self_ref": "#/tables/0",
                "data": {
                    "table_cells": [{"text": "A"}, {"text": "1"}],
                    "num_rows": 1,
                    "num_cols": 2,
                },
            }
        ],
        "pictures": [],
    }

    parsed = parse_docling_document(document)

    assert parsed["counts"]["tables_structured"] == 1
    assert parsed["counts"]["tables_empty_structure"] == 0
    assert parsed["tables"][0]["structure_status"] == "structured"
