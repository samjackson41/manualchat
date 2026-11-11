"""Round-trip and rejection tests for export and import (DEPLOYMENT M2)."""

import io
import json
import uuid
import zipfile

import pytest
from fastapi.testclient import TestClient

from backend import export, retrieval, storage
from backend.api.main import app
from backend.config import get_settings

DIM = 768


@pytest.fixture(autouse=True)
def _fresh_settings(tmp_path, monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("MANUALS_DIR", str(tmp_path / "manuals"))
    monkeypatch.setenv("VEHICLES_DIR", str(tmp_path / "vehicles"))
    monkeypatch.setenv("QDRANT_PATH", ":memory:")
    monkeypatch.setenv("QDRANT_URL", "")
    monkeypatch.setenv("QDRANT_COLLECTION", f"test_import_{uuid.uuid4().hex}")
    monkeypatch.setenv("RETRIEVAL_EMBED_DIM", str(DIM))
    get_settings.cache_clear()


def _fake_embed(texts):
    return [[float(i + 1)] * DIM for i in range(len(texts))]


def _fake_rerank(query, candidates, top_n):
    return candidates[:top_n]


def _pdf_bytes():
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "The oil drain bolt torque is 30 Nm.", fontsize=11)
    data = doc.tobytes(garbage=0)
    doc.close()
    return data


def _indexed_manual_id():
    vehicle = storage.store_vehicle("Demo vehicle")
    manual = storage.store_manual(
        source_pdf=_pdf_bytes(),
        vehicle_id=vehicle.vehicle_id,
        display_name="Demo manual",
        source_filename="demo.pdf",
    )
    manual_dir = storage.manual_dir(manual.manual_id)
    page_dir = manual_dir / "page_text"
    page_dir.mkdir(parents=True, exist_ok=True)
    (page_dir / "page_0001.txt").write_text("The oil drain bolt torque is 30 Nm.")
    (manual_dir / "tables.json").write_text("[]")
    storage.update_manual(manual.manual_id, page_count=1)
    retrieval.index_manual(manual.manual_id, embed=_fake_embed)
    return manual.manual_id


def _export_zip(tmp_path, manual_id):
    out = tmp_path / "manual.zip"
    export.export_manual(manual_id, out)
    return out.read_bytes()


def _post_import(client, vehicle_id, zip_bytes):
    return client.post(
        "/manuals/import",
        data={"vehicle_id": vehicle_id},
        files={"file": ("manual.zip", zip_bytes, "application/zip")},
    )


def _rewrite_manifest(zip_bytes, **changes):
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as src, zipfile.ZipFile(buf, "w") as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "manifest.json":
                manifest = json.loads(data)
                manifest.update(changes)
                data = json.dumps(manifest).encode()
            dst.writestr(item, data)
    return buf.getvalue()


def test_round_trip_imports_and_serves(tmp_path):
    client = TestClient(app)
    zip_bytes = _export_zip(tmp_path, _indexed_manual_id())

    target = storage.store_vehicle("Serving vehicle")
    resp = _post_import(client, target.vehicle_id, zip_bytes)
    assert resp.status_code == 200, resp.text
    imported = resp.json()
    assert imported["status"] == "ready"
    assert imported["page_count"] == 1
    assert imported["chunk_count"] == 1

    stored = storage.get_manual(imported["manual_id"])
    assert stored.vehicle_id == target.vehicle_id
    assert storage.read_manual_text(imported["manual_id"], "page_text/page_0001.txt") == (
        "The oil drain bolt torque is 30 Nm."
    )

    chunks = retrieval.search(
        "oil drain bolt",
        target.vehicle_id,
        top_n=5,
        embed=_fake_embed,
        rerank=_fake_rerank,
    )
    assert len(chunks) == 1
    assert chunks[0].vehicle_id == target.vehicle_id
    assert chunks[0].manual_id == imported["manual_id"]


def test_import_unknown_vehicle_returns_404():
    client = TestClient(app)
    resp = _post_import(client, "no-such-vehicle", b"x")
    assert resp.status_code == 404


def test_import_rejects_a_non_zip():
    client = TestClient(app)
    vehicle = storage.store_vehicle("V")
    assert _post_import(client, vehicle.vehicle_id, b"not a zip").status_code == 400


def test_import_rejects_wrong_embed_model(tmp_path):
    client = TestClient(app)
    vehicle = storage.store_vehicle("V")
    zip_bytes = _export_zip(tmp_path, _indexed_manual_id())
    resp = _post_import(client, vehicle.vehicle_id, _rewrite_manifest(zip_bytes, embed_model="other/model"))
    assert resp.status_code == 400


def test_import_rejects_wrong_vector_dim(tmp_path):
    client = TestClient(app)
    vehicle = storage.store_vehicle("V")
    zip_bytes = _export_zip(tmp_path, _indexed_manual_id())
    resp = _post_import(client, vehicle.vehicle_id, _rewrite_manifest(zip_bytes, vector_dim=123))
    assert resp.status_code == 400


def test_import_rejects_hash_mismatch(tmp_path):
    client = TestClient(app)
    vehicle = storage.store_vehicle("V")
    zip_bytes = _export_zip(tmp_path, _indexed_manual_id())

    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as src, zipfile.ZipFile(buf, "w") as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "tables.json":
                data = b"[{}]"
            dst.writestr(item, data)
    assert _post_import(client, vehicle.vehicle_id, buf.getvalue()).status_code == 400
