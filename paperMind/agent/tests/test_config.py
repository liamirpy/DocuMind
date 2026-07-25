from app.config import Settings


def test_settings_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.tools_base_url.endswith(":8090")
    assert settings.llm_enabled is False
    assert settings.formula_crop_scale == 3.0
    assert settings.path_api_enabled is True
    assert settings.allowed_input_directories == ""
    assert settings.allowed_output_directories == ""
