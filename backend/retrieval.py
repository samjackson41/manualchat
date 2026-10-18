"""Chunking, embedding, reranking, and Qdrant search/index (IMPLEMENTATION Task 3).

Turns a manual's ingest output into the chunks the RAG tools search over. The
ingest stage already wrote two things under ``manuals/{manual_id}/``: per-page
text (``page_text/page_NNNN.txt``) and the extracted tables (``tables.json``).
This module reads them, chunks them, embeds the chunks, and upserts them into a
local Qdrant collection.

Chunking follows the ratified values (DECISIONS D9-D11, D13):

  - D9  prose splits on section headings, and each table stays one chunk
  - D10 prose chunks target ``ingest_chunk_tokens`` tokens (512)
  - D11 adjacent chunks overlap by ``ingest_chunk_overlap_tokens`` tokens (64)
  - D13 token counting uses the ``ingest_tokenizer`` encoding (cl100k_base)

Storage follows D9-R9: an embedded local Qdrant (a directory on disk, no
server, no network, no credentials) with the ``qdrant_collection`` collection.
Heavy imports (tiktoken, sentence-transformers, qdrant-client) are deferred to
the functions that need them, so importing this module is free and does not
download a model. Run it with ``python -m backend.retrieval <manual_id>`` to
index, or add a query argument to search.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from functools import lru_cache
from pathlib import Path

from backend import storage
from backend.config import get_settings
from backend.schemas import ChunkPayload, IngestTable


# --- Token counting (DECISIONS D13) ---------------------------------------


@lru_cache(maxsize=None)
def _encoding(name: str):
    import tiktoken

    return tiktoken.get_encoding(name)


def _tokenizer():
    return _encoding(get_settings().ingest_tokenizer)


def count_tokens(text: str) -> int:
    """Token count under the configured chunking encoding."""
    return len(_tokenizer().encode(text))


# --- Section headings (DECISIONS D9) --------------------------------------


def is_heading(line: str) -> bool:
    """True when a line reads as a section heading, not prose.

    A heading is short, has no sentence ending, is numbered or mostly
    uppercase, and — when a single all-caps word — is long enough that inline
    attention labels (DANGER, WARNING, NOTE, CAUTION) do not split prose.
    """
    stripped = line.strip()
    if not stripped or len(stripped) > 80:
        return False
    if stripped[-1] in ".!?,;:":
        return False
    if not any(c.isalpha() for c in stripped):
        return False  # figure labels like "1" or "2"
    if stripped[0].isdigit() and stripped[1:2] in (" ", "."):
        return True  # numbered heading, e.g. "3. OIL"
    letters = [c for c in stripped if c.isalpha()]
    if sum(c.isupper() for c in letters) / len(letters) < 0.66:
        return False
    return " " in stripped or len(stripped) >= 8


def _prose_runs(page_number: int, text: str) -> list[tuple[str | None, str]]:
    """Split one page's text into (heading, body) runs at heading lines.

    A heading stays attached to the body it introduces, so windowing never
    splits a section title away from its content (D9).
    """
    if not get_settings().ingest_chunk_structure_aware:
        return [(None, text.strip())] if text.strip() else []

    runs: list[tuple[str | None, str]] = []
    heading: str | None = None
    body: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if is_heading(line):
            if heading is not None or body:
                runs.append((heading, "\n".join(body).strip()))
            heading = line
            body = []
        else:
            body.append(line)
    if heading is not None or body:
        runs.append((heading, "\n".join(body).strip()))
    return runs


def _window_text(text: str, max_tokens: int, overlap_tokens: int) -> list[str]:
    """Split one run of text into token-bounded windows with overlap."""
    if overlap_tokens >= max_tokens:
        raise ValueError("overlap must be smaller than the chunk size")
    tokens = _tokenizer().encode(text)
    if len(tokens) <= max_tokens:
        return [text] if text else []

    pieces: list[str] = []
    step = max_tokens - overlap_tokens
    start = 0
    total = len(tokens)
    while start < total:
        pieces.append(_tokenizer().decode(tokens[start : start + max_tokens]))
        if start + max_tokens >= total:
            break
        start += step
    return pieces


def _prose_chunks(
    text: str,
    page_number: int,
    section_name: str | None,
    vehicle_id: str,
    manual_id: str,
) -> list[ChunkPayload]:
    settings = get_settings()
    pieces = _window_text(
        text, settings.ingest_chunk_tokens, settings.ingest_chunk_overlap_tokens
    )
    return [
        ChunkPayload(
            text=piece,
            vehicle_id=vehicle_id,
            manual_id=manual_id,
            page_number=page_number,
            section_name=section_name,
        )
        for piece in pieces
    ]


def build_chunks(
    pages: dict[int, str],
    tables: list[IngestTable],
    vehicle_id: str,
    manual_id: str,
) -> list[ChunkPayload]:
    """Chunk pages and tables into the payloads that get embedded and stored.

    ``pages`` maps a 1-indexed physical page number to its normalized text;
    ``tables`` holds the extracted tables. Each chunk carries ``vehicle_id``,
    ``manual_id``, and ``page_number`` so retrieval can filter and cite.
    """
    chunks: list[ChunkPayload] = []
    for page_number in sorted(pages):
        for heading, body in _prose_runs(page_number, pages[page_number]):
            text = "\n".join(part for part in (heading, body) if part)
            chunks.extend(
                _prose_chunks(text, page_number, heading, vehicle_id, manual_id)
            )
    for table in tables:
        markdown = table.markdown.strip()
        if not markdown:
            continue
        # D9: a table stays one whole chunk, even when it exceeds the prose budget.
        chunks.append(
            ChunkPayload(
                text=markdown,
                vehicle_id=vehicle_id,
                manual_id=manual_id,
                page_number=table.page_number,
                section_name=table.caption,
                is_table=True,
            )
        )
    return chunks


# --- Embedding and reranking (DECISIONS R6-R8) ----------------------------


@lru_cache(maxsize=None)
def _sentence_transformer(model_name: str):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name)


@lru_cache(maxsize=None)
def _cross_encoder(model_name: str):
    from sentence_transformers import CrossEncoder
    import torch

    # ms-marco outputs raw logits; sigmoid maps them to 0-1 relevance, so a
    # score above 0.7 means "very likely relevant" (DECISIONS R7, Task 3 done-when).
    return CrossEncoder(model_name, activation_fn=torch.nn.Sigmoid())


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed texts with the first-pass bi-encoder, L2-normalized (R6)."""
    model = _sentence_transformer(get_settings().retrieval_embed_model)
    return model.encode(texts, normalize_embeddings=True).tolist()


def rerank_chunks(
    query: str, chunks: list[ChunkPayload], top_n: int
) -> list[ChunkPayload]:
    """Second pass with the cross-encoder (R7), keeping the top-n by score."""
    if not chunks:
        return []
    model = _cross_encoder(get_settings().retrieval_rerank_model)
    scores = model.predict([(query, c.text) for c in chunks])
    ranked = sorted(
        (c.model_copy(update={"score": float(score)}) for c, score in zip(chunks, scores)),
        key=lambda c: c.score,
        reverse=True,
    )
    return ranked[:top_n]


# --- Qdrant (DECISIONS R3-R4) --------------------------------------------


def _qdrant_dir() -> Path:
    """Absolute path to the local Qdrant store, repo-root-relative like manuals."""
    configured = Path(get_settings().qdrant_path)
    if configured.is_absolute():
        return configured
    return Path(__file__).resolve().parent.parent / configured


@lru_cache(maxsize=None)
def _client_for(location: tuple[str, str, bool, str]):
    url, api_key, is_memory, path = location
    from qdrant_client import QdrantClient

    if url:
        return QdrantClient(url=url, api_key=api_key or None)
    if is_memory:
        return QdrantClient(":memory:")
    return QdrantClient(path=path)


def _client():
    settings = get_settings()
    return _client_for(
        (
            settings.qdrant_url,
            settings.qdrant_api_key,
            settings.qdrant_path == ":memory:",
            str(_qdrant_dir()),
        )
    )


def _payload(chunk: ChunkPayload) -> dict:
    return {
        "text": chunk.text,
        "vehicle_id": chunk.vehicle_id,
        "manual_id": chunk.manual_id,
        "page_number": chunk.page_number,
        "section_name": chunk.section_name,
        "is_table": chunk.is_table,
    }


def _ensure_collection(client, dim: int) -> None:
    from qdrant_client.models import Distance, VectorParams

    collection = get_settings().qdrant_collection
    if not client.collection_exists(collection):
        client.create_collection(
            collection_name=collection,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )


def _delete_manual_points(client, manual_id: str) -> None:
    """Drop this manual's existing points so a re-index never duplicates them."""
    from qdrant_client.models import Filter, FieldCondition, FilterSelector, MatchValue

    client.delete(
        collection_name=get_settings().qdrant_collection,
        points_selector=FilterSelector(
            filter=Filter(
                must=[FieldCondition(key="manual_id", match=MatchValue(value=manual_id))]
            )
        ),
    )


def index_manual(manual_id: str, *, embed=None) -> int:
    """Chunk one ingested manual, embed the chunks, and upsert them into Qdrant.

    Returns the number of chunks stored and records it on the manual. ``embed``
    is injectable so tests never download a model (DECISIONS T1).
    """
    manual = storage.get_manual(manual_id)
    if manual is None:
        raise LookupError(f"manual not found: {manual_id}")

    chunks = build_chunks(
        _read_pages(manual_id), _read_tables(manual_id), manual.vehicle_id, manual_id
    )
    if not chunks:
        storage.update_manual(manual_id, chunk_count=0)
        return 0

    embed_fn = embed or embed_texts
    vectors = embed_fn([c.text for c in chunks])
    dim = len(vectors[0])

    client = _client()
    _ensure_collection(client, dim)
    _delete_manual_points(client, manual_id)
    from qdrant_client.models import PointStruct

    points = [
        # IDs must be unique across the whole collection, so they are derived
        # from the manual id; a bare chunk index would collide between manuals.
        PointStruct(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{manual_id}:chunk:{i}")),
            vector=[float(x) for x in vec],
            payload=_payload(chunk),
        )
        for i, (chunk, vec) in enumerate(zip(chunks, vectors))
    ]
    client.upsert(
        collection_name=get_settings().qdrant_collection, points=points, wait=True
    )
    storage.update_manual(manual_id, chunk_count=len(chunks))
    return len(chunks)


def search(
    query: str,
    vehicle_id: str,
    manual_id: str | None = None,
    top_n: int | None = None,
    *,
    embed=None,
    rerank=None,
) -> list[ChunkPayload]:
    """Two-stage retrieval: bi-encoder first pass, cross-encoder rerank (R6-R9)."""
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    settings = get_settings()
    embed_fn = embed or embed_texts
    rerank_fn = rerank or rerank_chunks

    must = [FieldCondition(key="vehicle_id", match=MatchValue(value=vehicle_id))]
    if manual_id:
        must.append(FieldCondition(key="manual_id", match=MatchValue(value=manual_id)))

    vector = [float(x) for x in embed_fn([query])[0]]
    hits = _client().query_points(
        collection_name=settings.qdrant_collection,
        query=vector,
        query_filter=Filter(must=must),
        limit=settings.retrieval_candidate_k,
        with_payload=True,
    ).points

    candidates = [
        ChunkPayload(
            text=hit.payload.get("text", ""),
            vehicle_id=hit.payload.get("vehicle_id", vehicle_id),
            manual_id=hit.payload.get("manual_id", ""),
            page_number=hit.payload.get("page_number", 0),
            section_name=hit.payload.get("section_name"),
            is_table=bool(hit.payload.get("is_table", False)),
            score=float(hit.score),
        )
        for hit in hits
    ]
    return rerank_fn(query, candidates, top_n or settings.retrieval_top_n)


# --- Ingest-output readers ------------------------------------------------


def _read_pages(manual_id: str) -> dict[int, str]:
    page_dir = storage.manual_dir(manual_id) / "page_text"
    pages: dict[int, str] = {}
    if not page_dir.is_dir():
        return pages
    for path in sorted(page_dir.glob("page_*.txt")):
        try:
            page_number = int(path.stem.split("_", 1)[1])
        except (IndexError, ValueError):
            continue
        pages[page_number] = path.read_text()
    return pages


def _read_tables(manual_id: str) -> list[IngestTable]:
    tables_path = storage.manual_dir(manual_id) / "tables.json"
    if not tables_path.is_file():
        return []
    return [IngestTable.model_validate(t) for t in json.loads(tables_path.read_text())]


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="backend.retrieval",
        description="Chunk and index one ingested manual, or search it.",
    )
    parser.add_argument("manual_id", help="the stored manual's UUID directory name")
    parser.add_argument(
        "query", nargs="?", default=None, help="search the manual instead of indexing"
    )
    args = parser.parse_args(argv)

    manual = storage.get_manual(args.manual_id)
    if manual is None:
        print(f"manual not found: {args.manual_id}", file=sys.stderr)
        return 1

    if args.query is None:
        count = index_manual(args.manual_id)
        print(f"Indexed {count} chunks for manual {args.manual_id}")
        return 0

    for chunk in search(args.query, manual.vehicle_id, args.manual_id):
        print(f"{chunk.score:.3f}  [p{chunk.page_number}]  {chunk.text[:80].strip()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))