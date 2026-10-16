"""Local manual storage — one `{manual_id}/` subdirectory per manual.

Implements DECISIONS U1: each manual is uploaded once and its processed result
stays on disk under `manuals_dir/{manual_id}/` so it is never re-derived.

On-disk layout (per manual):

    {manuals_dir}/
      {manual_id}/          # a server-generated UUID, never client input
        source.pdf          # the uploaded bytes (fixed name)
        manual.json         # the Manual record, JSON-serialised

The original filename is kept only in the `source_filename` field of the
record; the on-disk name is fixed so a hostile filename cannot escape the
directory.
"""

import json
import uuid
from pathlib import Path

from pydantic import ValidationError

from backend.config import get_settings
from backend.schemas import Manual


def manuals_root() -> Path:
    """Absolute path to the manuals directory (DECISIONS U1 / `manuals_dir`).

    A relative `manuals_dir` resolves against the repo root (the package's
    parent, `backend/..`), not the process CWD, so bare-metal and container
    runs agree regardless of where the server was started.
    """
    configured = Path(get_settings().manuals_dir)
    if configured.is_absolute():
        return configured
    return Path(__file__).resolve().parent.parent / configured


def store_manual(
    source_pdf: bytes,
    vehicle_id: str,
    display_name: str,
    kind: str,
    source_filename: str,
) -> Manual:
    """Write an uploaded manual and return its record.

    The `manual_id` is generated here (a UUID) and never taken from the
    client, so a request cannot address another manual's directory.
    """
    manual_id = str(uuid.uuid4())
    manual_dir = manuals_root() / manual_id
    manual_dir.mkdir(parents=True, exist_ok=False)

    (manual_dir / "source.pdf").write_bytes(source_pdf)

    manual = Manual(
        manual_id=manual_id,
        vehicle_id=vehicle_id,
        display_name=display_name,
        source_filename=source_filename,
        kind=kind,
        status="ready",
    )
    (manual_dir / "manual.json").write_text(
        json.dumps(manual.model_dump(mode="json"), indent=2)
    )
    return manual


def manual_dir(manual_id: str) -> Path:
    """Absolute path to one manual's directory, parent of its ``source.pdf``."""
    return manuals_root() / manual_id


def update_manual(manual_id: str, **updates) -> Manual | None:
    """Patch a manual's record fields and persist it, or return None when unknown.

    The ingest pipeline uses this to fill in ``page_count`` and ``status`` after
    a successful run without replacing the ``Manual`` identity.
    """
    manual = get_manual(manual_id)
    if manual is None:
        return None
    updated = manual.model_copy(update=updates)
    (manual_dir(manual_id) / "manual.json").write_text(
        json.dumps(updated.model_dump(mode="json"), indent=2)
    )
    return updated


def list_manuals() -> list[Manual]:
    """Return every stored manual, newest first."""
    root = manuals_root()
    records: list[Manual] = []
    if not root.is_dir():
        return records
    for manual_dir in root.iterdir():
        record_path = manual_dir / "manual.json"
        if not record_path.is_file():
            continue
        try:
            records.append(Manual.model_validate_json(record_path.read_text()))
        except (ValidationError, json.JSONDecodeError):
            continue
    records.sort(key=lambda m: m.created_at, reverse=True)
    return records


def get_manual(manual_id: str) -> Manual | None:
    """Return one manual by id, or None when unknown."""
    record_path = manuals_root() / manual_id / "manual.json"
    if not record_path.is_file():
        return None
    try:
        return Manual.model_validate_json(record_path.read_text())
    except (ValidationError, json.JSONDecodeError):
        return None