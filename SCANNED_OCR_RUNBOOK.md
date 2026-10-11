# SCANNED-OCR RUNBOOK — ManualChat MVP+1 (Scanned/Legacy Manual Ingestion)

> **Purpose.** This document captures the *verified* recipe for OCR-ing a fully-scanned
> service manual (the FJ40 Land Cruiser case) so it can be automated as part of the
> document-upload pipeline for adding new vehicles/manuals. It maps directly to the
> MVP+1 requirement in `SPECIFICATION.md` (§ "Scanned & Legacy Document OCR") and the
> branch in `IMPLEMENTATION.md` §2.2 where the MVP currently hardcodes `do_ocr=False`.
>
> **Source of truth tested here:** the 412-page Toyota FJ40 factory manual
> (`manuals/fj40manual.pdf`) — a worst-case, **100% raster** manual with dense exploded
> diagrams, spec tables, and electrical callouts. Results below are measured, not
> estimated.

---

## 1. When this applies (born-digital vs. scanned)

The MVP ingestion path (`do_ocr=False`) is correct **only** for born-digital PDFs that
carry a native text layer. A scanned manual has **no text layer at all** — every page is
a raster image — so `do_ocr=False` returns an empty document.

**Detection gate (runs before any conversion, cheap):**

```python
import pymupdf
d = pymupdf.open(pdf_path)
native_text = sum(len(d[i].get_text().strip()) for i in range(d.page_count))
if native_text == 0:
    # scanned -> take the OCR path below
else:
    # born-digital -> existing do_ocr=False path
```

The FJ40 measured `native_text == 0` on all 412 pages, zero embedded fonts — a clean
thumbs-down on the text-layer check.

---

## 2. The verified OCR recipe

### 2.1 Dependencies (all in `aie-cohort-202609/.venv`)

| package | needed? | note |
|---|---|---|
| `docling` (2.102.x) | yes | layout + table-structure + OCR orchestration |
| `onnxruntime` | **yes — install explicitly** | was missing; without it RapidOCR falls back to the ~10× slower torch backend |
| `rapidocr` | yes | the OCR engine Docling drives |
| `pymupdf`, `pypdf` | yes | page check, slicing |
| `torch` (CPU) | yes | layout/table model runtime |
| `tesseract` | optional | **not installed** — the PyMuPDF/Tesseract direct-OCR comparison (Q4) could not run |

Install the one missing piece:

```bash
uv pip install --python /home/sam/dev/aie-cohort-202609/.venv/bin/python onnxruntime
```

### 2.2 Pipeline config (the non-obvious parts)

```python
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions, RapidOcrOptions, TableFormerMode, TableStructureOptions, AcceleratorOptions,
)
ocr_options = RapidOcrOptions(
    lang=["english"],
    backend="onnxruntime",        # NOT the default; torch backend is ~10x slower
    force_full_page_ocr=True,     # CRITICAL — see gotcha G1
)
options = PdfPipelineOptions(
    do_ocr=True,
    do_table_structure=True,
    table_structure_options=TableStructureOptions(mode=TableFormerMode.FAST),
    ocr_options=ocr_options,
    layout_batch_size=1, table_batch_size=1, ocr_batch_size=1,
    accelerator_options=AcceleratorOptions(num_threads=8),
)
```

### 2.3 Memory-safe chunked execution

Peak RSS is **~2.3 GB and flat** (dominated by model weights, not page count), so this is
about process isolation, not RAM scarcity. Run in **40-page batches**, each in a fresh
subprocess wrapped in a systemd memory ceiling so an over-limit run dies inside its own
cgroup instead of triggering the global OOM killer:

```bash
# per batch: slice 40 pages with pypdf, then:
systemd-run --user --scope -p MemoryMax=4G --collect --quiet \
  /home/sam/dev/aie-cohort-202609/.venv/bin/python docling_probe_fj40.py \
    --phase batch --page-map "0,1,...,39" --pdf subset.pdf
```

Reference implementation: `spike/docling_probe_fj40.py` (phases `q1`/`q5`/`ocr`/`batch`/`q4`)
and `spike/run_ocr_full.sh` (the full-manual launcher).

### 2.4 One-shot command (full manual)

```bash
cd /home/sam/dev/aie-capstone/spike
DOCLING_THREADS=8 ./run_ocr_full.sh      # logs to output_fj40/ocr_full.log
```

---

## 3. Measured results (FJ40, 412 pages)

| metric | value |
|---|---|
| wall-clock | **35.6 min** (11 × 40-page batches) |
| peak RSS | **2.278 GB** (under the 4 GB guard) |
| batch failures | **0 / 11** |
| pages with OCR text | **253 / 412 (61%)** |
| char count / page | median 187, max 1582 (short = captions/callouts) |
| tables recovered | **92** (incl. clean TOC, torque specs, tolerances) |
| headings / text items / captions | 444 / 851 / 423 |
| full markdown | 203,730 chars → `full_manual.md` |

Pages with **zero** text (159, i.e. 39%) are overwhelmingly `diagram_heavy` (91) — pure
exploded-view drawings with no glyphs for OCR to find. This is the boundary where OCR
ends and a vision model must take over (§6).

---

## 4. Critical gotchas (tribal knowledge — do not rediscover)

**G1 — `force_full_page_ocr=True` is mandatory for scanned manuals.** With the default
(`False`), Docling's layout model classifies a whole diagram page as a single `picture`
and never OCRs inside it, silently dropping ~44% of pages. Measured: p.6 (the TOC) gave
`0 chars, {'picture': 1}` by default but recovered `"GENERAL REPAIR INSTRUCTIONS 1-2…"`
with the flag on.

**G2 — OCR backend matters 10×.** Default `OcrAutoOptions` picks `torch` here (no
onnxruntime installed), which ran ~150 s/page. `backend="onnxruntime"` brought it to
~10 s/page. Always install `onnxruntime` first.

**G3 — RapidOCR ignores `lang=["english"]`.** It loaded the **Chinese** PP-OCRv4 weights
(`ch_PP-OCRv4_rec_mobile.onnx`) despite `lang=["english"]`, because Docling's
`artifacts_path` was never populated with the `en_*` models, so RapidOCR fell back to its
bundled Chinese defaults. Consequence: **full-width CJK punctuation artifacts (，、一)**
scattered through the otherwise-readable English. *TODO before QA:* pin/download the
`en_*` models. (Not fatal for retrieval — embeddings tolerate it.)

**G4 — `prov[].page_no` is 1-based.** Treating it as 0-based (a natural mistake) shifts
every page label by one and collapses the last page of each batch to `-1`. Map with
`page_map[page_no - 1]`.

**G5 — memory is flat vs. page count.** 1.9 GB (4 pages) → 2.28 GB (40 pages). The cost
is model weights, not pages. So chunking is about isolation/recoverability, not headroom —
and full-document single-process runs are *not* safe on a 3 GB-free box.

**G6 — OCR output is recognizable but corrupted.** Missing inter-word spaces
(`"Assemblethepartsin thenumberedorder"`) is the dominant error, plus the G3 punctuation.
Tolerable for bi-encoder retrieval; not clean prose.

---

## 5. Mapping to the MVP+1 upload pipeline

The existing ingestion flow (`IMPLEMENTATION.md` §2.2) is:

```
PDF Upload → PyMuPDF page check → Docling(do_ocr=False) → Text/Unit Normalizer
           → Chunk Generator → Embedder → Qdrant ... → Slice & Thumbnail worker
```

MVP+1 inserts a **routing branch** right after the page check:

```
PyMuPDF page check
   ├─ native text layer present → Docling(do_ocr=False)      [unchanged MVP path]
   └─ native text layer EMPTY    → S C A N N E D   P A T H
        ├─ Docling(do_ocr=True, force_full_page_ocr=True, onnxruntime, FAST)   (§2)
        ├─ per-page text + TableItems → same Text Normalizer → Chunk → Embed → Qdrant
        └─ diagram-heavy pages (≈39%) → route to a VISION model for callouts/connectivity (§6)
```

Concrete automation tasks:
1. Add the `§1` scanned-detection gate to the upload handler.
2. Factor `§2.2` config + `§2.3` chunked runner into a reusable
   `ocr_manual(pdf) -> DoclingDocument` service (retire the spike script, keep the
   batch/subprocess/guard pattern).
3. Persist the same artifacts — full markdown + `TableItem` DataFrames — into the existing
   chunk/embed/Qdrant pipeline unchanged.
4. Add a per-manual "coverage" metric (pages-with-text / total) to the ingestion progress
   UI, so a 61%-coverage scanned manual is surfaced honestly vs. ~100% born-digital.

---

## 6. What OCR cannot capture (hand off to vision)

Even perfect OCR misses the information that lives in **geometry, not text**:

1. **Exploded-part positioning** — which callout number points at which part.
2. **Wiring/electrical connectivity** — which terminal connects to which wire/load.
3. **Switch/position matrices** — ●/○ grid states (headers survive; cells are dropped).
4. **Figure cross-references** — "install in the numbered order shown in Fig. 2-30"
   refers to a drawing whose ordering is spatial.

These correspond to the 91 `diagram_heavy` zero-text pages (and the sparse callout text on
many more). The MVP+1 vision path should feed those page images to a VLM
(GPT-4V / Claude-Vision / Qwen-VL) to extract captions + part↔label relationships, and
store the result alongside the OCR text so both are searchable.

---

## Verdict

OCR-only is a **necessary but insufficient** ingestion layer for scanned manuals: it
recovers ~61% of pages (all text, all real tables) in ~36 min at ~2.3 GB, cleanly and
crash-safe. The remaining ~39% — the diagram/exploded-view geometry — requires a separate
vision-model step. Both are now characterized with numbers, so the MVP+1 automation can
be scoped precisely instead of speculated about.