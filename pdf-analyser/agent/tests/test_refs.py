from app.canonical.refs import referenced_texts, resolve_ref


def test_resolve_ref_and_caption_text() -> None:
    document = {
        "texts": [
            {"text": "Table 1. Results"},
            {"orig": "Figure caption"},
        ]
    }
    assert resolve_ref(document, {"$ref": "#/texts/0"}) == {"text": "Table 1. Results"}
    assert referenced_texts(
        document,
        [{"$ref": "#/texts/0"}, {"cref": "#/texts/1"}],
    ) == ["Table 1. Results", "Figure caption"]
