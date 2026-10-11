# Spike Prompt: Scanned/Diagram-Heavy Manual Feasibility (FJ40)

**Manual under test:** `/home/sam/dev/aie-capstone/manuals/fj40manual.pdf`
**Runtime:** `/home/sam/dev/aie-cohort-202609/.venv/bin/python`
**Output directory:** `/home/sam/dev/aie-capstone/spike/output_fj40/`

## Context

The first spike (Rhino 700 FI, 503-page born-digital manual) proved that Docling with
`do_ocr=False` extracts text, tables, and page numbers well enough to anchor a retrieval
pipeline — with two caveats: the document had a hidden OCR text layer that introduced
character corruption, and Docling's TOC/document-index came back empty.

This spike targets the **hard case** — a 412-page Toyota Land Cruiser FJ40 factory manual
that is **entirely scanned** (every page is a raster image), with dense mechanical
diagrams, exploded parts views, wiring schematics, callouts, and annotation text. This is
the manual that was explicitly deferred to "MVP+1" in the brainstorming doc (§6 Q3, §7
item 2), with the open question: *"the result decides whether scanned manuals are a
realistic MVP+1 story or need a separate preprocessing path."*

This spike is purely for **exploration and feasibility**. The user expects OCR-only tools
will likely fall short, and that heavy dependence on an LLM vision model (GPT-4V /
Claude-Vision / Qwen-VL) might be the only viable path for this class of manual. But
**vision models are out of scope for this spike** — run the experiments with PDF/OCR
tools only, then characterize *where* and *how much* the gap is, so the vision-model
discussion has data behind it instead of speculation.

---

## Questions to Answer (by measurement, not opinion)

For each question, the answer must cite specific numeric evidence or a concrete
side-by-side example from the output artifacts.

### Q1 — Is there ANY extractable text layer?

Use PyMuPDF to check whether the PDF contains embedded fonts or text objects (even if
hidden), or whether every page is purely a raster image.

- For each page: report character count from `page.get_text()`.
- Report the font list extracted by PyMuPDF.
- If any page returns text, is it real content or OCR garbage (like the Rhino's
  `HiddenHorzOCR`)?

### Q2 — What does Docling with `do_ocr=True` actually produce?

Run Docling on the full 412 pages with OCR enabled. Because the OOM risk is high (see
Configuration Notes for the chunked strategy), run it in batches and measure:

- Wall-clock time and peak RSS memory.
- Extracted page count vs. ground truth.
- Per-page character counts (compare against Q1's pre-OCR numbers — what *new* text did
  OCR add?).
- Spot-check text fidelity on 3 pages chosen by a human: a text-heavy instruction page,
  a diagram-heavy page with callouts, and a wiring-schematic page. Write the extracted
  markdown to `output_fj40/page_text/page_NNN.md` for human inspection.
- Report the OCR engine Docling selected (RapidOCR vs EasyOCR vs fallback).

### Q3 — Can Docling recover ANY tables from a scanned page?

- Count and list all `TableItem` objects produced.
- Export each to a DataFrame/text file in `output_fj40/tables/`.
- For the best-looking table: does it have recognizable columns, numbers, and units?
- For the worst-looking table: what went wrong? (merged cells interpreted as rows,
  diagram callouts mangled, empty?)

### Q4 — Can PyMuPDF/Tesseract direct OCR outperform Docling's built-in OCR?

If Docling's OCR output is poor, run a side-by-side on the *same* 3 pages:

- Use `pymupdf.Page.get_textpage_ocr()` or `pymupdf.Page.get_text("ocr")` to extract
  text directly (PyMuPDF bundles Tesseract).
- Optionally call Tesseract CLI (`tesseract page_NNN.png stdout`) if installed.
- For each page, report character count and compare a few representative sentences
  against Docling's output side by side in the findings.

### Q5 — What is the diagram-to-text ratio, and what is uncapturable?

- Use PyMuPDF to count images/drawings per page.
- Classify each page into one of: `text_heavy`, `diagram_heavy`, `wiring_schematic`,
  `mixed`.
- For `wiring_schematic` pages: note that even if OCR works perfectly, the *relationships*
  (what connects to what) are encoded in lines and spatial layout, not text. Estimate how
  many pages are schematics where text alone is meaningless.
- For `diagram_heavy` pages with callouts: check whether the callout numbers/labels (e.g.,
  "① Cover gasket") are captured by OCR.

### Q6 — If you tried to build a *retrieval pipeline* from this output, what would fail?

This is the synthesis question. Given everything measured above:

- What percentage of chunks would contain recognizable, searchable English text?
- Can you construct a single realistic repair query (e.g., "What is the torque of the
  cylinder head bolt?") and show what vector search would return from this corpus?
- Which information classes from the manual are *structurally uncapturable* by OCR alone
  (wiring connectivity, exploded-part positioning, spatial callout lines)?

---

## Configuration Notes

For Docling, use OCR-enabled but otherwise memory-safe settings. **The 412-page count
makes OOM a certainty if run in one shot** — Docling eager-loads layout, table, AND
RapidOCR models (~6 GB RSS) before touching a single page, which is what OOM-killed
the Rhino spike with `do_ocr=True`. Every batch must run in a fresh subprocess.

### Memory-Safe Chunked OCR Strategy

Process the manual in **batches of 4-5 pages**, each in a fresh subprocess, so the
OCR model is loaded and then fully released between batches. This keeps peak RSS
under the machine limit and mirrors the approach that succeeded in the Rhino spike
(which ran a 42-page subset with `do_ocr=False`).

```python
# Pseudocode for the chunked runner — build this into docling_probe_fj40.py
BATCH_SIZE = 4
for batch_start in range(0, total_pages, BATCH_SIZE):
    batch_end = min(batch_start + BATCH_SIZE, total_pages)
    # 1. Use pypdf to slice a _subset_fj40_batch_N.pdf with pages [start:end]
    # 2. Run DocumentConverter(do_ocr=True, ...) on that subset
    # 3. Accumulate results: items, tables, heading metadata, per-page text
    # 4. Delete the subset PDF and gc.collect() before the next batch
```

If even a 4-page batch with `do_ocr=True` OOMs, try batch size 2. If that still
fails, the OCR model footprint is too large for this machine and the fallback is
to pre-rasterize pages with PyMuPDF, write PNGs to disk, and run Tesseract CLI
directly on them (one page at a time, zero model overhead between pages). Document
which path was used and why.

### Docling Pipeline Config (per batch)

```python
PIPELINE_OPTIONS = dict(
    do_ocr=True,                    # THIS is the key difference vs the Rhino spike
    do_table_structure=True,
    table_structure_options=TableStructureOptions(mode=TableFormerMode.FAST),
    layout_batch_size=1,
    table_batch_size=1,
    ocr_batch_size=1,
    accelerator_options=AcceleratorOptions(num_threads=2),
)
```

Before running, free as much RAM as possible: close browser tabs, stop Qdrant/Redis
Docker containers, and run `sync && echo 3 | sudo tee /proc/sys/vm/drop_caches`
(if you have sudo). Start a fresh terminal with no cohort venv already imported.

---

## Output Artifacts to Produce

All output goes to `/home/sam/dev/aie-capstone/spike/output_fj40/`:

- `docling_summary.json` — aggregate numbers: pages, tables, headings, timing, peak RSS
- `ocr_vs_native.json` — per-page text-length comparison Q1 vs Q2
- `page_classification.json` — per-page category + image/drawing counts (Q5)
- `page_text/page_NNN.md` — extracted text for 3+ human-spot-checked pages
- `tables/_index.json` + `tables/table_NNN_page_NN.txt` — all recovered tables
- `full_manual.md` — Docling's full markdown export of the entire document
- `SPIKE_FJ40_FINDINGS.md` — the human-readable findings report (see format below)

---

## Findings Report Format

Write the findings to `SPIKE_FJ40_FINDINGS.md` with this structure:

```
# SPIKE FINDINGS — Scanned/Diagram-Heavy Manual Feasibility (FJ40)

## Q1 — Native text layer check
[Evidence: per-page char counts, font list, verdict on born-digital vs scanned]

## Q2 — Docling OCR output
[Evidence: timing, memory, char counts per page, spot-check excerpts with commentary]

## Q3 — Table recovery
[Evidence: table count, best/worst examples pasted inline, judgement on usability]

## Q4 — PyMuPDF/Tesseract direct OCR comparison
[Evidence: side-by-side text excerpts from same pages, count comparison table]

## Q5 — Diagram/text ratio & uncapturable content
[Evidence: page classification table, schematic-page count, callout recovery rate]

## Q6 — Retrieval pipeline feasibility verdict
[Synthesis: chunk quality %, example query + expected retrieval result, gap catalog]

## Verdict
A one-paragraph bottom line: Is OCR-only viable enough to build a retrieval pipeline
against this manual? If not, what class of tool (vision model, manual human annotation,
hybrid) would be needed for each information class that failed?
```

---

## Non-Goals (Explicitly Out of Scope)

- Do **not** send images to a vision model (GPT-4V, Claude, Qwen-VL) — this spike is
  about PDF/OCR tools only.
- Do **not** build a retrieval pipeline or agent — this is pure extraction/feasibility.
- Do **not** do PDF slicing or raster rendering — those are already resolved by the first
  spike.
- Do **not** attempt to "fix" bad OCR output with regex or LLMs — just report what comes
  out raw.

---

## Running the Spike

```bash
cd /home/sam/dev/aie-capstone/spike
mkdir -p output_fj40

# Create and run docling_probe_fj40.py (derived from docling_probe.py,
# adapted for the FJ40 manual path, OCR-on config, and the Q1-Q6 questions above)
/home/sam/dev/aie-cohort-202609/.venv/bin/python \
  /home/sam/dev/aie-capstone/spike/docling_probe_fj40.py

# Tesseract side-by-side (if Tesseract is installed)
python3 -m pip install pytesseract Pillow
python3 -c "
import pymupdf
doc = pymupdf.open('/home/sam/dev/aie-capstone/manuals/fj40manual.pdf')
for i in [3, 9, 14]:
    page = doc[i]
    pix = page.get_pixmap(dpi=300)
    pix.save(f'output_fj40/page_{i+1:03d}.png')
    text = page.get_text('ocr')
    print(f'Page {i+1}: {len(text)} chars via PyMuPDF Tesseract')
    with open(f'output_fj40/page_text/page_{i+1:03d}_tesseract.txt', 'w') as f:
        f.write(text)
"
```

The spike script itself should be a modified copy of `docling_probe.py` (the existing
probe that already has all the measurement scaffolding — timing, RSS, page-count
validation, table dumping, spot-check text export). Change the PDF path, flip `do_ocr`
to `True`, wrap the converter call in the batched subprocess loop described in the
Configuration Notes above, add the extra comparisons for Q4 and Q5, and output to
`output_fj40/` instead of `output/`.