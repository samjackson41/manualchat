"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { listManuals, type Manual } from "@/lib/api";
import { useVehicles } from "./vehicle-runtime";

// The viewer shows the pages an answer cites. The cited page and which manual
// to render are app-wide, so a context carries them from the citation badges
// in the chat to the viewer pane.

type ViewerState = {
  open: boolean;
  citedPage: number | null;
  manualId: string | null;
  // The active vehicle's enabled, fully-ingested manuals, newest first.
  manuals: Manual[];
  loading: boolean;
  openPage: (page: number) => void;
  selectManual: (id: string) => void;
  clearCitation: () => void;
  toggle: () => void;
  close: () => void;
};

const ViewerContext = createContext<ViewerState | null>(null);

export function useViewer(): ViewerState {
  const ctx = useContext(ViewerContext);
  if (!ctx) {
    throw new Error("useViewer must be used inside ViewerProvider");
  }
  return ctx;
}

export function ViewerProvider({ children }: { children: ReactNode }) {
  const { activeVehicleId } = useVehicles();
  const [open, setOpen] = useState(false);
  const [citedPage, setCitedPage] = useState<number | null>(null);
  const [manualId, setManualId] = useState<string | null>(null);
  const [manuals, setManuals] = useState<Manual[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!activeVehicleId) {
      setManuals([]);
      setManualId(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    listManuals()
      .then((all) => {
        if (cancelled) return;
        const viewable = all.filter(
          (manual) =>
            manual.vehicle_id === activeVehicleId &&
            manual.enabled &&
            manual.status === "ready",
        );
        setManuals(viewable);
        // Keep the current choice when it is still viewable; otherwise fall
        // back to the first manual.
        setManualId((current) =>
          viewable.some((manual) => manual.manual_id === current)
            ? current
            : (viewable[0]?.manual_id ?? null),
        );
      })
      .catch(() => {
        // The viewer reads only; a failed refresh must not block the chat.
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeVehicleId, open]);

  const openPage = useCallback((page: number) => {
    setCitedPage(page);
    setOpen(true);
  }, []);

  const selectManual = useCallback((id: string) => setManualId(id), []);

  const clearCitation = useCallback(() => setCitedPage(null), []);

  const toggle = useCallback(() => setOpen((current) => !current), []);

  const close = useCallback(() => setOpen(false), []);

  // Closing the pane ends the cited view, so a slice and a browsed manual
  // never mix and browsing starts clean on the next open.
  useEffect(() => {
    if (!open) setCitedPage(null);
  }, [open]);

  const value = useMemo<ViewerState>(
    () => ({
      open,
      citedPage,
      manualId,
      manuals,
      loading,
      openPage,
      selectManual,
      clearCitation,
      toggle,
      close,
    }),
    [
      open,
      citedPage,
      manualId,
      manuals,
      loading,
      openPage,
      selectManual,
      clearCitation,
      toggle,
      close,
    ],
  );

  return (
    <ViewerContext.Provider value={value}>{children}</ViewerContext.Provider>
  );
}