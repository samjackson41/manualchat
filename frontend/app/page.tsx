"use client";

import { Thread } from "@/components/assistant-ui/elements/thread.aui";
import { ThreadList } from "@/components/assistant-ui/elements/thread-list.aui";
import { ManualViewerPanel } from "@/components/manual-viewer";
import { TopBar } from "@/components/top-bar";
import { cn } from "@/lib/utils";
import { useViewer } from "./viewer-runtime";
import { useVehicles } from "./vehicle-runtime";

export default function Home() {
  const {
    open: viewerOpen,
    toggle: onToggleViewer,
    chatHidden,
  } = useViewer();
  const { vehicles, activeVehicleId } = useVehicles();
  const activeVehicleName = vehicles.find(
    (v) => v.vehicle_id === activeVehicleId,
  )?.display_name;

  return (
    <main className="flex h-dvh flex-col">
      <TopBar viewerOpen={viewerOpen} onToggleViewer={onToggleViewer} />

      <div className="flex min-h-0 flex-1">
        <aside className="bg-sidebar border-sidebar-border flex w-64 shrink-0 flex-col border-r">
          <div className="text-muted-foreground border-sidebar-border border-b px-2.5 py-2 text-xs font-medium">
            {activeVehicleName
              ? `${activeVehicleName} Chat History`
              : "Chat History"}
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-2 pt-2 pb-2">
            <ThreadList />
          </div>
        </aside>

        <section className="flex min-h-0 min-w-0 flex-1">
          <div className={cn("min-h-0 min-w-0 flex-1", chatHidden && "hidden")}>
            <Thread />
          </div>
          {viewerOpen && <ManualViewerPanel />}
        </section>
      </div>
    </main>
  );
}