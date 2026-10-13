"""Feature tests for configuration helpers."""

from backend.config import Settings, model_label


def test_model_label_known_slug():
    assert model_label("~deepseek/deepseek-flash-latest") == "DeepSeek Flash"


def test_model_label_falls_back_to_slug_tail():
    assert model_label("~acme/unknown-latest") == "unknown-latest"


def test_model_options_accept_comma_separated_string():
    settings = Settings(model_options="~a/one, ~b/two")
    assert settings.model_options == ["~a/one", "~b/two"]
