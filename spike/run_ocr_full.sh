#!/usr/bin/env bash
# FULL overnight OCR run of the FJ40 manual (all 412 pages).
# force_full_page_ocr=True + onnxruntime + 8 threads.
# batch-size 40: measured peak RSS 2.28 GB (memory is model-weight-dominated, not
# page-count-dominated), so larger batches cut model-reload overhead without OOM risk.
# Each batch runs in a fresh subprocess wrapped in systemd-run MemoryMax=4G.
cd /home/sam/dev/aie-capstone/spike
export DOCLING_THREADS=8
exec /home/sam/dev/aie-cohort-202609/.venv/bin/python docling_probe_fj40.py \
  --phase ocr \
  --batch-size 40 \
  --use-systemd \
  --memory-max 4 \
  --spot-pages '34,284,333,374'
