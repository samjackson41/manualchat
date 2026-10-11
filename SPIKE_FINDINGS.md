# SPIKE FINDINGS — docling fidelity (Q6) & PDF slicing vs. raster (Q10)

Manual under test: `2008-2010-Rhino-700Fi-Manual.pdf` — **503 pages, 23 MB**, Yamaha
Rhino 700 FI service manual. Python was the cohort venv
(`/home/sam/dev/aie-cohort-202609/.venv/bin/python`, docling **2.102.2**). Libraries
**added** for this spike: `pymupdf==1.28.2` and `pypdf==6.19.0` (PyMuPDF for
rasterization, pypdf for slicing).

> **Method note (important).** The full 503-page docling run **OOM-killed a 15 GB
> machine** (details below). All Q6 conversion numbers below are therefore measured on a
> **42-page subset** (`spike/output/_subset_q6.pdf`: TOC pp.1-7, Specifications pp.32-56,
> valve-clearance/engine-oil pp.81-90) — the smallest slice that still answers every Q6
> question. Born-digital / 503-page facts were verified against the full file with
> PyMuPDF. Per-page throughput is used to extrapolate the full-manual cost.

---

## Q6 — docling fidelity

### 1. Does it run / what does it cost? (subset, tuned config)
| metric | value |
|---|---|
| config | `do_ocr=False`, `do_table_structure=True`, `TableFormerMode.FAST`, batch=1, threads=2 |
| wall-clock (42 pages) | **335.7 s** (~5.6 min) |
| peak RSS | **2.92 GB** (baseline 562 MB) |
| status | success, end-to-end |

**The default `DocumentConverter()` is a memory hazard on this box.** It eager-loads
OCR (RapidOCR/torch) + layout (DocLayout-Heron) + table-structure models at once and
was **OOM-killed at ~6 GB RSS** (kernel: `Out of memory: Killed process ... (python)`),
twice crashing the desktop. With `do_ocr=False` (correct for a born-digital manual) +
`FAST` table model + batch=1/threads=2, peak fell to **2.9 GB** and completed cleanly.
**Ingestion must pin `do_ocr=False`** for digital manuals; OCR is only for the scanned
stretch-manual path.

### 2. Extracted page count & text layer
- Extracted **42/42 pages** match ground truth (`page_count_matches: true`).
- **Born-digital confirmed.** Every sampled page had 350-2679 chars of real text with
  Arial/Helvetica/Times fonts. Body text extracts cleanly ("General information",
  "Engine oil: …", torque values).
- ⚠️ **But the PDF also carries a *hidden, noisy OCR text layer*** (font
  `HiddenHorzOCR`, invisible glyphs like `11~~~I0\\8llsPECI`). The noise bleeds into
  extraction in places (next sections). It is present in the PDF itself, not introduced
  by docling: PyMuPDF shows `ft·lb` on p.48 but `ft·Ib` on pp.49-50, and `SPECiFiCATIONS`
  on pp.4-5.

### 3. Text spot-checks (`output/page_text/`)
- p.1 (cover) — **0 chars** (image-only page).
- p.3 — 1013 chars, clean prose + symbols legend.
- p.22 — 28 chars (a diagram page; caption-level only).

### 4. Table recovery — the highest-value check ✅
**34 tables recovered as structured `TableItem`s (DataFrames), including the real spec
tables.** Sample quotes (`output/tables/`):

*Engine tightening torques — table_020_page_24.txt, 36x7 grid:*
```
Item                          Thread size  Qty   Nm    m·kg   ft·lb
Spark plug                        M10        1     13    1.3    9.4
Engine oil drain bolt             M14        1     30    3.0    22
Oil filter cartridge              M20        1     17    1.7    12
Crankcase bolt                    M8         3     26    2.6    19
```
*Engine specifications — table_006_page_9.txt (oil capacity):*
```
Engine oil:  without filter replacement   2.00 L (1.76 Imp qt, 2.11 US qt)
             with filter replacement      2.10 L (1.85 Imp qt, 2.22 US qt)
             total amount                 3.00 L (2.64 Imp qt, 3.17 US qt)
Fuel tank capacity                        29.3 L (6.45 Imp gal, 7.74 US gal)
Spark plug gap                            0.8 - 0.9 mm
```
Numbers and units are **correct and useful as-is**. Known warts (inherited from the
PDF, not docling): multi-row headers flatten (three "Tightening torque" unit columns
merge into one header); merged cells repeat values in adjacent columns; exploded-diagram
symbol references in "Remarks" become garbage; and the unit strings carry the PDF
`Ib`/`lb` and `m· kg` spacing noise.

### 5. Section / TOC / heading detection 🟡
- **71 `section_header` items detected, all with page numbers** — real chapters found:
  `CHAPTER 1 GENERAL INFORMATION (p4)`, `CHAPTER 4 ENGINE (p6)`, `SPECIFICATIONS (p8)`,
  `ENGINE SPECIFICATIONS (pp12-17)`, `EBS01005 TIGHTENING TORQUES (p24)`,
  `ADJUSTING THE VALVE CLEARANCE (p35)`. **Feasible** for §4.7 section segments.
- **But the list is noisy**: it also contains `TIP:`, `TTTTTTTTTTTT…` (decorative rule),
  `12.lnstall:`, `CHEC~N THESPARKPLU` as false-positive headers. A §4.7 section map must
  filter (drop all-`T` / short / `TIP:` / junk entries) before use.
- `document_index` (docling TOC outline) = **5 items with empty text** — not directly
  usable as a TOC. The chapter list *is* recoverable, but from the structured **TOC
  table** (pp.3-7 extracted as a `table` with "GENERAL SPECIFICATIONS … 2-1" page
  refs), not from `document_index`.

### 6. Page-number availability ✅
**513/513 items carry a `page_no`** (0 missing). Per-chunk/per-heading citations are
fully recoverable — the §4.7 page-index and the `extract_specs` citation contract are
supported.

### Q6 verdict: **sufficient with a documented fallback**
- **Adopt docling as the ingestion engine.** Structure, tables, page numbers, and body
  text are all good.
- **Documented fallback = a light normalization pass over *unit/header strings***
  (`lb`/`Ib`, `m· kg`, `N.m`, `SPECiFiCATIONS`, diagram-symbol junk in "Remarks").
  Numbers were reliable in every table inspected, so this is cheap string cleanup — not
  a full OCR-repair or a second LLM pass over everything. (Keep the second-LLM option in
  reserve for the *scanned* stretch manual, not this one.)
- Pin `do_ocr=False` + `FAST` table mode for digital manuals (memory + speed).

---

## Q10 — PDF slice vs. raster (generation + serving)

Representative pages: text-heavy (p8), diagram/spec-table (p48); diagrams render as
vector line art (the manual is diagram-dense: **75 `picture` items in 42 pages ~ 1.8
figures/page**).

| measure | PNG 150 dpi | PNG 300 dpi | WebP 300 dpi | **PDF slice** |
|---|---|---|---|---|
| size / page | 139-285 KB | 192-380 KB | ~110-295 KB | **49.7-51.0 KB** |
| pixel dims | 1275x1613 | 2550x3225 | (same) | vector (crisp) |
| generate / page | ~0.41 s | ~0.77 s | ~0.47 s | **~0.30 s** |
| text selectable | no (image) | no | no | **yes** |
| viewer mode | plain `<img>` / Next `<Image>` | (same) | (same) | react-pdf `<Document file>` |

- **Slice demo**: a 7-page window (pp.44-50) = **348 KB** vs the **23 MB** original; a
  heading-to-heading "enclosing section" (pp.43-49) = **357 KB**. Both re-open, render,
  and expose selectable text (521+ chars on p.1 of the slice). `pypdf` slicing is ~0.3 s
  for 7 pages.
- **Mobile**: a raster PNG/WebP pins/zooms natively as an image; a sliced PDF needs the
  full pdf.js/`react-pdf` document context — but §3.5 already commits to react-pdf for
  the viewer, and react-pdf handles a small slice (incl. pinch-zoom + text copy) fine.

### Q10 recommendation: **hybrid — PDF slices primary, raster thumbnails as companion**
- **Serve the viewer segment as a pre-sliced PDF** (`GET /manuals/{id}/pages/44-50` -> a
  50 KB self-contained slice), rendered by react-pdf in **PDF mode (`<Document
  file={slice}><Page/></Document>`)**. It is *smaller* (50 KB vs ~283 KB/page), keeps
  **selectable text** (torque values / part numbers / procedure steps — core repair UX),
  and keeps vector diagrams crisp.
- **Also pre-render per-page raster thumbnails** (150 dpi PNG/WebP via PyMuPDF) for the
  two already-planned companions where text is not needed: the citation-card inline
  diagram (§4.5 / §2.2 on-demand vision) and mobile list views — these are plain
  `<img>`/Next `<Image>` (plain `<img>` mode), **not** react-pdf.
- **Cheapest at ingest time:** both are trivial (~0.3-0.8 s/page) relative to docling
  ~5.8 s/page parse, so cost does not decide — correctness does. Slicing wins on size +
  selectable text -> primary; raster wins on "plain image / mobile" simplicity, and is
  the only way to *isolate a diagram* (§4.5) -> thumbnails.

---

## §7 planning — one-line answers

- **Total ingestion cost (this manual, one-time):** ~**50 min** CPU-bound — docling
  ~ 5.8 s/page => ~49 min for 503 pages, plus ~3-7 min to slice 503 pages + render 503
  thumbnails. Order of magnitude: **under an hour, not overnight.** (Measured at
  threads=2; 4-thread/batch-4 is faster but needs ~5 GB free RAM.)
- **First-run model downloads:** docling pulls ~**500 MB** from HuggingFace
  (`docling-layout-heron` ~164 MB + `docling-models` ~342 MB incl. TableFormer Fast/Accurate
  + figure classifier), **plus ~40 MB** RapidOCR from ModelScope **only if `do_ocr=True`**.
  ~570 MB total on a fresh machine.

---

## Anything that surprised us (the real risk)

1. **Default docling config OOMs a 15 GB dev box.** It eager-loads OCR + layout + table
   models (~6 GB) before touching a page — and on an already-busy machine that is a hard
   kernel OOM that took the desktop down twice. Pin `do_ocr=False`; treat "docling needs
   ~5 GB headroom" as an ingest-worker requirement.
2. **This "digital" manual has a hidden, noisy OCR text layer** (`HiddenHorzOCR`). It
   fingerprints as born-digital but silently degrades header/unit strings (`Ib`↔`lb`,
   `SPECiFiCATIONS`, `CHASSiS`) while leaving digits clean. Any extractor — docling or a
   fallback — inherits it. Normalization is a first-class ingest step, not an afterthought.
3. **docling 2.102 API differs from older tutorials**: `num_pages()` is a method,
   `iterate_items()` yields `(item, level)` tuples, label strings are lowercase
   (`section_header`, `table`), `PictureItem` has no `.text`, and
   `TableItem.export_to_dataframe()` deprecates no-arg use.
4. **`document_index` came back empty** (5 items, no text) — do not plan on docling TOC
   outline; the chapter/section map must be built from the (noisy) `section_header` list
   + the structured TOC table.
5. **Heading detection is too eager**: 71 "section headers" include `TIP:`, decorative
   `TTTTTT…` rules, and misclassified body text — worth a filter before the page-index is
   persisted, otherwise §4.7 section names will look sloppy in the viewer context bar.

*Files: `spike/docling_probe.py`, `spike/pdf_slice_raster_probe.py`; evidence under
`spike/output/` (`docling_summary.json`, `raster_slice_summary.json`, `headings.json`,
`document_index.json`, `tables/`, `raster/`, `slices/`, `page_text/`, `full_manual.md`).*
