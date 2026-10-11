#!/usr/bin/env python3
"""
Q6 probe — docling fidelity on the Rhino 700 FI manual (born-digital PDF).

Answers, with measured evidence:
  1. wall-clock + peak memory of a full DocumentConverter run; success/failure
  2. extracted page count vs. real page count (via PyMuPDF ground truth);
     is it born-digital (text layer) or scanned?
  3. spot-check text fidelity (page 1, a mid page, and located spec-table pages)
  4. table recovery — do real spec tables survive as structured tables or free text?
  5. section/TOC/heading detection — how much structure does docling expose?
  6. page-number availability per chunk/heading (citations requirement)

Run (from this dir):
  # full manual (needs ~5 GB free RAM; see SPIKE_FINDINGS.md)
  /home/sam/dev/aie-cohort-202609/.venv/bin/python /home/sam/dev/aie-capstone/spike/docling_probe.py
  # or a pre-sliced subset (memory-safe — what produced the findings here)
  /home/sam/dev/aie-cohort-202609/.venv/bin/python /home/sam/dev/aie-capstone/spike/docling_probe.py \
      /home/sam/dev/aie-capstone/spike/output/_subset_q6.pdf

All sample output is written to spike/output/ (markdown/json/txt). Stdout stays terse.
"""

import json
import os
import resource
import sys
import time
from collections import Counter
from pathlib import Path

import pymupdf  # PyMuPDF — used ONLY for ground-truth page count + text-layer check

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    AcceleratorOptions,
    PdfPipelineOptions,
    TableFormerMode,
    TableStructureOptions,
)
from docling.document_converter import DocumentConverter, PdfFormatOption

FULL_PDF = "/home/sam/dev/aie-capstone/2008-2010-Rhino-700Fi-Manual.pdf"
# Optional override: pass a subset PDF path as argv[1] (memory-safe testing).
PDF = sys.argv[1] if len(sys.argv) > 1 else FULL_PDF
OUT = Path("/home/sam/dev/aie-capstone/spike/output")
OUT.mkdir(parents=True, exist_ok=True)

# Pipeline config — memory-frugal and correct for a BORN-DIGITAL manual.
#   - do_ocr=False: this manual has a text layer, so RapidOCR (torch) is not needed.
#     (The default do_ocr=True downloads + eager-loads RapidOCR models and, together
#     with the layout/table models, OOM-killed a 15GB machine — see SPIKE_FINDINGS.md.)
#   - TableFormerMode.FAST: lighter table-structure model; ACCURATE is the heavier
#     fidelity fallback, documented in the findings.
#   - batch sizes 1 / num_threads 2: shrink inference activation buffers to fit RAM.
PIPELINE_OPTIONS = dict(
    do_ocr=False,
    do_table_structure=True,
    table_structure_options=TableStructureOptions(mode=TableFormerMode.FAST),
    layout_batch_size=1,
    table_batch_size=1,
    ocr_batch_size=1,
    accelerator_options=AcceleratorOptions(num_threads=2),
)

LOG = []


def log(msg: str) -> None:
    LOG.append(msg)
    print(msg)


def peak_rss_kb() -> int:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss  # already KB on Linux


def main() -> None:
    summary = {}

    # ---- ground truth via PyMuPDF (not docling) ----
    gt_doc = pymupdf.open(PDF)
    real_pages = gt_doc.page_count
    log(f"[ground-truth] PyMuPDF real page count = {real_pages}")

    # text-layer check: sample evenly-spaced pages, measure extractable text
    sample_idx = [0, real_pages // 4, real_pages // 2, 3 * real_pages // 4, real_pages - 1]
    text_lens = {}
    fonts = set()
    for i in sample_idx:
        page = gt_doc[i]
        text_lens[i] = len(page.get_text().strip())
        for f in page.get_fonts():
            fonts.add(f[3])
    born_digital = all(v > 50 for v in text_lens.values())
    log(
        f"[ground-truth] text-layer lens (chars) at pages {sample_idx}: "
        f"{ {k: text_lens[k] for k in sample_idx} }"
    )
    log(f"[ground-truth] born-digital (text layer) = {born_digital}; sample fonts = {sorted(fonts)}")
    summary["real_page_count"] = real_pages
    summary["born_digital"] = born_digital
    summary["sample_fonts"] = sorted(fonts)
    summary["text_layer_char_lens"] = {str(k): v for k, v in text_lens.items()}

    # ---- full docling conversion ----
    pipeline_options = PdfPipelineOptions(**PIPELINE_OPTIONS)
    format_options = {InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
    converter = DocumentConverter(format_options=format_options)
    summary["pipeline_config"] = {
        "do_ocr": pipeline_options.do_ocr,
        "do_table_structure": pipeline_options.do_table_structure,
        "table_mode": pipeline_options.table_structure_options.mode.name,
        "num_threads": pipeline_options.accelerator_options.num_threads,
    }
    log(f"[docling] config={summary['pipeline_config']}")
    log("[docling] starting full conversion (first run still loads layout + table models) ...")
    t0 = time.perf_counter()
    rss0 = peak_rss_kb()
    try:
        result = converter.convert(PDF)
        status = "success"
    except Exception as e:  # noqa: BLE001
        status = f"FAILED: {type(e).__name__}: {e}"
        result = None
    wall_s = time.perf_counter() - t0
    peak_kb = peak_rss_kb()
    log(
        f"[docling] status={status} wall={wall_s:.1f}s peak_rss={peak_kb/1024/1024:.2f} GB "
        f"(delta={ (peak_kb-rss0)/1024:.0f} MB over baseline {rss0/1024:.0f} MB)"
    )
    summary["docling_status"] = status
    summary["input_pdf"] = PDF
    summary["input_pdf_is_subset"] = PDF != FULL_PDF
    summary["wall_seconds"] = round(wall_s, 2)
    summary["peak_rss_gb"] = round(peak_kb / 1024 / 1024, 3)

    if result is None or getattr(result, "document", None) is None:
        summary["error"] = status
        (OUT / "docling_summary.json").write_text(json.dumps(summary, indent=2))
        return

    doc = result.document
    npages = doc.num_pages()
    log(f"[docling] extracted pages = {npages}")
    summary["docling_num_pages"] = npages
    summary["page_count_matches"] = npages == real_pages

    # timings per pipeline stage (if exposed)
    try:
        timings = {}
        for k, v in result.timings.items():
            try:
                timings[k] = {"sec": round(v.timings[0], 3), "details": v.timings[1]}
            except Exception:  # noqa: BLE001
                timings[k] = str(v)
        summary["pipeline_timings"] = timings
        log(f"[docling] pipeline stage timings: {json.dumps(timings, default=str)}")
    except Exception as e:  # noqa: BLE001
        log(f"[docling] (timings not exposed: {e})")

    # ---- full markdown export ----
    md = doc.export_to_markdown()
    md_path = OUT / "full_manual.md"
    md_path.write_text(md)
    # ---- item census: what did docling detect? ----
    label_counter = Counter()
    items = [it for it, _lvl in doc.iterate_items()]
    for it in items:
        label_counter[str(it.label)] += 1
    log(f"[docling] item census (label -> count): {dict(label_counter)}")
    summary["item_census"] = dict(label_counter)
    summary["total_items"] = len(items)

    # headings (section structure) + document_index (TOC outline)
    heading_labels = {"title", "section_header"}
    headings = []
    outline = []
    for it in items:
        lbl = str(it.label)
        if lbl in heading_labels:
            page = None
            try:
                page = it.prov[0].page_no
            except Exception:  # noqa: BLE001
                page = None
            headings.append({"label": lbl, "text": (getattr(it, "text", "") or "").strip(), "page": page})
        elif lbl == "document_index":
            outline.append(
                {
                    "label": lbl,
                    "text": (getattr(it, "text", "") or "").strip(),
                    "page": None,
                }
            )
    log(f"[docling] headings detected (title/section_header): {len(headings)}")
    log(f"[docling] document_index (TOC outline) items: {len(outline)}")
    summary["heading_count"] = len(headings)
    summary["document_index_count"] = len(outline)
    (OUT / "headings.json").write_text(json.dumps(headings, indent=2, ensure_ascii=False))
    (OUT / "document_index.json").write_text(json.dumps(outline, indent=2, ensure_ascii=False))

    # page-number availability across ALL items (citations requirement)
    items_with_page = 0
    items_without_page = 0
    for it in items:
        try:
            _ = it.prov[0].page_no
            items_with_page += 1
        except Exception:  # noqa: BLE001
            items_without_page += 1
    log(
        f"[docling] page-number availability: {items_with_page}/{len(items)} items carry a "
        f"page_no ({items_without_page} missing)"
    )
    # ---- tables: count + locate spec tables ----
    tables = list(doc.tables)
    log(f"[docling] tables detected = {len(tables)}")
    summary["table_count"] = len(tables)

    # build a flat page->text map for keyword search of spec tables
    def item_text(it) -> str:
        t = getattr(it, "text", None)
        if t:
            return t
        cap = getattr(it, "caption", None)
        return cap or ""

    def page_text(page_no: int) -> str:
        chunks = []
        for it in items:
            try:
                pn = it.prov[0].page_no
            except Exception:  # noqa: BLE001
                continue
            if pn == page_no:
                chunks.append(item_text(it))
        return "\n".join(chunks)

    keywords = ["torque", "engine oil", "oil capacity", "valve clearance", "specifications"]
    spec_pages = {}
    for kw in keywords:
        hits = []
        for it in items:
            t = item_text(it).lower()
            if kw in t:
                try:
                    hits.append(it.prov[0].page_no)
                except Exception:  # noqa: BLE001
                    pass
        spec_pages[kw] = sorted(set(hits))
    log(f"[docling] keyword hit pages: {json.dumps(spec_pages)}")
    summary["spec_keyword_hit_pages"] = {k: v for k, v in spec_pages.items()}

    # ---- spot-check text fidelity: page 1, mid page, spec-table pages ----
    spot_pages = [1]  # 1-based page for human reading
    spot_pages.append((real_pages // 2) + 1)
    # add the first located spec-table pages (specifications + torque) so a human can eyeball them
    for kw in ["specifications", "torque"]:
        if spec_pages.get(kw):
            spot_pages.append(spec_pages[kw][0] + 1)
    spot_pages = sorted(set(spot_pages))
    table_pages = set()
    for it in items:
        if str(it.label) == "table":
            try:
                table_pages.add(it.prov[0].page_no)
            except Exception:  # noqa: BLE001
                pass
    log(f"[docling] pages that contain at least one TABLE item: {sorted(table_pages)}")

    os.makedirs(OUT / "page_text", exist_ok=True)
    for pno in spot_pages:
        ptext = page_text(pno - 1)  # items use 0-based page_no
        fname = OUT / "page_text" / f"page_{pno:03d}.md"
        fname.write_text(ptext)
        log(f"[docling] spot-check page {pno}: {len(ptext)} chars -> {fname.name}")

    # ---- table recovery deep-dive ----
    os.makedirs(OUT / "tables", exist_ok=True)
    table_report = []
    for i, t in enumerate(tables):
        try:
            pn = t.prov[0].page_no
        except Exception:  # noqa: BLE001
            pn = None
        try:
            df = t.export_to_dataframe()
            n_rows, n_cols = df.shape
            full_repr = df.to_string()
        except Exception as e:  # noqa: BLE001
            df, n_rows, n_cols, full_repr = None, None, None, None
        if df is not None:
            (OUT / "tables" / f"table_{i:03d}_page_{pn}.txt").write_text(full_repr)
        entry = {
            "table_index": i,
            "page": pn,
            "shape": [n_rows, n_cols],
            "preview": (full_repr or f"<dataframe export failed>")[:600],
        }
        table_report.append(entry)
    (OUT / "tables" / "_index.json").write_text(
        json.dumps(table_report, indent=2, ensure_ascii=False, default=str)
    )
    log(
        f"[docling] wrote {len(table_report)} table dumps to {OUT/'tables/'} "
        f"(see _index.json for shapes + previews)"
    )

    # structured vs mangled: report tables whose page intersects a spec keyword page
    for kw, pages in spec_pages.items():
        hits = [t for t in table_report if t["page"] in pages]
        if hits:
            log(f"[docling] spec keyword '{kw}': {len(hits)} TABLE item(s) found on hit pages")
            for h in hits[:3]:
                log(f"    table idx={h['table_index']} page={h['page']} shape={h['shape']}")

    summary["table_pages"] = sorted(table_pages)
    (OUT / "docling_summary.json").write_text(json.dumps(summary, indent=2, default=str))

    # ---- verdict hints to aid the human (not authoritative) ----
    log("\n=== summary written to spike/output/docling_summary.json ===")
    log(f"    pages: extracted {doc.num_pages()} vs real {real_pages}")
    log(f"    tables: {len(tables)} detected; headings: {len(headings)}")
    log(f"    page_no availability: {items_with_page}/{len(items)}")


if __name__ == "__main__":
    main()