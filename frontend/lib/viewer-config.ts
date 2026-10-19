// Viewer tunables, each overridable with a NEXT_PUBLIC_ env var (DECISIONS P1).
// Next.js inlines NEXT_PUBLIC_ values at build time, so set them in
// docker-compose.yml and restart the frontend dev server to take effect.

function numberFromEnv(value: string | undefined, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

// Pages loaded on each side of the cited page (DECISIONS V1).
export const SLICE_PAGES_BEFORE = numberFromEnv(
  process.env.NEXT_PUBLIC_VIEWER_SLICE_BEFORE,
  1,
);
export const SLICE_PAGES_AFTER = numberFromEnv(
  process.env.NEXT_PUBLIC_VIEWER_SLICE_AFTER,
  2,
);

// Height/width of a page that has not rendered yet, used to size the
// placeholders in the lazy page list. The default suits US Letter paper.
export const PAGE_ASPECT = numberFromEnv(
  process.env.NEXT_PUBLIC_VIEWER_PAGE_ASPECT,
  1.294,
);

// The zoom controls: the scale a click adds, and the range it stays inside
// (DECISIONS V3). A zoom of 1 fits a page to the pane width.
export const ZOOM_STEP = numberFromEnv(process.env.NEXT_PUBLIC_VIEWER_ZOOM_STEP, 0.25);
export const ZOOM_MIN = numberFromEnv(process.env.NEXT_PUBLIC_VIEWER_ZOOM_MIN, 0.5);
export const ZOOM_MAX = numberFromEnv(process.env.NEXT_PUBLIC_VIEWER_ZOOM_MAX, 3);

// The pane width the reader drags, in pixels, and the range it stays inside
// (DECISIONS V4).
export const PANE_WIDTH_DEFAULT = numberFromEnv(
  process.env.NEXT_PUBLIC_VIEWER_WIDTH_DEFAULT,
  416,
);
export const PANE_WIDTH_MIN = numberFromEnv(
  process.env.NEXT_PUBLIC_VIEWER_WIDTH_MIN,
  280,
);
export const PANE_WIDTH_MAX = numberFromEnv(
  process.env.NEXT_PUBLIC_VIEWER_WIDTH_MAX,
  900,
);

export function clampPaneWidth(width: number): number {
  return Math.min(PANE_WIDTH_MAX, Math.max(PANE_WIDTH_MIN, width));
}
