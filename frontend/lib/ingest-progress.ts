// Turns the ingest progress a manual reports (DECISIONS U3) into what the
// upload dialog shows: a stage label, a bar fraction, and a rough time left.

import type { IngestProgress } from "@/lib/api";

/** What the pipeline is doing, in the reader's words. */
export function ingestStageLabel(progress: IngestProgress): string {
  switch (progress.stage) {
    case "convert":
      return `Reading pages ${progress.completed} of ${progress.total}`;
    case "index":
      return `Indexing ${progress.completed} of ${progress.total} chunks`;
    case "done":
      return "Finishing up";
    default:
      return "Opening the PDF";
  }
}

/** One-line status for a manual list row, e.g. "Processing 29%". */
export function ingestStatusText(progress: IngestProgress): string {
  const fraction = ingestStageFraction(progress);
  if (fraction === null) return "Processing…";
  return `Processing ${Math.round(fraction * 100)}%`;
}

/** How far the current stage has come, 0 to 1, or null when it cannot be counted. */
export function ingestStageFraction(progress: IngestProgress): number | null {
  if (progress.total <= 0) return null;
  return Math.min(1, progress.completed / progress.total);
}

// A stage's rate is only worth showing once enough of it has passed. Manual
// pages are not equally slow, so an early guess is not reliable.
const ETA_MIN_COMPLETED = 3;
const ETA_MIN_ELAPSED_MS = 10_000;

/**
 * Time left in the current stage, from the rate the run has actually kept.
 *
 * The rate is measured, never assumed. The same manual can take a minute or an
 * hour depending on the machine, so a fixed guess is wrong in one case or the
 * other.
 */
export function ingestRemainingMs(
  progress: IngestProgress,
  elapsedMs: number,
): number | null {
  if (progress.completed < ETA_MIN_COMPLETED) return null;
  if (progress.completed >= progress.total) return null;
  if (elapsedMs < ETA_MIN_ELAPSED_MS) return null;
  const perItem = elapsedMs / progress.completed;
  return perItem * (progress.total - progress.completed);
}

/** "about 2 min left". Rounded to the minute, because the rate is a rough one. */
export function formatRemaining(ms: number): string {
  const minutes = Math.round(ms / 60_000);
  if (minutes < 1) return "less than a minute left";
  if (minutes < 60) return `about ${minutes} min left`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest === 0
    ? `about ${hours} hr left`
    : `about ${hours} hr ${rest} min left`;
}
