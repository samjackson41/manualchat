"use client";

import { useState } from "react";
import { BookOpenIcon } from "lucide-react";
import { Thread } from "@/components/assistant-ui/elements/thread.aui";
import { ThreadList } from "@/components/assistant-ui/elements/thread-list.aui";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ManualUpload } from "@/components/manual-upload";
import { ManualViewerPanel } from "@/components/manual-viewer";
import { ThemeToggle } from "@/components/theme-toggle";
import { VehicleSelector } from "@/components/vehicle-selector";
import { useModelSelection } from "./chat-runtime";

export default function Home() {
  const { models, model, setModel } = useModelSelection();
  const [viewerOpen, setViewerOpen] = useState(false);

  return (
    <main className="flex h-dvh">
      <aside className="flex w-64 shrink-0 flex-col border-r border-border bg-muted/30">
        <div className="flex items-center justify-between px-3 pt-3 pb-2">
          <h1 className="text-lg font-semibold text-chrome">ManualChat</h1>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
          <ThreadList />
        </div>
      </aside>

      <section className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between gap-3 px-4 py-3">
          <VehicleSelector />

          <div className="flex items-center gap-2">
            <ManualUpload />
            <Button
              variant={viewerOpen ? "secondary" : "outline"}
              aria-pressed={viewerOpen}
              onClick={() => setViewerOpen((open) => !open)}
            >
              <BookOpenIcon /> Manual viewer
            </Button>
            <Select
              value={model}
              items={models.map((option) => ({
                value: option.id,
                label: option.label,
              }))}
              onValueChange={(value) => {
                if (value) setModel(value);
              }}
            >
              <SelectTrigger aria-label="Model selector" className="w-44">
                <SelectValue placeholder="Pick a model" />
              </SelectTrigger>
              <SelectContent>
                {models.map((option) => (
                  <SelectItem key={option.id} value={option.id}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <ThemeToggle />
          </div>
        </header>

        {viewerOpen && <ManualViewerPanel />}

        <div className="min-h-0 flex-1">
          <Thread />
        </div>
      </section>
    </main>
  );
}