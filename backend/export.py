"""Export one processed manual as a self-contained zip for import (DEPLOYMENT M2).

The serving image omits Docling and cannot ingest, so a manual is processed on a
machine that can (the export machine) and its stored files are zipped here, then
imported on the deployed service via `POST /manuals/import`. The zip holds every
stored file plus a manifest that records a SHA-256 per file, the chunk and
vector counts, and the embedding model, so the importer can refuse a corrupt or
mismatched zip.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

from backend import storage
from backend.config import get_settings

# Fixed files the zip carries, under their stored names. Page text files are
# added under `page_text/`.
_FILES = (
    "manual.json",
    "ingest.json",
    "source.pdf",
    "tables.json",
    "chunks.json",
    "vectors.npz",
)


def _stored_files(manual_id: str) -> dict[str, bytes]:
    """Map each stored file name to its bytes, from local storage."""
    manual_dir = storage.manual_dir(manual_id)
    files: dict[str, bytes] = {}
    for name in _FILES:
        path = manual_dir / name
        if path.is_file():
            files[name] = path.read_bytes()
    page_dir = manual_dir / "page_text"
    if page_dir.is_dir():
        for path in sorted(page_dir.glob("page_*.txt")):
            files[f"page_text/{path.name}"] = path.read_bytes()
    return files


def _vector_dim(data: bytes) -> int:
    import numpy as np

    archive = np.load(io.BytesIO(data))
    try:
        return int(archive["vectors"].shape[1])
    finally:
        archive.close()


def export_manual(manual_id: str, out_path: Path) -> Path:
    """Write the zip for one manual and return its path."""
    manual = storage.get_manual(manual_id)
    if manual is None:
        raise LookupError(f"manual not found: {manual_id}")

    files = _stored_files(manual_id)
    if "vectors.npz" not in files:
        raise RuntimeError(f"manual {manual_id} has not been indexed")

    manifest = {
        "manual_id": manual_id,
        "page_count": manual.page_count,
        "chunk_count": manual.chunk_count,
        "vector_dim": _vector_dim(files["vectors.npz"]),
        "embed_model": get_settings().retrieval_embed_model,
        "files": {
            name: hashlib.sha256(data).hexdigest()
            for name, data in sorted(files.items())
        },
    }

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in sorted(files.items()):
            zf.writestr(name, data)
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
    return out_path


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="backend.export",
        description="Export one processed manual as a zip for import.",
    )
    parser.add_argument("manual_id", help="the stored manual's UUID")
    parser.add_argument("out", nargs="?", help="output zip path (default: <manual_id>.zip)")
    args = parser.parse_args(argv)

    out = Path(args.out) if args.out else Path(f"{args.manual_id}.zip")
    try:
        path = export_manual(args.manual_id, out)
    except (LookupError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
