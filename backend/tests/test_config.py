"""Feature tests for configuration helpers."""

import json

from backend.config import Settings, SuperSubTier, model_label


def test_model_label_known_slug():
    assert model_label("~deepseek/deepseek-flash-latest") == "DeepSeek Flash"


def test_model_label_falls_back_to_slug_tail():
    assert model_label("~acme/unknown-latest") == "unknown-latest"


def test_model_options_accept_comma_separated_string():
    settings = Settings(model_options="~a/one, ~b/two")
    assert settings.model_options == ["~a/one", "~b/two"]


def test_flash_selects_the_fast_tier():
    """Flash: supervisor Flash @ high, worker Flash @ low (DECISIONS M1)."""
    tier = Settings().tier_for_model("~deepseek/deepseek-flash-latest")
    assert tier == SuperSubTier(
        supervisor_model="~deepseek/deepseek-flash-latest",
        supervisor_effort="high",
        sub_model="~deepseek/deepseek-flash-latest",
        sub_effort="low",
    )


def test_pro_selects_the_pro_tier():
    """Pro: supervisor Pro @ max, worker Flash @ high (DECISIONS M1)."""
    tier = Settings().tier_for_model("~deepseek/deepseek-pro-latest")
    assert tier == SuperSubTier(
        supervisor_model="~deepseek/deepseek-pro-latest",
        supervisor_effort="max",
        sub_model="~deepseek/deepseek-flash-latest",
        sub_effort="high",
    )


def test_unknown_slug_falls_back_to_the_fast_tier():
    tier = Settings().tier_for_model("~acme/unknown-latest")
    assert tier.supervisor_model == "~deepseek/deepseek-flash-latest"
    assert tier.sub_model == "~deepseek/deepseek-flash-latest"


def test_tier_table_loads_from_a_json_env_value(monkeypatch):
    """`SUPER_SUB_TIERS` overrides the table, following the env-only rule (P1)."""
    monkeypatch.setenv(
        "SUPER_SUB_TIERS",
        json.dumps(
            {
                "fast": {
                    "supervisor_model": "a",
                    "supervisor_effort": "high",
                    "sub_model": "b",
                    "sub_effort": "low",
                },
                "pro": {
                    "supervisor_model": "c",
                    "supervisor_effort": "max",
                    "sub_model": "d",
                    "sub_effort": "high",
                },
            }
        ),
    )
    tier = Settings().tier_for_model("~deepseek/deepseek-pro-latest")
    assert tier.supervisor_model == "c"
    assert tier.sub_model == "d"
