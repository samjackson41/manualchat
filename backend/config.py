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
    super_sub_tiers         <- SUPER_SUB_TIERS         (JSON)
    super_sub_slug_tiers    <- SUPER_SUB_SLUG_TIERS    (JSON)
    super_sub_default_tier  <- SUPER_SUB_DEFAULT_TIER
    agent_max_hops          <- AGENT_MAX_HOPS
    agent_max_tool_steps    <- AGENT_MAX_TOOL_STEPS
    openrouter_api_key      <- OPENROUTER_API_KEY
    langsmith_tracing       <- LANGSMITH_TRACING     (default false)
    langsmith_api_key       <- LANGSMITH_API_KEY     (secret, env only)
    langsmith_project       <- LANGSMITH_PROJECT
    langsmith_endpoint      <- LANGSMITH_ENDPOINT
    ingest_chunk_tokens     <- INGEST_CHUNK_TOKENS
    qdrant_url              <- QDRANT_URL      (empty = local mode)
    retrieval_embed_model   <- RETRIEVAL_EMBED_MODEL
    eval_judge_model        <- EVAL_JUDGE_MODEL
    eval_vehicle_id         <- EVAL_VEHICLE_ID   (the eval manual's vehicle)
    eval_min_pass_rate      <- EVAL_MIN_PASS_RATE
    eval_citation_precision_min <- EVAL_CITATION_PRECISION_MIN
"""

from functools import lru_cache
import json

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Display labels for the model selector. The slugs in `model_options` are the
# source of truth (DECISIONS M2). OpenRouter requires the `~` prefix.
_FLASH = "~deepseek/deepseek-flash-latest"
_PRO = "~deepseek/deepseek-pro-latest"

_MODEL_LABELS: dict[str, str] = {
    _FLASH: "DeepSeek Flash",
    _PRO: "DeepSeek Pro",
}


class SuperSubTier(BaseModel):
    """One model tier: the supervisor and the retrieval worker, with effort.

    The supervisor plans and writes the final answer; the sub-agent is the
    retrieval worker that runs the tool loop (DECISIONS M1).
    """

    supervisor_model: str
    supervisor_effort: str
    sub_model: str
    sub_effort: str


def _default_tiers() -> dict[str, SuperSubTier]:
    """The ratified tier table (DECISIONS M1). Overridable with `SUPER_SUB_TIERS`."""
    return {
        "fast": SuperSubTier(
            supervisor_model=_FLASH,
            supervisor_effort="high",
            sub_model=_FLASH,
            sub_effort="low",
        ),
        "pro": SuperSubTier(
            supervisor_model=_PRO,
            supervisor_effort="max",
            sub_model=_FLASH,
            sub_effort="high",
        ),
    }


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    # --- Secret (env only) ---
    # Not required at import, so /health works without a key.
    openrouter_api_key: str = ""

    # OpenRouter base URL (chat completions endpoint is appended in llm.py).
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # --- Model selection (DECISIONS M1-M3) ---
    model_default: str = _FLASH
    model_options: list[str] = Field(default_factory=lambda: [_FLASH, _PRO])

    # --- Generation params (tunable via env; unset values are omitted) ---
    model_reasoning_effort: str | None = "medium"  # fallback when a node passes no effort
    model_temperature: float | None = None         # TBD
    model_max_tokens: int | None = None            # TBD

    # --- Supervisor and sub-agent tiers (DECISIONS M1) ---
    # Keyed by tier name (`fast`, `pro`); each entry fixes the supervisor and
    # the worker model and reasoning effort. Load with JSON, e.g.
    # SUPER_SUB_TIERS='{"fast": {"supervisor_model": "...", ...}, "pro": {...}}'.
    super_sub_tiers: dict[str, SuperSubTier] = Field(default_factory=_default_tiers)
    # The selected slug picks a tier; an unknown slug falls back to the default.
    super_sub_slug_tiers: dict[str, str] = Field(
        default_factory=lambda: {_FLASH: "fast", _PRO: "pro"}
    )
    super_sub_default_tier: str = "fast"
    # Hop cap: the supervisor forces synthesis after this many worker hops
    # (IMPLEMENTATION §7). `agent_max_tool_steps` caps the worker's tool loop.
    agent_max_hops: int = 4
    agent_max_tool_steps: int = 4

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

    # --- Automated evals (IMPLEMENTATION Task 7) ---
    # The judge model stays distinct from the model under test: the eval runs
    # the agent on Flash, so Pro judges and self-preference bias stays low.
    eval_judge_model: str = _PRO
    # Reasoning effort for the judge call. OpenRouter lists `high` for both
    # DeepSeek slugs, so no fallback is needed (DECISIONS M1).
    eval_judge_reasoning_effort: str = "high"
    # A score at or above this passes a case when the judge omits `passed`.
    eval_pass_threshold: float = 0.7
    # CI gate on the overall pass rate (Task 7).
    eval_min_pass_rate: float = 0.8
    # The vehicle that owns the eval manual. Supplied at run time, because the
    # vehicle id is generated per upload; the runner reads `EVAL_VEHICLE_ID`.
    eval_vehicle_id: str = ""
    # CI gate on citation precision (Task 7 needs more than 0.9).
    eval_citation_precision_min: float = 0.9

    # --- LangSmith tracing (MVP+1 monitoring) ---
    # Off until both LANGSMITH_TRACING=true and LANGSMITH_API_KEY are set.
    # backend/tracing.py records one LLM run per OpenRouter call with the
    # token usage, the wall-clock latency, and any error. A failed post is
    # swallowed, so an unreachable LangSmith never breaks the chat.
    langsmith_tracing: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "manualchat"
    langsmith_endpoint: str = "https://api.smith.langchain.com"

    @field_validator("model_options", mode="before")
    @classmethod
    def _split_model_options(cls, value):
        """Allow `MODEL_OPTIONS=a,b,c` (comma-separated) in addition to a list."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("super_sub_tiers", "super_sub_slug_tiers", mode="before")
    @classmethod
    def _parse_json_dict(cls, value):
        """Allow a JSON string (e.g. `SUPER_SUB_TIERS=...`) as well as a dict."""
        if isinstance(value, str):
            return json.loads(value)
        return value

    @field_validator("langsmith_tracing", mode="before")
    @classmethod
    def _empty_string_means_off(cls, value):
        # Compose passes `LANGSMITH_TRACING=${LANGSMITH_TRACING:-}`, which is an
        # empty string when the host shell leaves it unset; that means off.
        if value == "":
            return False
        return value

    def tier_for_model(self, model: str) -> SuperSubTier:
        """Resolve a selected model slug to its supervisor/worker tier.

        A slug that is not in `super_sub_slug_tiers` falls back to
        `super_sub_default_tier` (DECISIONS M1).
        """
        name = self.super_sub_slug_tiers.get(model, self.super_sub_default_tier)
        return self.super_sub_tiers.get(name) or self.super_sub_tiers[
            self.super_sub_default_tier
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()


def model_label(slug: str) -> str:
    """Friendly dropdown label for a model slug, falling back to the slug tail."""
    return _MODEL_LABELS.get(slug, slug.rsplit("/", 1)[-1])