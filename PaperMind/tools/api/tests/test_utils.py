from app.utils import asset_url, safe_filename


def test_safe_filename_removes_path_components():
    assert safe_filename("../../paper.pdf") == "paper.pdf"


def test_asset_url_joins_prefix_and_relative_path():
    assert asset_url("/assets/", "/abc/figure.png") == "/assets/abc/figure.png"
