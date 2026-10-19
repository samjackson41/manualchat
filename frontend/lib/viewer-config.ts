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
