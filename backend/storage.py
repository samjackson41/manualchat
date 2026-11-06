"""Local manual and vehicle storage, one subdirectory per record.

Implements DECISIONS U1: each manual is uploaded once and its processed result
stays on disk under `manuals_dir/{manual_id}/` so it is never re-derived.

On-disk layout (per manual):

    {manuals_dir}/
      {manual_id}/          # a server-generated UUID, never client input
        source.pdf          # the uploaded bytes (fixed name)
        manual.json         # the Manual record, JSON-serialised

Vehicle profiles (SPECIFICATION §5) mirror the manual layout:

    {vehicles_dir}/
      {vehicle_id}/         # a server-generated UUID, never client input
        vehicle.json        # the Vehicle record, JSON-serialised

The original filename is kept only in the `source_filename` field of the
record; the on-disk name is fixed so a hostile filename cannot escape the
directory.
"""

import hashlib
import shutil
import json
import uuid
from pathlib import Path

from pydantic import ValidationError

from backend.config import get_settings
from backend.schemas import Manual, Vehicle


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
    source_filename: str,
    content_hash: str | None = None,
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
        content_hash=content_hash,
        status="processing",
    )
    _write_manual(manual)
    return manual


def content_hash_of(manual: Manual) -> str | None:
    """Return a manual's content hash, computing it from `source.pdf` if absent.

    A record written before `content_hash` existed carries no digest, so the
    stored PDF is hashed on demand and the digest is written back. Returns None
    only when the stored PDF is missing.
    """
    if manual.content_hash:
        return manual.content_hash
    source = manual_dir(manual.manual_id) / "source.pdf"
    if not source.is_file():
        return None
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    update_manual(manual.manual_id, content_hash=digest)
    return digest


def find_duplicate(vehicle_id: str, content_hash: str) -> Manual | None:
    """Return the manual of `vehicle_id` whose bytes hash to `content_hash`.

    The digest is the SHA-256 of the uploaded PDF. A match means the same PDF
    was already stored under this vehicle, so the new upload is a re-upload
    (DECISIONS U2). Returns None when no stored manual matches.
    """
    for manual in list_manuals():
        if manual.vehicle_id != vehicle_id:
            continue
        if content_hash_of(manual) == content_hash:
            return manual
    return None


def manual_dir(manual_id: str) -> Path:
    """Absolute path to one manual's directory, parent of its ``source.pdf``."""
    return manuals_root() / manual_id


def _write_manual(manual: Manual) -> None:
    """Write one manual record, replacing the file in a single step.

    Ingest rewrites the record while it runs so the upload dialog can poll its
    progress. A reader must never catch a half-written file.
    """
    record_path = manual_dir(manual.manual_id) / "manual.json"
    temp_path = record_path.with_name(record_path.name + ".tmp")
    temp_path.write_text(json.dumps(manual.model_dump(mode="json"), indent=2))
    temp_path.replace(record_path)


def update_manual(manual_id: str, **updates) -> Manual | None:
    """Patch a manual's record fields and persist it, or return None when unknown.

    The ingest pipeline uses this to fill in ``page_count``, ``status``, and
    ``progress`` after a successful run without replacing the ``Manual``
    identity.
    """
    manual = get_manual(manual_id)
    if manual is None:
        return None
    updated = manual.model_copy(update=updates)
    _write_manual(updated)
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


def delete_manual(manual_id: str) -> bool:
    """Remove a manual and its directory, or return False when unknown.

    This is permanent: the source PDF and the processed result (page text,
    tables, ingest summary) go with it. Indexed chunks are purged by the API
    layer before this runs (retrieval imports storage, so storage cannot
    import retrieval).
    """
    if get_manual(manual_id) is None:
        return False
    shutil.rmtree(manuals_root() / manual_id)
    return True


# --- Vehicle profiles (SPECIFICATION §5) ----------------------------------


def vehicles_root() -> Path:
    """Absolute path to the vehicles directory (`vehicles_dir`).

    Mirrors `manuals_root()`: a relative `vehicles_dir` resolves against the
    repo root, not the process CWD.
    """
    configured = Path(get_settings().vehicles_dir)
    if configured.is_absolute():
        return configured
    return Path(__file__).resolve().parent.parent / configured


def _write_vehicle(vehicle: Vehicle) -> None:
    """Write a vehicle record to its `vehicle.json`, creating nothing else."""
    record_path = vehicles_root() / vehicle.vehicle_id / "vehicle.json"
    record_path.write_text(json.dumps(vehicle.model_dump(mode="json"), indent=2))


def store_vehicle(display_name: str) -> Vehicle:
    """Create a new vehicle profile and return its record.

    The `vehicle_id` is generated here (a UUID) and never taken from the
    client, so a request cannot address another vehicle's directory.
    """
    vehicle_id = str(uuid.uuid4())
    vehicle_dir = vehicles_root() / vehicle_id
    vehicle_dir.mkdir(parents=True, exist_ok=False)

    vehicle = Vehicle(vehicle_id=vehicle_id, display_name=display_name)
    _write_vehicle(vehicle)
    return vehicle


def list_vehicles() -> list[Vehicle]:
    """Return every vehicle profile, newest first."""
    root = vehicles_root()
    records: list[Vehicle] = []
    if not root.is_dir():
        return records
    for vehicle_dir in root.iterdir():
        record_path = vehicle_dir / "vehicle.json"
        if not record_path.is_file():
            continue
        try:
            records.append(Vehicle.model_validate_json(record_path.read_text()))
        except (ValidationError, json.JSONDecodeError):
            continue
    records.sort(key=lambda v: v.created_at, reverse=True)
    return records


def get_vehicle(vehicle_id: str) -> Vehicle | None:
    """Return one vehicle by id, or None when unknown."""
    record_path = vehicles_root() / vehicle_id / "vehicle.json"
    if not record_path.is_file():
        return None
    try:
        return Vehicle.model_validate_json(record_path.read_text())
    except (ValidationError, json.JSONDecodeError):
        return None


def rename_vehicle(vehicle_id: str, display_name: str) -> Vehicle | None:
    """Change a vehicle's display name, or return None when unknown."""
    vehicle = get_vehicle(vehicle_id)
    if vehicle is None:
        return None
    updated = vehicle.model_copy(update={"display_name": display_name})
    _write_vehicle(updated)
    return updated


def delete_vehicle(vehicle_id: str) -> bool:
    """Remove a vehicle and its directory, or return False when unknown."""
    if get_vehicle(vehicle_id) is None:
        return False
    shutil.rmtree(vehicles_root() / vehicle_id)
    return True