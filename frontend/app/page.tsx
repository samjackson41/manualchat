"use client";

import { useState } from "react";
import Image from "next/image";
import logo from "@/assets/manual-chat-logo.svg";
import { Thread } from "@/components/assistant-ui/elements/thread.aui";
import { ThreadList } from "@/components/assistant-ui/elements/thread-list.aui";
import { ManualViewerPanel } from "@/components/manual-viewer";
import { TopBar } from "@/components/top-bar";

export default function Home() {
  const [viewerOpen, setViewerOpen] = useState(false);

  return (
    <main className="flex h-dvh flex-col">
      <TopBar
        viewerOpen={viewerOpen}
        onToggleViewer={() => setViewerOpen((open) => !open)}
      />

      <div className="flex min-h-0 flex-1">
        <aside className="bg-sidebar border-sidebar-border flex w-64 shrink-0 flex-col border-r">
          <div className="flex items-center px-3 pt-3 pb-2">
            <Image
              src={logo}
              alt="ManualChat"
              width={36}
              height={36}
              unoptimized
              priority
              className="size-9"
            />
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
            <ThreadList />
          </div>
        </aside>

        <section className="flex min-h-0 min-w-0 flex-1">
          <div className="min-h-0 min-w-0 flex-1">
            <Thread />
          </div>
          {viewerOpen && (
            <ManualViewerPanel onClose={() => setViewerOpen(false)} />
          )}
        </section>
      </div>
    </main>
  );
}