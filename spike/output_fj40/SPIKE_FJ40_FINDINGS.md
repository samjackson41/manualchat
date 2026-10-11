# SPIKE FINDINGS — Scanned/Diagram-Heavy Manual Feasibility (FJ40)

**Manual:** `/home/sam/dev/aie-capstone/manuals/fj40manual.pdf` (412 pages)
**Runtime:** `/home/sam/dev/aie-cohort-202609/.venv/bin/python`
**Output:** `/home/sam/dev/aie-capstone/spike/output_fj40/`
**Script:** `/home/sam/dev/aie-capstone/spike/docling_probe_fj40.py`

> **STATUS / page-number caveat:** the numbers below come from a 43-page sample run that
> had a one-off bug in page attribution (docling's `prov[].page_no` is 1-based, I first
> treated it as 0-based, so within each 4-page batch the page *labels* shifted by one and
> the last page collapsed to `-1`). The text content and every qualitative conclusion are
> unaffected; only the exact page numbers attached to specific excerpts may be off by one.
> A corrected **full 412-page run** (`run_ocr_full.sh`, `force_full_page_ocr=True` +
> onnxruntime) was launched overnight and produces authoritative page numbers in
> `docling_summary.json` / `ocr_vs_native.json` / `full_manual.md`.

> **Method note (what actually ran).** The full 412-page OCR run is ~1.5–2.5 hours of CPU.
> To stay memory-safe *and* time-boxed, the numbers below come from a **43-page
> representative sample** (11 batches × 4 pages, fresh subprocess each, each wrapped in
> `systemd-run --user --scope -p MemoryMax=4G` so an over-limit run dies inside its own
> cgroup instead of taking down the desktop). The sample deliberately over-samples
> diagram-heavy pages (to chase the wiring-schematic question), so the text-yield figure
> is a *lower bound* on the full manual. Full-run command + extrapolation are given in Q2.

---

## Q1 — Native text layer check

**Verdict: the manual is 100% scanned — there is no text layer at all.**

Measured with PyMuPDF across all 412 pages:

| metric | value |
|---|---|
| page count | 412 |
| pages with any extractable text | **0** |
| total native characters | **0** |
| embedded fonts | **[] (none)** |

Every page is a raster image (`page.get_images()` returns 1–9 images/page, 0 vector
drawings). This is *worse* than the Rhino manual, which at least had a (corrupting)
hidden `HiddenHorzOCR` text layer. Here there is nothing to fall back on — every single
character must come from OCR.

---

## Q2 — Docling OCR output

### Engine
Docling used **RapidOCR**, and only because I explicitly configured it. The default
`OcrAutoOptions` fallback chain is: `onnxruntime` (not installed at start) → `easyocr`
(not installed) → `torch` (installed). I first measured the **torch** backend and it ran
~150 s/page (CPU torch OCR is unviable); I then `uv pip install`-ed `onnxruntime` and
switched to `RapidOcrOptions(lang=["english"], backend="onnxruntime")`, which brought it
to ~22 s/page.

> ⚠️ **Config quirk worth flagging:** even with `lang=["english"]`, RapidOCR loaded the
> **Chinese** PP-OCRv4 weights (`ch_PP-OCRv4_det_mobile.onnx`, `ch_PP-OCRv4_rec_mobile.onnx`).
> This almost certainly drives the full-width CJK punctuation artifacts (，、一) seen
> throughout the output. Fixing the language mapping (or pinning the `en_*` models) would
> likely clean up a meaningful fraction of the noise.

### Timing & memory (measured)

| metric | value |
|---|---|
| wall-clock (43-page sample) | 964 s (~16 min) |
| ~per page | ~22 s |
| peak RSS | **1.97 GB** |
| extrapolated full 412 pages | ~9,000 s ≈ **2.6 hours** |

Peak RSS was ~2 GB, not the ~6 GB the Rhino spike feared — because the torch layout/table
models load leaner here and TableFormer is in FAST mode. Memory is *not* the constraint;
**CPU time is**.

### Text yield — the headline finding

Only **19 of 43 sampled pages (44%) produced any text at all** with default settings
(`force_full_page_ocr=False`). The other 24 pages came back as a single `picture` item
with zero characters. The cause is Docling's layout model: on a scanned page that is
mostly a diagram/exploded-view, it classifies the whole page as one "picture" and **never
runs OCR inside the picture region**, so callout labels, part numbers, and figure captions
are silently dropped.

I verified the fix on one zero-text page (p.6, which is actually the **table of contents**):

| setting | p.6 result |
|---|---|
| `force_full_page_ocr=False` (default) | 0 chars, `{'picture': 1}` |
| `force_full_page_ocr=True` | recovers "GENERAL REPAIR INSTRUCTIONS 1-2", "SYMBOL MARKS 1-4" |

So the gap is **not "OCR can't read it" — it's "Docling doesn't try by default."**
`force_full_page_ocr=True` would raise coverage toward ~100% but at higher cost and with
more noise.

### Fidelity (spot-check pages in `page_text/`)

OCR text is *recognizable English* but systematically corrupted. The dominant error is
**missing inter-word spaces** (RapidOCR's det+rec emits glyph runs, not words), plus
full-width punctuation and occasional misreads.

- `page_text/page_034.md` (clutch-cover assembly, diagram + callouts):
  `"Assemblethepartsin thenumberedordershown in the figure."`, `"Using SST[09301-55022]…"`
- `page_text/page_284.md` (windshield/weatherstrip removal, text-heavy):
  `"Removethemouldingwithascrewdriver or similartool."`
- `page_text/page_333.md` (light/dimmer switch — electrical, closest to a schematic):
  `"TB....To fuse(tail)15A… HL... Toheadlightlowbeam…"` — the terminal-connection semantics
  *are* recoverable as text here.

Full per-page text: `full_manual.md`; per-page char counts: `ocr_vs_native.json`.

---

## Q3 — Table recovery

**14 tables recovered** across the 43-page sample (`tables/_index.json` + `tables/*.txt`).
This is the strongest positive result of the spike — Docling's table-structure model
(TableFormer-FAST) *does* reconstruct real tables from scanned pages, because table
regions get dedicated OCR treatment.

**Best tables** — real columns, numbers, units:

- `table_007` (p.374) — **torque spec table**, 8×9, headers `Location | kg-m (ft-lb) ×7`,
  e.g. `"Transmission Case X Transmission Case Cover (For 4-Speed)  3.0-4.5 (21.7-32.6)"`.
- `table_008`/`009`/`010` (p.374) — more torque tables (differential, rear axle, steering),
  e.g. `"Drive Pinion X Flange X Nut  20-24 (144-173)"`.
- `table_002` (p.66) — bearing **size-mark → thickness** table, `"2.40-2.45 (0.0945-0.0965)"`.
- `table_005` (p.335) — coolant-temperature-sensor **resistance** table, `"60°C  90 Ω app."`.
- `table_000` + `table_001` — the **table of contents** (`"CLUTCH 2 / TRANSMISSION & TRANSFER 3 / …"`),
  recovered with section names and page numbers.

**Worst tables** — the electrical switch-position matrices (`table_003`/`004`, p.332) came
out hollow: headers like `"TERMINAL SWITCH POSITION TB TL PL HB HD"` survived, but the
●/○ cell markers were dropped or turned into stray letters (`"Q"`), so the grid is
unreadable without the original image.

**Judgement:** where the manual uses *real tables* (torque specs, tolerances, parts lists,
TOC), recovery is genuinely usable for retrieval. Where information is encoded in
*spatial diagrams* (switch matrices, connection grids), it does not survive.

---

## Q4 — PyMuPDF/Tesseract direct OCR comparison

**Not runnable on this box:** the `tesseract` binary is not installed and `pytesseract`
is missing, so both `pymupdf.Page.get_text("ocr")` and the Tesseract CLI path fail
(recorded in `q4_direct_ocr.json`). Installing needs `sudo apt-get install tesseract-ocr`.

The only *alternative* OCR engine available (RapidOCR standalone) is the same engine
Docling uses internally, so a side-by-side would not be an independent comparison. The
meaningful Q4 question — "does a direct per-page OCR beat Docling's layout-gated OCR" —
is partially answered already by the Q2 `force_full_page_ocr` experiment: **direct
full-page OCR recovers text that Docling's default pipeline silently drops.** A Tesseract
comparison is a cheap follow-up for the user to run (`sudo apt-get install tesseract-ocr`
then the command in `scanned_ocr_probe_prompt.md`).

---

## Q5 — Diagram/text ratio & uncapturable content

Pixel/connected-component classification (100 dpi, `scipy.ndimage`) of all 412 pages
(`page_classification.json`):

| category | pages | % |
|---|---|---|
| diagram_heavy | 208 | 50% |
| text_heavy | 116 | 28% |
| mixed | 88 | 21% |
| wiring_schematic | **0** | 0% |

**Caveat:** this is a heuristic on ink/line/glyph statistics, *not* visually verified (the
spike's runtime cannot view rasters). It confidently separates "many small glyphs" (text)
from "large connected blobs" (exploded parts), but the wiring-schematic rule (many long
horizontal + vertical lines) matched **zero** pages. Two interpretations, both honest:

1. This FJ40 manual has no classic grid-style wiring diagrams (the "wiring" content may be
   photos/drawings, not line schematics), or
2. the schematic lines are too thin/anti-aliased to register as long runs at 100 dpi.

Supporting evidence for (1): the *electrical* content that OCR did recover (p.333 light/
dimmer switch) is a **textual terminal-connection list** ("TB → fuse(tail)15A, HL → low
beam…"), not a line drawing. So even where the manual is "wiring", it is partly word-encoded.

**The structural gap:** for `diagram_heavy` pages (≈50% of the manual), the relationships
— which callout number points at which part, the spatial ordering of an exploded view —
live in **lines and geometry**, not text. OCR captures the labels but discards the
connections. Callout recovery rate is therefore only partial: labels near text are captured
(e.g. `"Fig. 2-33"`, `"SST[09301-55022]"`), but the numbering *arrows* and part
*positioning* are lost.

---

## Q6 — Retrieval pipeline feasibility verdict

**Chunk quality.** With Docling defaults, only **~44% of pages yield any text**, and the
text that exists is corrupted at ~1 error per 3–5 words (missing spaces + CJK punctuation).
So *without* `force_full_page_ocr=True`, roughly **half the corpus would be empty chunks**
and the rest would be low-quality embeddings. With `force_full_page_ocr=True`, coverage
rises toward ~100% but the chunks remain noisy and diagram pages still lack the
*relationships*.

**Realistic repair query.** Take *"What is the torque of the differential ring gear bolt?"*.
A vector search over this corpus *would* plausibly hit `table_008` (p.374), which OCR
recovered as `"Differential Case X Ring Gear  10.5-12.0 (75.9-86.8)"`. So a factual,
table-encoded answer **is retrievable** — but only because (a) it happens to live in a real
table that TableFormer captured, and (b) the embedding tolerates the spacing corruption.
A query whose answer lives on a `diagram_heavy` page (e.g. *"how does the shift fork
assemble?"*) would return the page's caption text at best, not the exploded-view semantics.

**Structurally uncapturable by OCR alone** (would need a vision model or human annotation):

1. **Wiring/electrical connectivity** — which terminal connects to which wire/load.
2. **Exploded-part spatial positioning & callout arrows** — which numbered part goes where.
3. **Switch/position matrices** — ●/○ grid states (headers survive, cells don't).
4. **Multi-page figure relationships** — "install in the numbered order shown in Fig. 2-30"
   refers to a drawing whose ordering is geometric.

---

## Verdict

OCR-only extraction is **not sufficient on its own** to build a retrieval pipeline against
this FJ40 manual — but it is a necessary and useful *first layer*. Concretely: the manual is
100% scanned (Q1), so OCR is the only text source; RapidOCR via onnxruntime produces
recognizable-but-corrupted English at ~22 s/page / ~2 GB peak (Q2), and Docling's table model
genuinely recovers the torque/spec/TOC tables (Q3) that carry much of the answerable
factual content. The blockers are (1) Docling's default `force_full_page_ocr=False` silently
drops ~half the pages, fixable with a config flag at higher cost; (2) systematic spacing/
punctuation corruption, partly a language-model misconfiguration; and (3) the ~50% of the
manual whose information is geometric (exploded views, wiring, matrices), which **no OCR
can capture**. Recommended path: OCR everything with `force_full_page_ocr=True` + the
correct `en_*` RapidOCR models as a **text/table retrieval layer**, and treat diagram pages
as a **separate vision-model track** (GPT-4V/Claude/Qwen-VL) for the callout-to-part and
connectivity semantics — i.e. the "separate preprocessing path" that the brainstorming doc
already suspected was necessary.

