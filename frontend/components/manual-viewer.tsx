"use client";

import { BookOpenIcon, XIcon } from "lucide-react";
import { Button } from "@/components/ui/button";

export function ManualViewerPanel({ onClose }: { onClose: () => void }) {
  return (
    <aside
      aria-label="Manual viewer"
      className="bg-card border-border flex w-[26rem] max-w-[55%] shrink-0 flex-col border-l"
    >
      <header className="border-border flex items-center justify-between gap-2 border-b px-3 py-2">
        <div className="flex items-center gap-2">
          <BookOpenIcon className="text-primary size-4" />
          <h2 className="text-sm font-semibold">Manual viewer</h2>
        </div>
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label="Close manual viewer"
          onClick={onClose}
        >
          <XIcon />
        </Button>
      </header>

      <div className="min-h-0 flex-1 p-3">
        <div className="border-border bg-muted/40 flex h-full flex-col items-center justify-center gap-2 rounded-lg border border-dashed p-6 text-center">
          <BookOpenIcon className="text-gold size-8" />
          <p className="text-sm font-medium">Cited pages load here</p>
          <p className="text-muted-foreground max-w-xs text-sm">
            The page-slice viewer is not built yet. The pages the answer cites
            will open in this pane (DECISIONS V1).
          </p>
        </div>
      </div>
    </aside>
  );
}