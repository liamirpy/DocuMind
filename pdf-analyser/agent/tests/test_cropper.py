from pathlib import Path

import pymupdf

from app.canonical.cropper import crop_region


def test_crop_region_from_bottom_left_coordinates(tmp_path: Path) -> None:
    pdf_path = tmp_path / "sample.pdf"
    document = pymupdf.open()
    page = document.new_page(width=300, height=400)
    page.insert_text((50, 100), "E = mc^2", fontsize=20)
    document.save(pdf_path)
    document.close()

    output = tmp_path / "formula.png"
    result = crop_region(
        pdf_path,
        provenance=[
            {
                "page_no": 1,
                "bbox": {
                    "l": 40,
                    "t": 330,
                    "r": 180,
                    "b": 270,
                    "coord_origin": "BOTTOMLEFT",
                },
            }
        ],
        destination=output,
        scale=2.0,
        padding_points=2.0,
    )
    assert result["status"] == "saved"
    assert output.is_file()
    assert result["width"] > 0
    assert result["height"] > 0
