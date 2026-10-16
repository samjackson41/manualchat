"use client";

import { BookOpenIcon } from "lucide-react";

export function ManualViewerPanel() {
  return (
    <section className="border-b border-border bg-muted/30 px-4 py-3">
      <div className="flex h-64 items-center justify-center rounded-lg border border-dashed border-border">
        <div className="flex flex-col items-center gap-2 text-center">
          <BookOpenIcon className="size-8 text-gold" />
          <p className="text-sm font-medium">Manual viewer</p>
          <p className="max-w-xs text-sm text-muted-foreground">
            The page-slice viewer is not built yet. Cited pages will load here
            (DECISIONS V1).
          </p>
        </div>
      </div>
    </section>
  );
}