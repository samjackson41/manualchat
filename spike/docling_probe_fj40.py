#!/usr/bin/env python3
"""
Scanned / diagram-heavy manual feasibility spike — Toyota Land Cruiser FJ40 factory manual.

Answers Q1-Q6 from scanned_ocr_probe_prompt.md with measured evidence.

Phases (select with --phase):
  q1    : native text-layer check via PyMuPDF (ALL 412 pages) + font list
  q5    : page classification — image/drawing counts + a pixel heuristic
  q1q5  : both of the above (the safe, memory-light half of the spike)
  ocr   : PARENT orchestrator — Docling do_ocr=True in batches, each in a fresh
          subprocess (optionally wrapped in systemd-run --user --scope MemoryMax)
  batch : INTERNAL subprocess entry point (converts ONE subset PDF + dumps JSON).
  q4    : direct-OCR (Tesseract / PyMuPDF OCR) side-by-side — see notes (tesseract absent)
  all   : q1q5 + ocr + q4

Crash-safety: `ocr` batches may be guarded with
  systemd-run --user --scope -p MemoryMax=<N>G
so an over-limit Docling run is OOM-killed inside its own cgroup instead of
taking down the desktop (the Rhino spike OOM-killed the desktop twice — see
SPIKE_FINDINGS.md). Enable with --use-systemd and set --memory-max.
"""

import argparse
import gc
import json
import logging
import resource
import subprocess
import time
from collections import Counter
from pathlib import Path

import pymupdf

PDF = "/home/sam/dev/aie-capstone/manuals/fj40manual.pdf"
OUT = Path("/home/sam/dev/aie-capstone/spike/output_fj40")
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "batches").mkdir(parents=True, exist_ok=True)
(OUT / "page_text").mkdir(parents=True, exist_ok=True)
(OUT / "tables").mkdir(parents=True, exist_ok=True)

PY = "/home/sam/dev/aie-cohort-202609/.venv/bin/python"
SCRIPT = str(Path(__file__).resolve())


def log(msg: str) -> None:
    print(msg, flush=True)


def peak_rss_gb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 / 1024  # KB -> GB


# --------------------------------------------------------------------------- #
# Q1 — native text-layer check (PyMuPDF, cheap)
# --------------------------------------------------------------------------- #
def phase_q1() -> dict:
    doc = pymupdf.open(PDF)
    n = doc.page_count
    per_page = []
    fonts = set()
    nonempty = 0
    total_chars = 0
    for i in range(n):
        t = doc[i].get_text().strip()
        L = len(t)
        per_page.append(L)
        total_chars += L
        if L > 0:
            nonempty += 1
        for f in doc[i].get_fonts():
            fonts.add(f[3])
    if nonempty == 0:
        verdict = "scanned (no embedded text layer — every page is a raster image)"
    elif nonempty < n:
        verdict = f"partial text layer ({nonempty}/{n} pages have text)"
    else:
        verdict = "born-digital (full text layer)"
    summary = {
        "question": "Q1",
        "page_count": n,
        "nonempty_text_pages": nonempty,
        "total_native_chars": total_chars,
        "fonts": sorted(fonts),
        "verdict": verdict,
        "per_page_native_chars": per_page,
    }
    (OUT / "q1_native_text.json").write_text(json.dumps(summary, indent=2))
    log(f"[Q1] page_count={n} nonempty_text_pages={nonempty} total_chars={total_chars}")
    log(f"[Q1] fonts={sorted(fonts)}")
    log(f"[Q1] verdict: {verdict}")
    return summary


# --------------------------------------------------------------------------- #
# Q5 — page classification (image/drawing counts + pixel heuristic)
# --------------------------------------------------------------------------- #
def _profile(page, dpi=100) -> dict:
    import numpy as np
    from scipy import ndimage

    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY, alpha=False)
    a = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    dark = a < 128
    ink = float(dark.mean())

    label, n = ndimage.label(dark)  # 4-connectivity
    slices = ndimage.find_objects(label)
    n_glyphs = n_blobs = n_lines_h = n_lines_v = 0
    H, W = dark.shape
    for sl in slices:
        h = sl[0].stop - sl[0].start
        w = sl[1].stop - sl[1].start
        area = int(dark[sl].sum())
        long_side = max(h, w)
        short_side = min(h, w)
        aspect = long_side / max(short_side, 1)
        if area <= 400 and aspect < 5:
            n_glyphs += 1
        elif area > 1500:
            n_blobs += 1
        if aspect >= 4 and long_side >= 0.15 * max(H, W):
            if w >= h:
                n_lines_h += 1
            else:
                n_lines_v += 1
    return {
        "ink": round(ink, 4),
        "components": int(n),
        "glyphs": n_glyphs,
        "blobs": n_blobs,
        "lines_h": n_lines_h,
        "lines_v": n_lines_v,
        "px_h": H,
        "px_w": W,
    }


def _classify(p: dict) -> str:
    lines = p["lines_h"] + p["lines_v"]
    if lines >= 10 and p["blobs"] <= 3:
        return "wiring_schematic"
    if p["blobs"] >= 4 and p["glyphs"] < 1500:
        return "diagram_heavy"
    if p["glyphs"] >= 800 and p["blobs"] <= 3 and lines <= 5:
        return "text_heavy"
    return "mixed"


def phase_q5() -> dict:
    doc = pymupdf.open(PDF)
    n = doc.page_count
    rows = []
    counts = Counter()
    for i in range(n):
        page = doc[i]
        n_imgs = len(page.get_images(full=True))
        n_draw = len(page.get_drawings())
        prof = _profile(page)
        cat = _classify(prof)
        counts[cat] += 1
        rows.append(
            {
                "page": i + 1,
                "images": n_imgs,
                "drawings": n_draw,
                "ink": prof["ink"],
                "components": prof["components"],
                "glyphs": prof["glyphs"],
                "blobs": prof["blobs"],
                "lines_h": prof["lines_h"],
                "lines_v": prof["lines_v"],
                "category": cat,
            }
        )
    summary = {
        "question": "Q5",
        "page_count": n,
        "category_counts": dict(counts),
        "per_page": rows,
    }
    (OUT / "page_classification.json").write_text(json.dumps(summary, indent=2))
    log(f"[Q5] category counts: {dict(counts)}")
    schematics = [r["page"] for r in rows if r["category"] == "wiring_schematic"]
    log(f"[Q5] wiring_schematic pages ({len(schematics)}): {schematics[:60]}")
    return summary


# --------------------------------------------------------------------------- #
# OCR pipeline config (shared by the `batch` subprocess)
# --------------------------------------------------------------------------- #
def build_converter():
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import (
        AcceleratorOptions,
        PdfPipelineOptions,
        RapidOcrOptions,
        TableFormerMode,
        TableStructureOptions,
    )
    from docling.document_converter import DocumentConverter, PdfFormatOption

    # onnxruntime IS now installed (was missing; torch backend measured ~150s/page — too slow).
    # easyocr + tesseract binary absent. Use RapidOCR's onnxruntime backend. lang=english.
    # force_full_page_ocr=True: REQUIRED for this scanned manual — without it Docling's
    # layout model treats whole diagram pages as one "picture" and drops ~half the text.
    import os

    threads = int(os.environ.get("DOCLING_THREADS", "2"))
    ocr_options = RapidOcrOptions(lang=["english"], backend="onnxruntime", force_full_page_ocr=True)
    pipeline_options = PdfPipelineOptions(
        do_ocr=True,
        do_table_structure=True,
        table_structure_options=TableStructureOptions(mode=TableFormerMode.FAST),
        ocr_options=ocr_options,
        layout_batch_size=1,
        table_batch_size=1,
        ocr_batch_size=1,
        accelerator_options=AcceleratorOptions(num_threads=threads),
    )
    format_options = {InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
    return DocumentConverter(format_options=format_options), ocr_options


# --------------------------------------------------------------------------- #
# batch — INTERNAL: convert ONE subset PDF with Docling, dump a per-batch JSON
# --------------------------------------------------------------------------- #
def phase_batch(page_map: list[int], subset_pdf: str) -> None:
    records: list[str] = []

    class _H(logging.Handler):
        def emit(self, r):
            records.append(r.getMessage())

    h = _H()
    logging.getLogger("docling").addHandler(h)
    logging.getLogger("docling").setLevel(logging.INFO)

    converter, ocr_options = build_converter()

    result = None
    status = "success"
    err = None
    t0 = time.perf_counter()
    try:
        result = converter.convert(subset_pdf)
    except Exception as e:  # noqa: BLE001
        status = f"FAILED: {type(e).__name__}"
        err = str(e)
    wall = time.perf_counter() - t0
    peak_gb = peak_rss_gb()

    engine_lines = [r for r in records if any(k in r.lower() for k in
                 ("ocr", "rapid", "tesseract", "easyocr", "engine"))]
    out = {
        "start": page_map[0] if page_map else None,
        "end": (page_map[-1] + 1) if page_map else None,
        "status": status,
        "error": err,
        "wall_seconds": round(wall, 2),
        "peak_rss_gb": round(peak_gb, 3),
        "ocr_backend_configured": f"{ocr_options.kind} (backend={ocr_options.backend}, lang={ocr_options.lang})",
        "docling_log_lines": engine_lines[:20],
        "per_page_chars": {},
        "per_page_text": {},
        "item_census": {},
        "tables": [],
        "headings": [],
        "markdown": "",
        "num_pages": None,
    }

    def _abs(subset_pn: int) -> int:
        # docling prov[0].page_no is 1-based within the subset; page_map holds the
        # 0-based absolute page index in subset order.
        pn = int(subset_pn)
        return page_map[pn - 1] if 1 <= pn <= len(page_map) else -1

    if result is not None and getattr(result, "document", None) is not None:
        doc = result.document
        out["num_pages"] = doc.num_pages()
        items = [it for it, _lvl in doc.iterate_items()]
        out["item_census"] = dict(Counter(str(it.label) for it in items))

        pages: dict[int, list[str]] = {}
        for it in items:
            try:
                pn = it.prov[0].page_no
            except Exception:  # noqa: BLE001
                continue
            abs_pn = _abs(pn)
            t = getattr(it, "text", "") or ""
            if t.strip():
                pages.setdefault(abs_pn, []).append(t)
        out["per_page_text"] = {str(k): "\n".join(v) for k, v in pages.items()}
        out["per_page_chars"] = {str(k): len("\n".join(v)) for k, v in pages.items()}

        for it in items:
            if str(it.label) in {"title", "section_header"}:
                pn = it.prov[0].page_no if it.prov else 0
                out["headings"].append(
                    {"label": str(it.label), "text": (getattr(it, "text", "") or "").strip(),
                     "page": _abs(pn)}
                )

        for it in doc.tables:
            try:
                pn = _abs(it.prov[0].page_no)
            except Exception:  # noqa: BLE001
                pn = None
            try:
                df = it.export_to_dataframe()
                shape = list(df.shape)
                df_repr = df.to_string()
            except Exception as e:  # noqa: BLE001
                shape, df_repr = None, f"<export failed: {e}>"
            out["tables"].append({"page": pn, "shape": shape, "text": df_repr or ""})

        out["markdown"] = doc.export_to_markdown()

    json_path = OUT / "batches" / f"batch_{page_map[0]:03d}_{page_map[-1]+1:03d}.json"
    json_path.write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    print(f"BATCH_DONE {json_path}", flush=True)


# --------------------------------------------------------------------------- #
# ocr — PARENT: slice pages, spawn guarded subprocess per batch, aggregate
# --------------------------------------------------------------------------- #
def slice_pdf(page_indices: list[int], dest: Path) -> None:
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(PDF)
    writer = PdfWriter()
    for p in page_indices:
        writer.add_page(reader.pages[p])
    with open(dest, "wb") as f:
        writer.write(f)


def phase_ocr(batch_size: int, use_systemd: bool, memory_max: int,
              max_batches: int | None, pages: list[int] | None) -> dict:
    total = pymupdf.open(PDF).page_count
    # 0-based page indices to process: full doc, or a requested sample
    if pages:
        plan = [p - 1 for p in pages if 1 <= p <= total]
    else:
        plan = list(range(total))

    n_batches = 0
    peak_overall = 0.0
    wall_overall = 0.0
    statuses = []
    aggregate = {
        "per_page_chars": {},
        "per_page_text": {},
        "item_census": Counter(),
        "tables": [],
        "headings": [],
        "markdown_parts": [],
        "batches": [],
        "plan": [p + 1 for p in plan],
    }
    t0 = time.perf_counter()
    for i in range(0, len(plan), batch_size):
        if max_batches is not None and n_batches >= max_batches:
            log(f"[ocr] canary limit reached ({max_batches} batches); stopping.")
            break
        chunk = plan[i:i + batch_size]
        start = chunk[0]
        end = chunk[-1] + 1
        subset = OUT / f"_subset_fj40_batch_{n_batches:03d}.pdf"
        slice_pdf(chunk, subset)
        page_map = ",".join(str(p) for p in chunk)
        cmd = [PY, SCRIPT, "--phase", "batch", "--page-map", page_map,
               "--pdf", str(subset)]
        if use_systemd:
            cmd = ["systemd-run", "--user", "--scope", "-p", f"MemoryMax={memory_max}G",
                   "--collect", "--quiet", *cmd]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        json_path = None
        for line in r.stdout.splitlines():
            if line.startswith("BATCH_DONE "):
                json_path = line.split(" ", 1)[1]
        batch = None
        if json_path and Path(json_path).exists():
            batch = json.loads(Path(json_path).read_text())
        elif r.returncode != 0:
            batch = {"start": start, "end": end, "status": "subprocess_failed",
                     "error": (r.stderr or "")[-800:], "peak_rss_gb": None,
                     "wall_seconds": None}
        else:
            batch = {"start": start, "end": end, "status": "no_batch_json",
                     "error": (r.stdout or "")[-800:] + (r.stderr or "")[-400:]}

        statuses.append(batch.get("status"))
        peak_overall = max(peak_overall, batch.get("peak_rss_gb") or 0)
        wall_overall += batch.get("wall_seconds") or 0
        aggregate["batches"].append(batch)
        for k, v in (batch.get("per_page_chars") or {}).items():
            aggregate["per_page_chars"][k] = v
        for k, v in (batch.get("per_page_text") or {}).items():
            aggregate["per_page_text"][k] = v
        for k, v in (batch.get("item_census") or {}).items():
            aggregate["item_census"][k] += v
        aggregate["tables"].extend(batch.get("tables") or [])
        aggregate["headings"].extend(batch.get("headings") or [])
        if batch.get("markdown"):
            aggregate["markdown_parts"].append(batch["markdown"])

        subset.unlink(missing_ok=True)
        gc.collect()
        n_batches += 1
        log(f"[ocr] batch {start}-{end} status={batch.get('status')} "
            f"peak={batch.get('peak_rss_gb')}GB wall={batch.get('wall_seconds')}s "
            f"(cumulative wall={time.perf_counter()-t0:.0f}s)")

    wall_overall = time.perf_counter() - t0
    return aggregate, {
        "total_pages": total,
        "pages_processed": len(aggregate["per_page_chars"]),
        "batches": n_batches,
        "statuses": Counter(statuses),
        "peak_rss_gb": round(peak_overall, 3),
        "wall_seconds": round(wall_overall, 1),
    }, statuses


# --------------------------------------------------------------------------- #
# finalize — write the aggregate artifacts from accumulated batch JSONs
# --------------------------------------------------------------------------- #
def finalize(aggregate: dict, meta: dict, spot_pages: list[int]) -> None:
    # full_manual.md (concatenated markdown in page order)
    full_md = "\n\n".join(aggregate["markdown_parts"])
    (OUT / "full_manual.md").write_text(full_md)

    # ocr_vs_native.json — merge Q1 native chars with Q2 OCR chars
    native = {}
    q1_path = OUT / "q1_native_text.json"
    if q1_path.exists():
        native = {str(i): v for i, v in
                  enumerate(json.loads(q1_path.read_text())["per_page_native_chars"])}
    ocr = aggregate["per_page_chars"]
    all_pages = sorted({int(k) for k in set(native) | set(ocr)})
    vs = [{"page": p, "native_chars": native.get(str(p), 0),
           "ocr_chars": ocr.get(str(p), 0)} for p in all_pages]
    (OUT / "ocr_vs_native.json").write_text(json.dumps(vs, indent=2))

    # tables
    tindex = []
    for i, t in enumerate(aggregate["tables"]):
        pn = t.get("page")
        fname = OUT / "tables" / f"table_{i:03d}_page_{pn}.txt"
        fname.write_text(t.get("text", ""))
        tindex.append({"table_index": i, "page": pn, "shape": t.get("shape"),
                       "preview": (t.get("text") or "")[:400]})
    (OUT / "tables" / "_index.json").write_text(json.dumps(tindex, indent=2, ensure_ascii=False))

    # headings
    (OUT / "headings.json").write_text(json.dumps(aggregate["headings"], indent=2, ensure_ascii=False))

    # spot-check page text
    for pn in spot_pages:
        txt = aggregate["per_page_text"].get(str(pn - 1), "")
        (OUT / "page_text" / f"page_{pn:03d}.md").write_text(txt)

    # summary
    summary = {
        "question": "Q2/Q3",
        **meta,
        "item_census": dict(aggregate["item_census"]),
        "table_count": len(aggregate["tables"]),
        "heading_count": len(aggregate["headings"]),
        "ocr_vs_native_written": "ocr_vs_native.json",
    }
    (OUT / "docling_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    log(f"[finalize] wrote full_manual.md ({len(full_md)} chars), "
        f"{len(aggregate['tables'])} tables, summary -> docling_summary.json")


# --------------------------------------------------------------------------- #
# q4 — direct OCR side-by-side (Tesseract / PyMuPDF OCR)
# --------------------------------------------------------------------------- #
def phase_q4() -> dict:
    import shutil

    result = {
        "question": "Q4",
        "tesseract_binary": shutil.which("tesseract"),
        "pytesseract_import": None,
        "pymupdf_ocr_note": "PyMuPDF get_text('ocr') / get_textpage_ocr() require the "
                            "Tesseract binary, which is NOT installed.",
    }
    try:
        import pytesseract  # noqa: F401

        result["pytesseract_import"] = "available"
    except ImportError:
        result["pytesseract_import"] = "MISSING"
    result["verdict"] = (
        "Tesseract is not installed -> PyMuPDF/Tesseract direct OCR cannot run. "
        "Install with: sudo apt-get install tesseract-ocr, then re-run Q4."
    )
    (OUT / "q4_direct_ocr.json").write_text(json.dumps(result, indent=2))
    log(f"[Q4] tesseract_binary={result['tesseract_binary']} "
        f"pytesseract={result['pytesseract_import']}")
    log(f"[Q4] {result['verdict']}")
    return result


# --------------------------------------------------------------------------- #
# main / argparse
# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description="FJ40 scanned-manual feasibility spike")
    ap.add_argument("--phase", default="q1q5",
                    choices=["q1", "q5", "q1q5", "ocr", "batch", "q4", "all"])
    ap.add_argument("--batch-size", type=int, default=2)
    ap.add_argument("--use-systemd", action="store_true")
    ap.add_argument("--memory-max", type=int, default=5, help="GB ceiling for systemd MemoryMax")
    ap.add_argument("--max-batches", type=int, default=None,
                    help="canary: stop after N batches")
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--end", type=int, default=0)
    ap.add_argument("--page-map", type=str, default="",
                    help="comma-separated 0-based absolute page indices (batch phase)")
    ap.add_argument("--pdf", type=str, default="")
    ap.add_argument("--spot-pages", type=str, default="",
                    help="comma-separated 1-based page numbers for spot-check export")
    ap.add_argument("--pages", type=str, default="",
                    help="comma-separated 1-based page numbers to OCR (default: whole doc)")
    args = ap.parse_args()

    if args.phase == "batch":
        page_map = [int(x) for x in args.page_map.split(",") if x.strip()]
        phase_batch(page_map, args.pdf)
        return
    if args.phase in ("q1", "q1q5", "all"):
        phase_q1()
    if args.phase in ("q5", "q1q5", "all"):
        phase_q5()
    if args.phase in ("ocr", "all"):
        spot = [int(x) for x in args.spot_pages.split(",") if x.strip()]
        pages = [int(x) for x in args.pages.split(",") if x.strip()] or None
        aggregate, meta, _statuses = phase_ocr(
            args.batch_size, args.use_systemd, args.memory_max, args.max_batches, pages)
        finalize(aggregate, meta, spot)
    if args.phase in ("q4", "all"):
        phase_q4()


if __name__ == "__main__":
    main()
