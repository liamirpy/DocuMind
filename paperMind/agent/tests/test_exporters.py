from app.canonical.exporters import (
    normalize_llm_table,
    table_matrix,
    table_to_latex,
    table_to_markdown,
)


def test_table_matrix_extracts_headers_and_rows() -> None:
    table = {
        "data": {
            "num_rows": 3,
            "num_cols": 2,
            "table_cells": [
                {
                    "text": "Model",
                    "start_row_offset_idx": 0,
                    "end_row_offset_idx": 1,
                    "start_col_offset_idx": 0,
                    "end_col_offset_idx": 1,
                    "column_header": True,
                },
                {
                    "text": "Accuracy",
                    "start_row_offset_idx": 0,
                    "end_row_offset_idx": 1,
                    "start_col_offset_idx": 1,
                    "end_col_offset_idx": 2,
                    "column_header": True,
                },
                {
                    "text": "A",
                    "start_row_offset_idx": 1,
                    "end_row_offset_idx": 2,
                    "start_col_offset_idx": 0,
                    "end_col_offset_idx": 1,
                },
                {
                    "text": "0.91",
                    "start_row_offset_idx": 1,
                    "end_row_offset_idx": 2,
                    "start_col_offset_idx": 1,
                    "end_col_offset_idx": 2,
                },
                {
                    "text": "B",
                    "start_row_offset_idx": 2,
                    "end_row_offset_idx": 3,
                    "start_col_offset_idx": 0,
                    "end_col_offset_idx": 1,
                },
                {
                    "text": "0.94",
                    "start_row_offset_idx": 2,
                    "end_row_offset_idx": 3,
                    "start_col_offset_idx": 1,
                    "end_col_offset_idx": 2,
                },
            ],
        }
    }
    columns, rows, warnings = table_matrix(table)
    assert columns == ["Model", "Accuracy"]
    assert rows == [["A", "0.91"], ["B", "0.94"]]
    assert warnings == []
    assert "| Model | Accuracy |" in table_to_markdown(columns, rows)
    assert r"\begin{tabular}{ll}" in table_to_latex(
        columns,
        rows,
        caption="Results",
        label="tab:results",
    )


def test_empty_table_and_llm_normalization() -> None:
    assert table_matrix({"data": {"num_rows": 0, "num_cols": 0}})[0] == []
    columns, rows, warnings = normalize_llm_table(
        {"columns": ["A", "B"], "rows": [["1"], ["2", "3", "4"]]}
    )
    assert columns == ["A", "B"]
    assert rows == [["1", ""], ["2", "3"]]
    assert warnings
