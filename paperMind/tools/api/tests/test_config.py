from app.config import Settings


def test_coordinate_list_accepts_comma_separated_environment_value(monkeypatch):
    monkeypatch.setenv("GROBID_TEI_COORDINATES", "figure,table,formula")
    settings = Settings()
    assert settings.grobid_tei_coordinates == ["figure", "table", "formula"]


def test_cuda_index_device_is_accepted(monkeypatch):
    monkeypatch.setenv("DOCLING_ACCELERATOR_DEVICE", "cuda:1")
    settings = Settings()
    assert settings.docling_accelerator_device == "cuda:1"


def test_asset_prefix_is_normalized(monkeypatch):
    monkeypatch.setenv("ASSETS_URL_PREFIX", "assets/")
    settings = Settings()
    assert settings.assets_url_prefix == "/assets"
