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