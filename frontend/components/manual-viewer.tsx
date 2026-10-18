"use client";

import { useEffect, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/TextLayer.css";
import "react-pdf/dist/Page/AnnotationLayer.css";
import { BookOpenIcon, LoaderCircleIcon, XIcon } from "lucide-react";

import { useViewer } from "@/app/viewer-runtime";
import { manualPagesUrl } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
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

// The viewer shows the cited page plus two pages on each side (DECISIONS V1).
const SLICE_RADIUS = 2;

function EmptyState({ children }: { children: React.ReactNode }) {
  return (
    <div className="border-border bg-muted/40 flex h-full flex-col items-center justify-center gap-2 rounded-lg border border-dashed p-6 text-center">
      <BookOpenIcon className="text-gold size-8" />
      {children}
    </div>
  );
}

export function ManualViewerPanel() {
  const { citedPage, manualId, manuals, selectManual, close } = useViewer();
  const [pdfData, setPdfData] = useState<ArrayBuffer | null>(null);
  const [sliceStart, setSliceStart] = useState<number | null>(null);
  const [numPages, setNumPages] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);
  const citedRef = useRef<HTMLDivElement>(null);

  const manual =
    manuals.find((item) => item.manual_id === manualId) ?? null;

  useEffect(() => {
    if (!manual || citedPage === null) {
      setPdfData(null);
      setSliceStart(null);
      return;
    }
    const start = Math.max(1, citedPage - SLICE_RADIUS);
    const end = Math.min(manual.page_count, citedPage + SLICE_RADIUS);
    if (start > end) {
      setPdfData(null);
      setSliceStart(null);
      return;
    }

    let cancelled = false;
    setError(null);
    fetch(manualPagesUrl(manual.manual_id, start, end))
      .then((res) => {
        if (!res.ok) {
          throw new Error(`Could not load pages ${start}-${end} (${res.status})`);
        }
        return res.arrayBuffer();
      })
      .then((buffer) => {
        if (!cancelled) {
          setSliceStart(start);
          setPdfData(buffer);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load pages");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [manual, citedPage]);

  useEffect(() => {
    if (pdfData && citedRef.current) {
      citedRef.current.scrollIntoView({ block: "start", behavior: "smooth" });
    }
  }, [pdfData, numPages]);

  return (
    <aside
      aria-label="Manual viewer"
      className="bg-card border-border flex w-[26rem] max-w-[55%] shrink-0 flex-col border-l"
    >
      <header className="border-border flex items-center justify-between gap-2 border-b px-3 py-2">
        <div className="flex min-w-0 items-center gap-2">
          <BookOpenIcon className="text-primary size-4 shrink-0" />
          <h2 className="shrink-0 text-sm font-semibold">Manual viewer</h2>
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

      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        {!manual && (
          <EmptyState>
            <p className="text-sm font-medium">No manual to show</p>
            <p className="text-muted-foreground max-w-xs text-sm">
              Upload a manual and finish its ingest to view pages here.
            </p>
          </EmptyState>
        )}

        {manual && citedPage === null && (
          <EmptyState>
            <p className="text-sm font-medium">Cited pages load here</p>
            <p className="text-muted-foreground max-w-xs text-sm">
              Click a [Page N] badge in the chat to open that page in this pane.
            </p>
          </EmptyState>
        )}

        {manual && citedPage !== null && error && (
          <EmptyState>
            <p className="text-sm font-medium text-destructive">
              Could not load the page
            </p>
            <p className="text-muted-foreground max-w-xs text-sm">{error}</p>
          </EmptyState>
        )}

        {manual && citedPage !== null && !error && !pdfData && (
          <div className="flex h-full items-center justify-center gap-2 text-sm text-muted-foreground">
            <LoaderCircleIcon className="size-4 animate-spin" />
            Loading pages…
          </div>
        )}

        {manual && citedPage !== null && pdfData && sliceStart !== null && (
          <>
            <p className="text-muted-foreground mb-2 text-xs">
              Page {citedPage} of {manual.page_count} · {manual.display_name}
            </p>
            <Document
              file={pdfData}
              loading={
                <div className="flex items-center justify-center gap-2 py-6 text-sm text-muted-foreground">
                  <LoaderCircleIcon className="size-4 animate-spin" />
                  Rendering…
                </div>
              }
              onLoadSuccess={({ numPages: count }) => setNumPages(count)}
            >
              {Array.from({ length: numPages }, (_, index) => {
                const page = sliceStart + index;
                const isCited = page === citedPage;
                return (
                  <div
                    key={page}
                    ref={isCited ? citedRef : undefined}
                    className={cn(
                      "mb-3 rounded-md border bg-white p-2",
                      isCited
                        ? "border-primary ring-primary/30 ring-2"
                        : "border-border",
                    )}
                  >
                    <Page
                      pageNumber={index + 1}
                      renderAnnotationLayer={false}
                      renderTextLayer
                    />
                    <p className="text-muted-foreground mt-1 text-center text-xs">
                      {page}
                    </p>
                  </div>
                );
              })}
            </Document>
          </>
        )}
      </div>
    </aside>
  );
}