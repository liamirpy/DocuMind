from app.canonical.matching import best_match, text_similarity


def test_text_similarity_and_best_match() -> None:
    assert text_similarity("Table 2: Model accuracy", "Table 2 Model Accuracy") > 0.95
    source = {
        "captions": ["Performance on the test dataset"],
        "provenance": [{"page_no": 4, "bbox": {"l": 1, "t": 10, "r": 20, "b": 1}}],
    }
    candidates = [
        {"caption": "Unrelated table", "coords": "2,1,1,10,10"},
        {"caption": "Performance on test dataset", "coords": "4,1,1,10,10"},
    ]
    index, score, parts = best_match(
        source,
        candidates,
        source_text=lambda item: " ".join(item.get("captions") or []),
        candidate_text=lambda item: item.get("caption"),
        source_index=1,
    )
    assert index == 1
    assert score > 0.7
    assert parts["page_score"] == 1.0
