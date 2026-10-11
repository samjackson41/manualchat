#!/usr/bin/env bash
# Launcher for the FJ40 OCR sample run (runs detached, logs to ocr_sample.log)
cd /home/sam/dev/aie-capstone/spike
exec /home/sam/dev/aie-cohort-202609/.venv/bin/python docling_probe_fj40.py \
  --phase ocr \
  --pages '1,2,3,5,6,22,34,48,50,67,81,97,98,100,122,150,166,174,175,200,238,250,274,275,281,284,290,300,312,333,336,344,346,350,370,375,376,384,389,390,394,395,400' \
  --spot-pages '22,6,35' \
  --batch-size 4 \
  --use-systemd \
  --memory-max 4
