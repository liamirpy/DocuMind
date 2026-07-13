from app.canonical.quality import build_quality_report
from app.config import Settings


def test_quality_report_flags_empty_table() -> None:
    canonical = {
        "metadata": {"title": "A paper"},
        "content": {
            "text_blocks": [{"text": "hello"}],
            "tables": [{"id": "table_001", "quality": {"status": "failed"}}],
            "formulas": [],
            "figures": [],
        },
    }
    extraction = {
        "docling": {"status": "completed", "parsed": {"counts": {"tables": 1}}},
        "grobid": {"status": "completed", "parsed": {"counts": {"tables": 1}}},
    }
    report = build_quality_report(canonical, extraction=extraction, settings=Settings())
    assert report["status"] in {"green", "yellow"}
    assert any(issue["type"] == "table_failed" for issue in report["issues"])
