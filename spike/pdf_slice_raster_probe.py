#!/usr/bin/env python3
"""
Q10 probe — PDF page-slicing vs. raster-image rendering on the Rhino 700 FI manual.

Measures, on 2-3 representative pages (text-heavy, diagram-heavy, spec-table):
  1. Raster: PNG (and WebP) at ~150 and ~300 DPI via PyMuPDF — per-page file size,
     render time, pixel dimensions.
  2. Slice: pypdf page-range extraction into a self-contained PDF — slice size vs the
     23 MB original, and confirm the slice re-opens / re-renders / keeps selectable text.
  3. Comparison across: size-per-page, generation cost, text selectability, mobile
     friendliness → feeds the Q10 recommendation.

Run (from this dir):
  /home/sam/dev/aie-cohort-202609/.venv/bin/python /home/sam/dev/aie-capstone/spike/pdf_slice_raster_probe.py

Writes PNG/WebP/PDF slice artifacts + a JSON summary to spike/output/. Stdout terse.
"""

import json
import os
import time
from io import BytesIO
from pathlib import Path

import pymupdf
from pypdf import PdfReader, PdfWriter

PDF = "/home/sam/dev/aie-capstone/2008-2010-Rhino-700Fi-Manual.pdf"
OUT = Path("/home/sam/dev/aie-capstone/spike/output")
RASTER = OUT / "raster"
SLICE = OUT / "slices"
for d in (RASTER, SLICE):
    d.mkdir(parents=True, exist_ok=True)
ORIGINAL_MB = os.path.getsize(PDF) / 1024 / 1024

LOG = []


def log(msg: str) -> None:
    LOG.append(msg)
    print(msg)


def pick_pages(doc: pymupdf.Document) -> dict:
    """Auto-locate representative pages: text-heavy, diagram-heavy, spec-table."""
    n = doc.page_count
    text_lens = []
    image_counts = []
    drawing_counts = []
    for i in range(n):
        page = doc[i]
        text = page.get_text()
        text_lens.append((len(text), i))
        # get_drawings is expensive; only run where the page looks graphic-heavy
        if len(text) < 200:
            drawing_counts.append((len(page.get_drawings()), i))
        image_counts.append((len(page.get_images(full=True)), i))

    text_page = max(text_lens)[1]
    img_page = max(image_counts)[1]
    draw_page = max(drawing_counts)[1] if drawing_counts else img_page

    spec_page = None
    for i in range(n):
        t = doc[i].get_text().lower()
        if "torque" in t and ("n·m" in t or "nm" in t or "kg" in t or "lb" in t):
            spec_page = i
            break
    if spec_page is None:
        for i in range(n):
            if "specifications" in doc[i].get_text().lower():
                spec_page = i
                break

    return {
        "text_heavy": text_page,
        "diagram_heavy": draw_page,
        "spec_table": spec_page if spec_page is not None else text_page,
    }


def rasterize(doc, page_idx, dpi, fmt) -> dict:
    page = doc[page_idx]
    zoom = dpi / 72.0
    mat = pymupdf.Matrix(zoom, zoom)
    t0 = time.perf_counter()
    pix = page.get_pixmap(matrix=mat, alpha=False)
    png_bytes = pix.tobytes("png")
    dt = time.perf_counter() - t0
    if fmt == "png":
        data = png_bytes
    else:
        from PIL import Image  # deferred import

        img = Image.open(BytesIO(png_bytes))
        buf = BytesIO()
        img.save(buf, format="WEBP", quality=80)
        data = buf.getvalue()
    fname = RASTER / f"page_{page_idx + 1:03d}_{dpi}dpi.{fmt}"
    fname.write_bytes(data)
    return {
        "page": page_idx + 1,
        "dpi": dpi,
        "fmt": fmt,
        "w_px": pix.width,
        "h_px": pix.height,
        "size_kb": round(len(data) / 1024, 1),
        "render_sec": round(dt, 4),
        "file": str(fname.relative_to(OUT)),
    }


def slice_pages(start_idx, end_idx, label) -> dict:
    """Extract inclusive start_idx..end_idx (0-based) into a self-contained PDF via pypdf."""
    t0 = time.perf_counter()
    reader = PdfReader(PDF)
    writer = PdfWriter()
    for i in range(start_idx, end_idx + 1):
        writer.add_page(reader.pages[i])
    out_path = SLICE / f"{label}_pages_{start_idx + 1}-{end_idx + 1}.pdf"
    with open(out_path, "wb") as f:
        writer.write(f)
    dt = time.perf_counter() - t0
    size_kb = os.path.getsize(out_path) / 1024
    return {
        "label": label,
        "range": f"{start_idx + 1}-{end_idx + 1}",
        "n_pages": end_idx - start_idx + 1,
        "size_kb": round(size_kb, 1),
        "size_mb": round(size_kb / 1024, 3),
        "slice_sec": round(dt, 4),
        "file": str(out_path.relative_to(OUT)),
    }


def main() -> None:
    summary = {"original_mb": round(ORIGINAL_MB, 2)}

    doc = pymupdf.open(PDF)
    pages = pick_pages(doc)
    log(f"[q10] representative pages (0-based): {pages}")
    log(f"       text-heavy={pages['text_heavy']+1} "
        f"diagram-heavy={pages['diagram_heavy']+1} "
        f"spec-table={pages['spec_table']+1}")

    # ---- raster ----
    raster_rows = []
    for kind in ["text_heavy", "diagram_heavy", "spec_table"]:
        p = pages[kind]
        for dpi in [150, 300]:
            for fmt in ["png", "webp"]:
                r = rasterize(doc, p, dpi, fmt)
                r["kind"] = kind
                raster_rows.append(r)
                log(
                    f"[raster] {kind} page {r['page']} @{dpi}dpi {fmt}: "
                    f"{r['w_px']}x{r['h_px']}px, {r['size_kb']} KB, {r['render_sec']}s"
                )
    summary["raster"] = raster_rows

    # ---- slice ----
    slice_rows = []
    center = 46  # 0-based page 47
    s = slice_pages(center - 3, center + 3, "page47_window")
    slice_rows.append(s)
    log(f"[slice] page-47 window {s['range']}: {s['size_kb']} KB ({s['slice_sec']}s)")

    # enclosing-section range, if docling headings.json is available
    headings_path = OUT / "headings.json"
    enclosing = None
    if headings_path.exists():
        headings = json.loads(headings_path.read_text())
        pages_with_h = [h for h in headings if h.get("page") is not None]
        for i, h in enumerate(pages_with_h):
            start = h["page"]
            end = pages_with_h[i + 1]["page"] - 1 if i + 1 < len(pages_with_h) else start + 6
            if 4 <= (end - start) <= 15:
                enclosing = (h["text"], start, end)
                break
    if enclosing:
        title, start, end = enclosing
        s = slice_pages(start, min(end, doc.page_count - 1), "enclosing_section")
        s["section_title"] = title[:60]
        slice_rows.append(s)
        log(f"[slice] enclosing section '{title[:40]}' pages {s['range']}: {s['size_kb']} KB")
    else:
        log("[slice] no usable section boundary found in headings.json — skipped enclosing slice")

    summary["slices"] = slice_rows

    # ---- verify slices re-open + render + keep selectable text ----
    verify = []
    for srow in slice_rows:
        fp = OUT / srow["file"]
        rdoc = pymupdf.open(str(fp))
        text0 = rdoc[0].get_text().strip()
        pix = rdoc[0].get_pixmap(matrix=pymupdf.Matrix(1.0, 1.0), alpha=False)
        verify.append(
            {
                "file": srow["file"],
                "opens": True,
                "pages_in_slice": rdoc.page_count,
                "first_page_text_chars": len(text0),
                "text_selectable": len(text0) > 0,
                "renders": pix.width > 0,
            }
        )
        log(
            f"[verify] {srow['file']}: pages={rdoc.page_count} "
            f"text_selectable={len(text0) > 0} renders=ok"
        )
    summary["slice_verification"] = verify

    # ---- size-per-page comparison ----
    png300 = [r for r in raster_rows if r["dpi"] == 300 and r["fmt"] == "png"]
    avg_kb_per_page_raster = sum(r["size_kb"] for r in png300) / len(png300)
    slice_kb_per_page = [s["size_kb"] / s["n_pages"] for s in slice_rows]
    summary["avg_kb_per_page_300dpi_png"] = round(avg_kb_per_page_raster, 1)
    summary["slice_kb_per_page"] = [round(x, 1) for x in slice_kb_per_page]
    log(
        f"[compare] ~300dpi PNG ≈ {avg_kb_per_page_raster:.1f} KB/page; "
        f"PDF slice ≈ {[round(x,1) for x in slice_kb_per_page]} KB/page"
    )

    (OUT / "raster_slice_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print("\n=== written to spike/output/raster_slice_summary.json ===")


if __name__ == "__main__":
    main()