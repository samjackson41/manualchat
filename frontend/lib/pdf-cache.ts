// Byte caches for the manual viewer (DECISIONS V6).
//
// Only PDF bytes are cached, never rendered pages: a rendered page costs far
// more memory. Page slices live in a module-level map with an LRU cap. The map
// clears on a reload or a tab close, not when the reader switches threads or
// pane modes. A whole manual is larger, so it lives once per manual in the
// Cache API.
//
// The caches hold Blobs rather than ArrayBuffers. pdfjs transfers the
// ArrayBuffer it reads to its worker, which detaches it, so a second read of
// the same ArrayBuffer throws. A Blob is immutable and can be read again, which
// also keeps the viewer safe under React StrictMode's double mount.

import { manualPagesUrl, manualPdfUrl } from "./api";
import { SLICE_CACHE_ENTRIES } from "./viewer-config";

const WHOLE_CACHE_NAME = "manualchat-manual-pdf";

const sliceBytes = new Map<string, Blob>();

function sliceKey(manualId: string, start: number, end: number): string {
  return `${manualId}:${start}-${end}`;
}

function rememberSlice(key: string, bytes: Blob): void {
  // Re-setting a key moves it to the young end of the map's insertion order,
  // so the first key is always the least recently used one.
  sliceBytes.delete(key);
  sliceBytes.set(key, bytes);
  while (sliceBytes.size > SLICE_CACHE_ENTRIES) {
    const oldest = sliceBytes.keys().next().value;
    if (oldest === undefined) break;
    sliceBytes.delete(oldest);
  }
}

/** The bytes of one page slice, from the map or from the backend. */
export async function loadSliceBytes(
  manualId: string,
  start: number,
  end: number,
): Promise<Blob> {
  const key = sliceKey(manualId, start, end);
  const hit = sliceBytes.get(key);
  if (hit) {
    rememberSlice(key, hit);
    return hit;
  }
  const res = await fetch(manualPagesUrl(manualId, start, end));
  if (!res.ok) {
    throw new Error(`Could not load pages ${start}-${end} (${res.status})`);
  }
  const bytes = await res.blob();
  rememberSlice(key, bytes);
  return bytes;
}

function cacheStorage(): CacheStorage | null {
  // The Cache API needs a secure context, so it is absent on some hosts.
  return typeof caches === "undefined" ? null : caches;
}

/** The whole manual's bytes, from the Cache API or from the backend. */
export async function loadWholeManualBytes(manualId: string): Promise<Blob> {
  const url = manualPdfUrl(manualId);
  const storage = cacheStorage();
  const cache = storage ? await storage.open(WHOLE_CACHE_NAME) : null;

  const hit = cache ? await cache.match(url) : undefined;
  if (hit) return hit.blob();

  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Could not load the manual (${res.status})`);
  }
  const bytes = await res.blob();
  if (cache) {
    // A cache write can fail (quota, private mode); the viewer must still work.
    const store = new Response(bytes, { headers: res.headers });
    await cache.put(url, store).catch(() => undefined);
  }
  return bytes;
}

/** Drops a manual's cached bytes, for when the reader deletes the manual. */
export async function forgetManualBytes(manualId: string): Promise<void> {
  const prefix = `${manualId}:`;
  for (const key of [...sliceBytes.keys()]) {
    if (key.startsWith(prefix)) sliceBytes.delete(key);
  }
  const storage = cacheStorage();
  if (!storage) return;
  const cache = await storage.open(WHOLE_CACHE_NAME);
  await cache.delete(manualPdfUrl(manualId)).catch(() => undefined);
}
