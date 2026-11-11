# Deployment

ManualChat runs two ways. Development runs on one machine. Deployment mirrors
the aie-cohort-202609 project. A stateless Cloud Run service runs the backend.
GCS holds the manual and vehicle files. Qdrant Cloud holds the chunk index.
Secret Manager holds the keys.

The deployment has three milestones. Milestone 1 makes the backend cloud-ready.
Milestone 2 adds the zip import. Milestone 3 adds the online ingest job.

## Architecture

| Part | Service | Purpose |
|---|---|---|
| Compute | Cloud Run | Runs the backend API. Serverless, scales to zero. |
| Files | GCS | Holds `source.pdf`, page text, tables, and the records. |
| Search index | Qdrant Cloud | Holds the embedded chunks, in `us-east-1`. |
| Secrets | Secret Manager | Holds the OpenRouter and Qdrant keys. |
| Frontend | Firebase Hosting | Serves the static Next.js build over HTTPS. |

Cloud Run is Google's serverless container service. GCS is Google Cloud
Storage, the object store. Qdrant Cloud is the hosted vector database.
Secret Manager is the Google Cloud key store.

The Cloud Run service is stateless. No manual, vehicle, or index lives in the
container. The `/health` endpoint checks the connection to GCS and to Qdrant,
the way the aie-cohort `/health` endpoint checks its services.

Ingest is the expensive step. It converts a PDF with Docling and embeds the
chunks. The deployed service omits Docling and torchvision, so it cannot run
ingest. A user ingests on a machine, then imports the result as a zip. A later
milestone moves ingest to a Cloud Run Job.

## Milestone 1: cloud-ready serving

Change the backend to read files from a storage backend, not the local disk.
Add the slim serving image. Make the CORS list a configuration value.

| File | Change |
|---|---|
| `backend/pyproject.toml` | Move `docling` and `torchvision` into the `ingest` dependency group. Add `google-cloud-storage`. Keep `torch` and `sentence-transformers` for query embedding. Regenerate `uv.lock`. |
| `backend/config.py` | Add `storage_backend` (`local` or `gcs`), `gcs_bucket`, and `cors_origins`. |
| `backend/storage.py` | Add a `StorageBackend` protocol. A local backend keeps the path code. A GCS backend uses object keys such as `manuals/{id}/source.pdf`. Keep the public function names. |
| `backend/slicer.py` | Read `source.pdf` from the storage backend. PyMuPDF opens a byte stream. |
| `backend/thumbnails.py` | Read `source.pdf` from the storage backend. |
| `backend/tools.py` | Read `tables.json` and `page_text/` from the storage backend. |
| `backend/retrieval.py` | Read the pages and tables from the storage backend. |
| `backend/ingest.py` | Write the ingest output through the storage backend. |
| `backend/api/main.py` | Build the CORS list from `cors_origins`. Extend `/health` to check GCS and Qdrant. |
| `backend/Dockerfile` | New slim serving image. Multi-stage, non-root, uvicorn on `$PORT`. |
| `backend/Dockerfile.dev` | The current image, renamed. Docker Compose uses it for development. |
| `docker-compose.yml` | Point the backend at `Dockerfile.dev`. |

## Milestone 2: zip import

Add an export step and an import endpoint. The export step packages a processed
manual. The import endpoint checks the zip and loads it without re-embedding.

| File | Change |
|---|---|
| `backend/export.py` | New. `python -m backend.export_manual <id>` writes the zip. The zip holds `manual.json`, `ingest.json`, `source.pdf`, `page_text/`, `tables.json`, `chunks.json`, `vectors.npz`, and `manifest.json`. |
| `backend/retrieval.py` | Add `upsert_vectors`. It stores the uploaded vectors without embedding. |
| `backend/api/main.py` | Add `POST /manuals/import`. The endpoint checks the manifest, then stores the files and upserts the vectors. |
| `backend/schemas.py` | Add the manifest model. |
| `backend/tests/` | A round-trip test with the local backend. A rejection test for a bad zip. |

The manifest records a SHA-256 for each file, the page count, the chunk count,
and the vector dimension. The server refuses a zip whose vectors do not match
the chunks, whose dimension is not 768, or whose PDF does not open.

## Milestone 3: online ingest job

Move ingest to a Cloud Run Job. The job runs the local pipeline and writes the
same zip to GCS. The serving service then loads the zip. This milestone is
optional and deferred.

| File | Change |
|---|---|
| `backend/Dockerfile.ingest` | New. The full dependency set, with an ingest entrypoint. |
| Cloud Run Job | Runs the job on demand or on a schedule. |

## Runbook

Follow these steps in order. Steps 1 to 3 are one-time setup. Step 4 and later
deploy the services.

1. Sign in to Google Cloud. Pick or create the project. Attach the free-trial
   billing account.
2. Enable the APIs: `run`, `cloudbuild`, `artifactregistry`, `secretmanager`,
   `storage`, and `iamcredentials`.
3. Create a deploy service account. Grant it `Cloud Run Admin`, `Storage Admin`,
   `Secret Manager Secret Accessor`, `Artifact Registry Writer`, and
   `Cloud Build Editor`.
4. Create the GCS bucket `manualchat-data`. Keep it private. The service account
   alone holds access.
5. Create a Qdrant Cloud cluster in `us-east-1` on the free tier. Record the URL
   and the API key. Self-hosting on a GCE VM is the fallback if the free tier
   caps out.
6. In Secret Manager, create `openrouter-api-key` and `qdrant-api-key`.
7. From `manualchat/`, run:

   ```bash
   gcloud run deploy manualchat-api \
     --source backend \
     --region us-east1 \
     --memory 1Gi \
     --timeout 300 \
     --service-account <deploy-sa> \
     --update-secrets "OPENROUTER_API_KEY=openrouter-api-key:latest,QDRANT_API_KEY=qdrant-api-key:latest" \
     --set-env-vars "STORAGE_BACKEND=gcs,GCS_BUCKET=manualchat-data,QDRANT_URL=<url>,CORS_ORIGINS=<frontend-origin>"
   ```

8. Make sure that `GET /health` returns `{"status":"ok"}` and that it reports
   the GCS and Qdrant checks as healthy.
9. Build the frontend with `NEXT_PUBLIC_BACKEND_URL` set to the Cloud Run URL.
   Publish the static output to Firebase Hosting.
10. Restrict access with Identity-Aware Proxy and an email allowlist. The app
    must not be open to the public, so gate both the API and the frontend
    origin. Set an OpenRouter spending cap.
11. To load a manual, run `python -m backend.export_manual <id>` on the machine
    that ingested it, then upload the zip through `POST /manuals/import`.

## Ratified deployment decisions

- Qdrant: the Qdrant Cloud free tier in `us-east-1`. Self-host on a GCE VM only
  if the tier caps out.
- Access: Identity-Aware Proxy with an email allowlist, on both the API and the
  frontend origin. There is no shared API key in the bundle.
- Embedding model: the export machine and the service pin the same
  `RETRIEVAL_EMBED_MODEL`. The manifest records the model and its revision, and
  the import refuses a mismatch.
