"""Application configuration.

Reads ONLY environment variables — there is deliberately NO `.env` file in
this repo (secrets and tunables are supplied at run time). Field names map to
env vars case-insensitively, so:

    model_reasoning_effort  <- MODEL_REASONING_EFFORT
    model_temperature       <- MODEL_TEMPERATURE
    model_max_tokens        <- MODEL_MAX_TOKENS
    agent_system_prompt     <- AGENT_SYSTEM_PROMPT
    manuals_dir             <- MANUALS_DIR
    vehicles_dir            <- VEHICLES_DIR
    model_default           <- MODEL_DEFAULT
    model_options           <- MODEL_OPTIONS   (comma-separated)
    openrouter_api_key      <- OPENROUTER_API_KEY
    ingest_chunk_tokens     <- INGEST_CHUNK_TOKENS
    qdrant_url              <- QDRANT_URL      (empty = local mode)
    retrieval_embed_model   <- RETRIEVAL_EMBED_MODEL
"""

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Display labels for the model selector. The slugs in `model_options` are the
# source of truth (DECISIONS M2). OpenRouter requires the `~` prefix.
_MODEL_LABELS: dict[str, str] = {
    "~deepseek/deepseek-flash-latest": "DeepSeek Flash",
    "~deepseek/deepseek-pro-latest": "DeepSeek Pro",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    # --- Secret (env only) ---
    # Not required at import, so /health works without a key.
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

    # --- Generation params (tunable via env; unset values are omitted) ---
    model_reasoning_effort: str | None = "medium"  # ratified (DECISIONS M note)
    model_temperature: float | None = None         # TBD
    model_max_tokens: int | None = None            # TBD

    # --- Agent graph (DECISIONS A3) ---
    agent_system_prompt: str = (
        "You are a grounded repair-manual assistant. Answer using only the "
        "manual content that the retrieval tools return. Never answer from your "
        "own outside knowledge of vehicles.\n"
        "\n"
        "Answering style:\n"
        "- Lead with the direct answer, then stop. Do not keep going into nearby "
        "or related manual topics the question did not ask for.\n"
        "- Size the answer to the question: a one-value question gets the value "
        "and its page, not the surrounding procedure.\n"
        "\n"
        "Grounding rules:\n"
        "\n"
        "1. Cite when the source page changes. Within one paragraph or numbered "
        "list, one [Page N] covers every fact drawn from page N; add another "
        "citation only when a fact comes from a different page. Never repeat the "
        "same [Page N] on every sentence, clause, or step.\n"
        "2. Answer only from the retrieved manual content. Do not add, infer, or "
        "guess anything the manual does not state.\n"
        "3. If the manual does not contain the asked-for value or procedure, "
        "output exactly: \"The manual does not contain information on [topic].\" "
        "Replace [topic] with the question's topic. You may follow with at most "
        "one sentence naming the single closest real fact, with no page "
        "citation, only when that fact directly explains why the answer is "
        "absent.\n"
        "4. If the manual gives conflicting values for one thing, show every "
        "value with its own [Page N] citation. Do not pick one and do not invent "
        "a middle value.\n"
        "\n"
        "Use the retrieval tools (search_manual, extract_specs, get_page_text) "
        "when the question needs facts or steps from the manual."
    )

    # --- Local manual storage (DECISIONS U1) ---
    # Directory that holds one `{manual_id}/` subdirectory per uploaded manual,
    # with the source PDF and its JSON record inside it.
    manuals_dir: str = "manuals"

    # --- Local vehicle storage ---
    # Directory that holds one `{vehicle_id}/` subdirectory per vehicle profile,
    # with its JSON record inside it.
    vehicles_dir: str = "vehicles"

    # --- Manual viewer: raster thumbnails (IMPLEMENTATION Task 5) ---
    # Resolution of the PNG page previews, in dots per inch (Task 2).
    thumbnail_dpi: int = 150

    # --- Manual viewer: caching of stored page bytes (DECISIONS V5) ---
    # A manual and its pages never change after upload (DECISIONS U1), so the
    # viewer may cache the served bytes for this long, in seconds.
    viewer_cache_max_age_seconds: int = 31536000

    # --- Ingestion pipeline (DECISIONS D1-D3, D12; IMPLEMENTATION Task 1) ---
    # OCR is off for MVP because every manual is born-digital (DECISIONS S2).
    ingest_do_ocr: bool = False
    # The text-layer probe: a manual needs OCR when its average text per page
    # falls below this many characters (DECISIONS D1).
    ingest_ocr_min_chars_per_page: float = 50.0
    # Strip an invisible OCR font layer (e.g. `HiddenHorzOCR`) before Docling
    # reads the PDF (DECISIONS D2).
    ingest_strip_hidden_ocr_layer: bool = True
    # Run the unit/header normalization stage explicitly after Docling
    # (DECISIONS D3).
    ingest_normalization_enabled: bool = True
    # Citations carry the physical PDF page number; printed page numbers are
    # not recovered (DECISIONS D12).
    ingest_use_printed_page_numbers: bool = False
    # Docling runtime flags. `FAST` table mode and the low thread/batch values
    # keep peak memory below the spike's documented crash threshold.
    ingest_do_table_structure: bool = True
    ingest_table_mode: str = "FAST"
    ingest_threads: int = 2
    ingest_batch_size: int = 1

    # --- Chunking (DECISIONS D9-D13) ---
    # Split prose on section headings and keep each table as one chunk (D9).
    ingest_chunk_structure_aware: bool = True
    # Prose chunk target and overlap, in tokens (D10, D11).
    ingest_chunk_tokens: int = 512
    ingest_chunk_overlap_tokens: int = 64
    # Token counter for chunking (D13), the cl100k_base tiktoken encoding.
    ingest_tokenizer: str = "cl100k_base"

    # --- Retrieval (DECISIONS R3-R9) ---
    # Empty `qdrant_url` means embedded local mode (R3): Qdrant stores under
    # `qdrant_path` on disk with no server, network, or credentials. A http(s)
    # URL switches to a remote client.
    qdrant_url: str = ""
    qdrant_path: str = "qdrant"  # local-mode on-disk dir, repo-relative
    qdrant_collection: str = "manualchat_chunks"  # R4
    qdrant_api_key: str = ""  # R5 (empty in dev; production sets it via env)
    retrieval_embed_model: str = "multi-qa-mpnet-base-dot-v1"  # R6
    retrieval_rerank_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"  # R7
    retrieval_candidate_k: int = 50  # R8, first-pass candidates for the reranker
    retrieval_top_n: int = 5  # R9, chunks returned to the agent

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