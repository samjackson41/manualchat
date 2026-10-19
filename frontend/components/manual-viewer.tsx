"use client";

import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type RefObject,
} from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/TextLayer.css";
import "react-pdf/dist/Page/AnnotationLayer.css";
import { BookOpenIcon, LoaderCircleIcon, XIcon } from "lucide-react";

import { useViewer } from "@/app/viewer-runtime";
import { manualPagesUrl, manualPdfUrl } from "@/lib/api";
import {
  PAGE_ASPECT,
  SLICE_PAGES_AFTER,
  SLICE_PAGES_BEFORE,
} from "@/lib/viewer-config";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

// A window of pages from one stored PDF: the bytes plus, for each page of the
// document, the physical PDF page number it holds. A window is either the
// cited slice (DECISIONS V1) or the whole manual (DECISIONS V2).
type PdfWindow = {
  // Names one fetched window. A new key mounts a new <Document>, so a live
  // document never has its `file` swapped for another window.
  key: string;
  manualId: string;
  pages: number[];
  data: ArrayBuffer;
};

// The 1px border on each side of a page wrapper, taken off the pane width so a
// page fits without a horizontal scrollbar.
const PAGE_BORDER = 2;

function EmptyState({ children }: { children: React.ReactNode }) {
  return (
    <div className="border-border bg-muted/40 flex h-full flex-col items-center justify-center gap-2 rounded-lg border border-dashed p-6 text-center">
      <BookOpenIcon className="text-gold size-8" />
      {children}
    </div>
  );
}

function Loader({ label }: { label: string }) {
  return (
    <div className="flex h-full items-center justify-center gap-2 text-sm text-muted-foreground">
      <LoaderCircleIcon className="size-4 animate-spin" />
      {label}
    </div>
  );
}

// Measures an element's content width so pages can be rendered to fit the pane.
function useElementWidth<T extends HTMLElement>(): [RefObject<T>, number] {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) setWidth(entry.contentRect.width);
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return [ref, width];
}

// One page in a lazy list: a placeholder holds the page's place until it comes
// near the viewport, then the real <Page> mounts. This keeps a 500-page manual
// responsive instead of rasterising every page at once.
function LazyPage({
  pageNumber,
  label,
  width,
  isCited,
  root,
}: {
  pageNumber: number;
  label: number;
  width: number;
  isCited: boolean;
  root: RefObject<HTMLElement>;
}) {
  const holder = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const node = holder.current;
    if (!node) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { root: root.current, rootMargin: "800px 0px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [root]);

  // The cited page opens the slice, so bring it into view once it renders.
  useEffect(() => {
    if (visible && isCited) {
      holder.current?.scrollIntoView({ block: "start", behavior: "smooth" });
    }
  }, [visible, isCited]);

  return (
    <div
      ref={holder}
      style={visible ? undefined : { height: width * PAGE_ASPECT }}
      className={cn(
        "mb-3 rounded-md border",
        isCited ? "border-primary ring-primary/30 ring-2" : "border-border",
      )}
    >
      {visible && (
        <Page
          pageNumber={pageNumber}
          width={width}
          renderAnnotationLayer={false}
          renderTextLayer
        />
      )}
      {visible && (
        <p className="text-muted-foreground mt-1 text-center text-xs">{label}</p>
      )}
    </div>
  );
}

// Renders a fetched window. Pages render at the pane width, so the reader never
// scrolls sideways at the default zoom.
function PageList({
  doc,
  width,
  citedPage,
  root,
}: {
  doc: PdfWindow;
  width: number;
  citedPage: number | null;
  root: RefObject<HTMLElement>;
}) {
  return (
    <Document
      key={doc.key}
      file={doc.data}
      loading={<Loader label="Rendering…" />}
    >
      {doc.pages.map((page, index) => (
        <LazyPage
          key={page}
          pageNumber={index + 1}
          label={page}
          width={width}
          isCited={page === citedPage}
          root={root}
        />
      ))}
    </Document>
  );
}

export function ManualViewerPanel() {
  const { citedPage, manualId, manuals, selectManual, close } = useViewer();
  const [slice, setSlice] = useState<PdfWindow | null>(null);
  const [whole, setWhole] = useState<PdfWindow | null>(null);
  const [wholeRequested, setWholeRequested] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [wholeError, setWholeError] = useState<string | null>(null);
  const [scrollRef, containerWidth] = useElementWidth<HTMLDivElement>();

  const manual = manuals.find((item) => item.manual_id === manualId) ?? null;
  const manualKey = manual?.manual_id ?? null;
  const pageCount = manual?.page_count ?? 0;
  // Pages render at the pane width, so a page fits without a sideways scroll.
  const pageWidth = Math.max(80, containerWidth - PAGE_BORDER);

  // A new manual drops the manual that was loaded whole, so its pages never
  // show under another manual's name.
  useEffect(() => {
    setWhole(null);
    setWholeError(null);
    setWholeRequested(false);
  }, [manualKey]);

  // The window a citation opens: the cited page plus the configured pages on
  // each side (DECISIONS V1).
  const sliceWindow = useMemo(() => {
    if (!manual || citedPage === null) return null;
    const start = Math.max(1, citedPage - SLICE_PAGES_BEFORE);
    const end = Math.min(manual.page_count, citedPage + SLICE_PAGES_AFTER);
    return start <= end ? { start, end } : null;
  }, [manual, citedPage]);

  const sliceLabel = sliceWindow
    ? sliceWindow.start === sliceWindow.end
      ? `Pg ${sliceWindow.start}`
      : `Pgs ${sliceWindow.start}-${sliceWindow.end}`
    : "";

  useEffect(() => {
    if (!manualKey || !sliceWindow) {
      setSlice(null);
      return;
    }
    const { start, end } = sliceWindow;

    let cancelled = false;
    setError(null);
    const key = `${manualKey}:${start}-${end}`;
    fetch(manualPagesUrl(manualKey, start, end))
      .then((res) => {
        if (!res.ok) {
          throw new Error(`Could not load pages ${start}-${end} (${res.status})`);
        }
        return res.arrayBuffer();
      })
      .then((buffer) => {
        if (cancelled) return;
        // A repeated window keeps the buffer it already holds: react-pdf
        // reloads on a new `file` object even when the bytes are the same.
        setSlice((current) =>
          current?.key === key
            ? current
            : {
                key,
                manualId: manualKey,
                pages: Array.from(
                  { length: end - start + 1 },
                  (_, index) => start + index,
                ),
                data: buffer,
              },
        );
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load pages");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [manualKey, sliceWindow]);

  // Hides the pages of another manual while the replacement window loads.
  const shownSlice = slice && slice.manualId === manualKey ? slice : null;

  // The whole manual loads only when the reader asks for it (DECISIONS V2).
  useEffect(() => {
    if (!wholeRequested || !manualKey || pageCount === 0) return;
    let cancelled = false;
    setWholeError(null);
    fetch(manualPdfUrl(manualKey))
      .then((res) => {
        if (!res.ok) {
          throw new Error(`Could not load the manual (${res.status})`);
        }
        return res.arrayBuffer();
      })
      .then((buffer) => {
        if (cancelled) return;
        setWhole({
          key: `whole:${manualKey}`,
          manualId: manualKey,
          pages: Array.from({ length: pageCount }, (_, index) => index + 1),
          data: buffer,
        });
      })
      .catch((err) => {
        if (!cancelled) {
          setWholeError(
            err instanceof Error ? err.message : "Could not load the manual",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [wholeRequested, manualKey, pageCount]);

  const shownWhole = whole && whole.manualId === manualKey ? whole : null;

  return (
    <aside
      aria-label="Manual viewer"
      className="bg-card border-border flex w-[26rem] max-w-[55%] shrink-0 flex-col border-l"
    >
      <header className="border-border flex items-center justify-between gap-2 border-b px-3 py-2">
        <div className="flex min-w-0 items-center gap-2">
          <BookOpenIcon className="text-primary size-4 shrink-0" />
          <h2 className="shrink-0 text-sm font-semibold">Manual viewer</h2>
          {citedPage !== null && manual ? (
            <span className="text-muted-foreground min-w-0 truncate text-sm">
              {manual.display_name}, {sliceLabel}
            </span>
          ) : (
            <Select
              value={manualId ?? undefined}
              items={manuals.map((item) => ({
                value: item.manual_id,
                label: item.display_name,
              }))}
              onValueChange={(value) => {
                if (value) selectManual(value);
              }}
            >
              <SelectTrigger
                aria-label="Manual selector"
                className="w-40"
                disabled={manuals.length === 0}
              >
                <SelectValue placeholder="Pick a manual" />
              </SelectTrigger>
              <SelectContent>
                {manuals.map((item) => (
                  <SelectItem key={item.manual_id} value={item.manual_id}>
                    <span className="block truncate">{item.display_name}</span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label="Close manual viewer"
          onClick={close}
        >
          <XIcon />
        </Button>
      </header>

      <div ref={scrollRef} className="min-h-0 flex-1 overflow-auto p-3">
        {!manual && (
          <EmptyState>
            <p className="text-sm font-medium">No manual to show</p>
            <p className="text-muted-foreground max-w-xs text-sm">
              Upload a manual and finish its ingest to view pages here.
            </p>
          </EmptyState>
        )}

        {manual && citedPage === null && !wholeRequested && (
          <EmptyState>
            <p className="text-sm font-medium">Cited pages load here</p>
            <p className="text-muted-foreground max-w-xs text-sm">
              Click a [Page N] badge in the chat to open that page in this pane.
            </p>
            <Tooltip>
              <TooltipTrigger
                render={
                  <Button
                    variant="outline"
                    size="sm"
                    className="mt-1"
                    onClick={() => setWholeRequested(true)}
                  />
                }
              >
                <BookOpenIcon /> View whole manual
              </TooltipTrigger>
              <TooltipContent>Whole manual may be slow to load</TooltipContent>
            </Tooltip>
          </EmptyState>
        )}

        {manual && citedPage === null && wholeRequested && wholeError && (
          <EmptyState>
            <p className="text-sm font-medium text-destructive">
              Could not load the manual
            </p>
            <p className="text-muted-foreground max-w-xs text-sm">
              {wholeError}
            </p>
          </EmptyState>
        )}

        {manual &&
          citedPage === null &&
          wholeRequested &&
          !wholeError &&
          (!shownWhole || containerWidth === 0) && (
            <Loader label="Loading manual…" />
          )}

        {manual &&
          citedPage === null &&
          wholeRequested &&
          shownWhole &&
          containerWidth > 0 && (
            <>
              <p className="text-muted-foreground mb-2 text-xs">
                {manual.display_name} · {pageCount} pages
              </p>
              <PageList
                doc={shownWhole}
                width={pageWidth}
                citedPage={null}
                root={scrollRef}
              />
            </>
          )}

        {manual && citedPage !== null && error && (
          <EmptyState>
            <p className="text-sm font-medium text-destructive">
              Could not load the page
            </p>
            <p className="text-muted-foreground max-w-xs text-sm">{error}</p>
          </EmptyState>
        )}

        {manual &&
          citedPage !== null &&
          !error &&
          (!shownSlice || containerWidth === 0) && <Loader label="Loading pages…" />}

        {manual && citedPage !== null && shownSlice && containerWidth > 0 && (
          <>
            <p className="text-muted-foreground mb-2 text-xs">
              Page {citedPage} of {pageCount}
            </p>
            <PageList
              doc={shownSlice}
              width={pageWidth}
              citedPage={citedPage}
              root={scrollRef}
            />
          </>
        )}
      </div>
    </aside>
  );
}