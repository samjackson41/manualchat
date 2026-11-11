"""Manual and vehicle storage over a local disk or a GCS bucket (DEPLOYMENT M1).

Implements DECISIONS U1: each manual is uploaded once and its processed result
stays under ``manuals/{manual_id}/`` so it is never re-derived. A
``StorageBackend`` maps object keys (``manuals/{id}/source.pdf``) to local files
or GCS blobs, so the serving image can read and write the same layout without
local disk.

Ingest and indexing are local-only by design (DEPLOYMENT M1): they need a real
file path for Docling and PyMuPDF. ``manual_dir`` returns that path and raises
on the ``gcs`` backend, which never runs ingest.
"""

import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from backend.config import get_settings
from backend.schemas import Manual, Vehicle


class StorageBackend(Protocol):
    """Byte and text access to one storage backend, keyed by object keys."""

    def read_bytes(self, key: str) -> bytes: ...
    def write_bytes(self, key: str, data: bytes) -> None: ...
    def read_text(self, key: str) -> str: ...
    def write_text(self, key: str, text: str) -> None: ...
    def exists(self, key: str) -> bool: ...
    def delete(self, key: str) -> None: ...
    def delete_prefix(self, prefix: str) -> None: ...
    def stat(self, key: str) -> tuple[int, int]: ...
    def list_keys(self, prefix: str) -> list[str]: ...


def _manual_key(manual_id: str, name: str) -> str:
    return f"manuals/{manual_id}/{name}"


def _vehicle_key(vehicle_id: str) -> str:
    return f"vehicles/{vehicle_id}/vehicle.json"


def manuals_root() -> Path:
    """Absolute path to the manuals directory (DECISIONS U1 / `manuals_dir`)."""
    configured = Path(get_settings().manuals_dir)
    if configured.is_absolute():
        return configured
    return Path(__file__).resolve().parent.parent / configured


def vehicles_root() -> Path:
    """Absolute path to the vehicles directory (`vehicles_dir`)."""
    configured = Path(get_settings().vehicles_dir)
    if configured.is_absolute():
        return configured
    return Path(__file__).resolve().parent.parent / configured


class LocalStorage:
    """Local disk backend: ``manuals/…`` and ``vehicles/…`` keys map to files."""

    def __init__(self, manuals: Path, vehicles: Path):
        self._manuals = manuals
        self._vehicles = vehicles

    def _path(self, key: str) -> Path:
        if key.startswith("manuals/"):
            return self._manuals / key[len("manuals/"):]
        if key.startswith("vehicles/"):
            return self._vehicles / key[len("vehicles/"):]
        raise ValueError(f"unknown key prefix: {key}")

    def _atomic_write(self, path: Path, data: bytes) -> None:
        # Ingest rewrites records while a reader polls them; the tmp+replace
        # keeps a reader from ever catching a half-written file.
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)

    def read_bytes(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def write_bytes(self, key: str, data: bytes) -> None:
        self._atomic_write(self._path(key), data)

    def read_text(self, key: str) -> str:
        return self._path(key).read_text()

    def write_text(self, key: str, text: str) -> None:
        self._atomic_write(self._path(key), text.encode())

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def delete_prefix(self, prefix: str) -> None:
        root, rel = self._split_prefix(prefix)
        base = root / rel
        if base.is_dir():
            shutil.rmtree(base)

    def stat(self, key: str) -> tuple[int, int]:
        st = self._path(key).stat()
        return (st.st_size, st.st_mtime_ns)

    def list_keys(self, prefix: str) -> list[str]:
        root, rel = self._split_prefix(prefix)
        base = root / rel
        if not base.is_dir():
            return []
        namespace = "manuals" if root == self._manuals else "vehicles"
        return [
            f"{namespace}/" + str(p.relative_to(root))
            for p in base.rglob("*")
            if p.is_file()
        ]

    def _split_prefix(self, prefix: str) -> tuple[Path, str]:
        for namespace, root in (("manuals", self._manuals), ("vehicles", self._vehicles)):
            if prefix.startswith(namespace):
                return root, prefix[len(namespace):].lstrip("/")
        raise ValueError(f"unknown key prefix: {prefix}")


class GCSStorage:
    """Google Cloud Storage backend: object keys map to blob names."""

    def __init__(self, bucket_name: str, client):
        self._bucket = client.bucket(bucket_name)

    def read_bytes(self, key: str) -> bytes:
        blob = self._bucket.blob(key)
        if not blob.exists():
            raise FileNotFoundError(key)
        return blob.download_as_bytes()

    def write_bytes(self, key: str, data: bytes) -> None:
        self._bucket.blob(key).upload_from_string(data)

    def read_text(self, key: str) -> str:
        return self.read_bytes(key).decode()

    def write_text(self, key: str, text: str) -> None:
        self.write_bytes(key, text.encode())

    def exists(self, key: str) -> bool:
        return self._bucket.blob(key).exists()

    def delete(self, key: str) -> None:
        self._bucket.blob(key).delete()

    def delete_prefix(self, prefix: str) -> None:
        blobs = list(self._bucket.list_blobs(prefix=prefix))
        if blobs:
            self._bucket.delete_blobs(blobs)

    def stat(self, key: str) -> tuple[int, int]:
        blob = self._bucket.get_blob(key)
        if blob is None:
            raise FileNotFoundError(key)
        return (blob.size or 0, int(blob.updated.timestamp() * 1e9))

    def list_keys(self, prefix: str) -> list[str]:
        return [blob.name for blob in self._bucket.list_blobs(prefix=prefix)]


_gcs_client = None


def _gcs():
    global _gcs_client
    if _gcs_client is None:
        from google.cloud import storage as gcs

        _gcs_client = gcs.Client()
    return _gcs_client


def _backend() -> StorageBackend:
    settings = get_settings()
    if settings.storage_backend == "gcs":
        if not settings.gcs_bucket:
            raise RuntimeError("GCS_BUCKET must be set when STORAGE_BACKEND=gcs")
        return GCSStorage(settings.gcs_bucket, _gcs())
    return LocalStorage(manuals_root(), vehicles_root())


# --- Byte-level manual accessors (the serving read/write surface) ----------


def read_manual_bytes(manual_id: str, name: str) -> bytes:
    return _backend().read_bytes(_manual_key(manual_id, name))


def write_manual_bytes(manual_id: str, name: str, data: bytes) -> None:
    _backend().write_bytes(_manual_key(manual_id, name), data)


def read_manual_text(manual_id: str, name: str) -> str:
    return _backend().read_text(_manual_key(manual_id, name))


def write_manual_text(manual_id: str, name: str, text: str) -> None:
    _backend().write_text(_manual_key(manual_id, name), text)


def manual_file_exists(manual_id: str, name: str) -> bool:
    return _backend().exists(_manual_key(manual_id, name))


def manual_file_stat(manual_id: str, name: str) -> tuple[int, int]:
    return _backend().stat(_manual_key(manual_id, name))


def page_text_name(page_number: int) -> str:
    return f"page_text/page_{page_number:04d}.txt"


# --- Manual records ---------------------------------------------------------


def store_manual(
    source_pdf: bytes,
    vehicle_id: str,
    display_name: str,
    source_filename: str,
    content_hash: str | None = None,
) -> Manual:
    """Write an uploaded manual and return its record."""
    manual_id = str(uuid.uuid4())
    write_manual_bytes(manual_id, "source.pdf", source_pdf)

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


def manual_dir(manual_id: str) -> Path:
    """Local-only path to one manual's directory (ingest and indexing)."""
    if get_settings().storage_backend == "gcs":
        raise RuntimeError("manual_dir is local-only; the gcs backend has no paths")
    return manuals_root() / manual_id


def _write_manual(manual: Manual) -> None:
    write_manual_text(
        manual.manual_id, "manual.json", json.dumps(manual.model_dump(mode="json"), indent=2)
    )


def content_hash_of(manual: Manual) -> str | None:
    """Return a manual's content hash, computing it from `source.pdf` if absent."""
    if manual.content_hash:
        return manual.content_hash
    if not manual_file_exists(manual.manual_id, "source.pdf"):
        return None
    digest = hashlib.sha256(read_manual_bytes(manual.manual_id, "source.pdf")).hexdigest()
    update_manual(manual.manual_id, content_hash=digest)
    return digest


def find_duplicate(vehicle_id: str, content_hash: str) -> Manual | None:
    """Return the manual of `vehicle_id` whose bytes hash to `content_hash`."""
    for manual in list_manuals():
        if manual.vehicle_id != vehicle_id:
            continue
        if content_hash_of(manual) == content_hash:
            return manual
    return None


def update_manual(manual_id: str, **updates) -> Manual | None:
    """Patch a manual's record fields and persist it, or return None when unknown."""
    manual = get_manual(manual_id)
    if manual is None:
        return None
    updated = manual.model_copy(update=updates)
    _write_manual(updated)
    return updated


def list_manuals() -> list[Manual]:
    """Return every stored manual, newest first."""
    records: list[Manual] = []
    for key in _backend().list_keys("manuals/"):
        if not key.endswith("/manual.json"):
            continue
        manual = get_manual(key.split("/")[1])
        if manual is not None:
            records.append(manual)
    records.sort(key=lambda m: m.created_at, reverse=True)
    return records


def get_manual(manual_id: str) -> Manual | None:
    """Return one manual by id, or None when unknown."""
    if not manual_file_exists(manual_id, "manual.json"):
        return None
    try:
        return Manual.model_validate_json(read_manual_text(manual_id, "manual.json"))
    except (ValidationError, json.JSONDecodeError):
        return None


def delete_manual(manual_id: str) -> bool:
    """Remove a manual and its files, or return False when unknown.

    This is permanent. Indexed chunks are purged by the API layer before this
    runs (retrieval imports storage, so storage cannot import retrieval).
    """
    if get_manual(manual_id) is None:
        return False
    _backend().delete_prefix(f"manuals/{manual_id}/")
    return True


# --- Vehicle profiles (SPECIFICATION §5) ------------------------------------


def _write_vehicle(vehicle: Vehicle) -> None:
    _backend().write_text(
        _vehicle_key(vehicle.vehicle_id),
        json.dumps(vehicle.model_dump(mode="json"), indent=2),
    )


def store_vehicle(display_name: str) -> Vehicle:
    """Create a new vehicle profile and return its record."""
    vehicle_id = str(uuid.uuid4())
    vehicle = Vehicle(vehicle_id=vehicle_id, display_name=display_name)
    _write_vehicle(vehicle)
    return vehicle


def list_vehicles() -> list[Vehicle]:
    """Return every vehicle profile, newest first."""
    records: list[Vehicle] = []
    for key in _backend().list_keys("vehicles/"):
        if not key.endswith("/vehicle.json"):
            continue
        vehicle = get_vehicle(key.split("/")[1])
        if vehicle is not None:
            records.append(vehicle)
    records.sort(key=lambda v: v.created_at, reverse=True)
    return records


def get_vehicle(vehicle_id: str) -> Vehicle | None:
    """Return one vehicle by id, or None when unknown."""
    key = _vehicle_key(vehicle_id)
    if not _backend().exists(key):
        return None
    try:
        return Vehicle.model_validate_json(_backend().read_text(key))
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
    """Remove a vehicle and its files, or return False when unknown."""
    if get_vehicle(vehicle_id) is None:
        return False
    _backend().delete_prefix(f"vehicles/{vehicle_id}/")
    return True
