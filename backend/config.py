"""Application configuration.

Reads ONLY environment variables — there is deliberately NO `.env` file in
this repo (secrets and tunables are supplied at run time). Field names map to
env vars case-insensitively, so:

    model_reasoning_effort  <- MODEL_REASONING_EFFORT
    model_temperature       <- MODEL_TEMPERATURE
    model_max_tokens        <- MODEL_MAX_TOKENS
    model_default           <- MODEL_DEFAULT
    model_options           <- MODEL_OPTIONS   (comma-separated)
    openrouter_api_key      <- OPENROUTER_API_KEY
"""

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Cosmetic display names for the model selector only. The slugs held in
# `model_options` are the source of truth (DECISIONS M2); these labels are
# UI-only and can be extended freely when `models.options` grows.
#
# NOTE: the `~` prefix is REQUIRED by OpenRouter — DeepSeek's `-latest` aliases
# are served as "prerelease" (prefixed `~`) at the time of writing. DECISIONS.md
# pinned the slugs *without* the `~`; that was corrected against the live
# OpenRouter catalog (see README "Deviations").
_MODEL_LABELS: dict[str, str] = {
    "~deepseek/deepseek-flash-latest": "DeepSeek Flash",
    "~deepseek/deepseek-pro-latest": "DeepSeek Pro",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    # --- Secret (DECISIONS: secrets stay out of config; managed via env) ---
    # Not required at import so that /health + /models still respond without a
    # key. `llm.chat()` fails fast with a clear error when it's missing.
    openrouter_api_key: str = ""

    # OpenRouter base URL (chat completions endpoint is appended in llm.py).
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # --- Model selection (DECISIONS M1-M3) ---
    model_default: str = "~deepseek/deepseek-flash-latest"
    model_options: list[str] = Field(
        default_factory=lambda: [
            "~deepseek/deepseek-flash-latest",
            "~deepseek/deepseek-pro-latest",
        ]
    )

    # --- Generation params (TBD — under research; surfaced so they can be
    # tuned via env without code edits). Unset/empty values are omitted from
    # the request so the provider applies its own default. ---
    model_reasoning_effort: str | None = "medium"  # ratified (DECISIONS M note)
    model_temperature: float | None = None         # TBD
    model_max_tokens: int | None = None            # TBD

    @field_validator("model_options", mode="before")
    @classmethod
    def _split_model_options(cls, value):
        """Allow `MODEL_OPTIONS=a,b,c` (comma-separated) in addition to a list."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


def model_label(slug: str) -> str:
    """Friendly dropdown label for a model slug, falling back to the slug tail."""
    return _MODEL_LABELS.get(slug, slug.rsplit("/", 1)[-1])