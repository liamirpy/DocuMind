import csv
import html
import io
from pathlib import Path
from typing import Any

from app.utils import atomic_write_text

_LATEX_ESCAPE = {
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
    "\\": r"\textbackslash{}",
}


def latex_escape(value: object) -> str:
    text = "" if value is None else str(value)
    return "".join(_LATEX_ESCAPE.get(char, char) for char in text)


def table_matrix(table_item: dict[str, Any]) -> tuple[list[str], list[list[str]], list[str]]:
    data = table_item.get("data") or {}
    cells = data.get("table_cells") or []
    row_count = int(data.get("num_rows") or 0)
    col_count = int(data.get("num_cols") or 0)
    warnings: list[str] = []

    if row_count <= 0 or col_count <= 0 or not cells:
        return [], [], ["Docling returned an empty table structure."]

    grid = [["" for _ in range(col_count)] for _ in range(row_count)]
    header_rows: set[int] = set()
    for cell in cells:
        try:
            row_start = int(cell.get("start_row_offset_idx") or 0)
            row_end = int(cell.get("end_row_offset_idx") or row_start + 1)
            col_start = int(cell.get("start_col_offset_idx") or 0)
            col_end = int(cell.get("end_col_offset_idx") or col_start + 1)
        except (TypeError, ValueError):
            warnings.append("Skipped a cell with invalid row or column offsets.")
            continue
        if row_start >= row_count or col_start >= col_count:
            warnings.append("Skipped an out-of-range table cell.")
            continue
        text = " ".join(str(cell.get("text") or "").split())
        grid[row_start][col_start] = text
        if bool(cell.get("column_header")):
            header_rows.add(row_start)
        # Preserve span information without duplicating text into every cell.
        if row_end - row_start > 1 or col_end - col_start > 1:
            warnings.append(
                f"Cell at row {row_start}, column {col_start} spans multiple cells; "
                "the flat matrix stores text only in its top-left position."
            )

    header_index = min(header_rows) if header_rows else 0
    columns = grid[header_index]
    rows = [row for index, row in enumerate(grid) if index != header_index]
    if not any(columns):
        columns = [f"column_{index + 1}" for index in range(col_count)]
        rows = grid
        warnings.append("No explicit column header was found; generated placeholder names.")
    return columns, rows, list(dict.fromkeys(warnings))


def normalize_llm_table(payload: dict[str, Any]) -> tuple[list[str], list[list[str]], list[str]]:
    columns = [str(value) for value in payload.get("columns") or []]
    rows = [[str(value) for value in row] for row in payload.get("rows") or []]
    warnings = [str(value) for value in payload.get("warnings") or []]
    width = len(columns)
    if width == 0 and rows:
        width = max(len(row) for row in rows)
        columns = [f"column_{index + 1}" for index in range(width)]
        warnings.append(
            "The vision model returned rows without headers; placeholders were generated."
        )
    normalized_rows: list[list[str]] = []
    for row in rows:
        if len(row) < width:
            row = row + [""] * (width - len(row))
        elif len(row) > width:
            warnings.append("A vision-model row had more cells than headers and was truncated.")
            row = row[:width]
        normalized_rows.append(row)
    return columns, normalized_rows, list(dict.fromkeys(warnings))


def table_to_csv(columns: list[str], rows: list[list[str]]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    if columns:
        writer.writerow(columns)
    writer.writerows(rows)
    return buffer.getvalue()


def table_to_markdown(columns: list[str], rows: list[list[str]]) -> str:
    if not columns:
        return ""

    def clean(value: str) -> str:
        return value.replace("|", r"\|").replace("\n", " ")

    lines = [
        "| " + " | ".join(clean(value) for value in columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    lines.extend("| " + " | ".join(clean(value) for value in row) + " |" for row in rows)
    return "\n".join(lines) + "\n"


def table_to_html(columns: list[str], rows: list[list[str]], caption: str | None) -> str:
    parts = ["<table>"]
    if caption:
        parts.append(f"  <caption>{html.escape(caption)}</caption>")
    if columns:
        parts.append("  <thead><tr>")
        parts.extend(f"    <th>{html.escape(value)}</th>" for value in columns)
        parts.append("  </tr></thead>")
    parts.append("  <tbody>")
    for row in rows:
        parts.append("    <tr>")
        parts.extend(f"      <td>{html.escape(value)}</td>" for value in row)
        parts.append("    </tr>")
    parts.extend(["  </tbody>", "</table>"])
    return "\n".join(parts) + "\n"


def table_to_latex(
    columns: list[str],
    rows: list[list[str]],
    *,
    caption: str | None,
    label: str,
) -> str:
    if not columns:
        return "% No structured table data was available.\n"
    alignment = "l" * len(columns)
    lines = [
        r"\begin{table}[htbp]",
        r"\centering",
    ]
    if caption:
        lines.append(rf"\caption{{{latex_escape(caption)}}}")
    lines.extend(
        [
            rf"\label{{{latex_escape(label)}}}",
            rf"\begin{{tabular}}{{{alignment}}}",
            r"\hline",
            " & ".join(latex_escape(value) for value in columns) + r" \\",
            r"\hline",
        ]
    )
    for row in rows:
        lines.append(" & ".join(latex_escape(value) for value in row) + r" \\")
    lines.extend(
        [
            r"\hline",
            r"\end{tabular}",
            r"\end{table}",
            "",
        ]
    )
    return "\n".join(lines)


def write_table_assets(
    directory: Path,
    *,
    stem: str,
    columns: list[str],
    rows: list[list[str]],
    caption: str | None,
    latex_label: str,
) -> dict[str, str]:
    directory.mkdir(parents=True, exist_ok=True)
    paths = {
        "csv": directory / f"{stem}.csv",
        "markdown": directory / f"{stem}.md",
        "html": directory / f"{stem}.html",
        "latex": directory / f"{stem}.tex",
    }
    atomic_write_text(paths["csv"], table_to_csv(columns, rows))
    atomic_write_text(paths["markdown"], table_to_markdown(columns, rows))
    atomic_write_text(paths["html"], table_to_html(columns, rows, caption))
    atomic_write_text(
        paths["latex"],
        table_to_latex(columns, rows, caption=caption, label=latex_label),
    )
    return {key: path.name for key, path in paths.items()}
