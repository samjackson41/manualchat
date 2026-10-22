"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { LoaderCircleIcon, UploadIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { VehiclePicker } from "@/components/vehicle-picker";
import {
  getManual,
  listManuals,
  uploadManual,
  type Manual,
} from "@/lib/api";
import {
  formatRemaining,
  ingestRemainingMs,
  ingestStageFraction,
  ingestStageLabel,
  ingestStatusText,
} from "@/lib/ingest-progress";
import { useVehicles } from "@/app/vehicle-runtime";

// Ingest runs in the background after the upload, so the list below refreshes
// while any manual is still processing.
const POLL_MS = 3000;

function statusText(manual: Manual): string {
  if (manual.status === "processing") return ingestStatusText(manual.progress);
  if (manual.status === "ready") return `Ready, ${manual.page_count} pages`;
  return "Ingest failed";
}

/** A determinate bar for a stage with countable work, a moving one without. */
function IngestBar({ fraction }: { fraction: number | null }) {
  return (
    <div className="bg-muted h-1.5 w-full overflow-hidden rounded-full">
      {fraction === null ? (
        <div className="bg-primary h-full w-1/2 animate-pulse rounded-full" />
      ) : (
        <div
          className="bg-primary h-full rounded-full transition-[width] duration-700 ease-out"
          style={{ width: `${fraction * 100}%` }}
        />
      )}
    </div>
  );
}

export function ManualUpload() {
  const { activeVehicleId } = useVehicles();
  const [open, setOpen] = useState(false);
  const [vehicleId, setVehicleId] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<Manual | null>(null);
  const [uploadedId, setUploadedId] = useState<string | null>(null);
  const [watched, setWatched] = useState<Manual | null>(null);
  const [manuals, setManuals] = useState<Manual[]>([]);
  const [stageStartedAt, setStageStartedAt] = useState<number | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const submittingRef = useRef(false);
  const anyProcessing = manuals.some((manual) => manual.status === "processing");

  const watching = watched?.status === "processing";
  const locked = busy || watching;

  const stage = watched?.progress.stage ?? null;
  const remaining =
    watched && stageStartedAt !== null
      ? ingestRemainingMs(watched.progress, Date.now() - stageStartedAt)
      : null;

  useEffect(() => {
    if (!open || !vehicleId) {
      setManuals([]);
      return;
    }
    let cancelled = false;
    listManuals()
      .then((all) => {
        if (!cancelled) {
          setManuals(
            all.filter((manual) => manual.vehicle_id === vehicleId),
          );
        }
      })
      .catch(() => {
        // The list is a convenience. A failed refresh must not block an upload.
      });
    return () => {
      cancelled = true;
    };
  }, [open, vehicleId]);

  useEffect(() => {
    if (!open || !vehicleId || !anyProcessing) return;
    const timer = setInterval(() => {
      listManuals()
        .then((all) =>
          setManuals(
            all.filter((manual) => manual.vehicle_id === vehicleId),
          ),
        )
        .catch(() => {
          // Keep the last known list when a refresh fails.
        });
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [open, vehicleId, anyProcessing]);

  // The estimate measures one stage at a time, so it restarts on each change.
  useEffect(() => {
    setStageStartedAt(stage === null ? null : Date.now());
  }, [stage]);

  // The watched manual is polled on its own, so the toast and the panel keep up
  // while the dialog is closed.
  useEffect(() => {
    if (!uploadedId) return;
    let cancelled = false;
    const refresh = () => {
      getManual(uploadedId)
        .then((record) => {
          if (!cancelled) setWatched(record);
        })
        .catch(() => {
          // Keep the last known record when a refresh fails.
        });
    };
    refresh();
    const timer = setInterval(refresh, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [uploadedId]);

  useEffect(() => {
    if (!watched || watched.status === "processing") return;
    if (watched.status === "ready") {
      setDone(watched);
      setFile(null);
      setDisplayName("");
      setDescription("");
    } else {
      setError("The ingest of this manual failed. Read the backend log.");
    }
    setUploadedId(null);
    setWatched(null);
  }, [watched]);

  function reset() {
    setVehicleId(activeVehicleId);
    setFile(null);
    setDisplayName("");
    setDescription("");
    setBusy(false);
    setError(null);
    setDone(null);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (submittingRef.current) return;
    const trimmed = displayName.trim();
    if (!vehicleId || !file || !trimmed) return;
    submittingRef.current = true;
    setBusy(true);
    setError(null);
    setDone(null);
    try {
      const manual = await uploadManual({
        file,
        vehicleId,
        displayName: trimmed,
        description: description.trim() || undefined,
      });
      setManuals((previous) => [
        manual,
        ...previous.filter((item) => item.manual_id !== manual.manual_id),
      ]);
      setUploadedId(manual.manual_id);
      setWatched(manual);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      submittingRef.current = false;
      setBusy(false);
    }
  }

  return (
    <>
      <Button
        variant="outline"
        aria-label="Upload manual"
        onClick={() => {
          reset();
          setOpen(true);
        }}
      >
        <UploadIcon /> Upload manual
      </Button>

      <Dialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          if (!next) reset();
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Upload a manual</DialogTitle>
          </DialogHeader>

          <form onSubmit={submit} className="flex min-w-0 flex-col gap-3">
            {locked ? (
              <div className="flex flex-col gap-3 py-2">
                <p className="truncate text-sm font-medium">
                  {watched?.source_filename ?? file?.name ?? "Manual"}
                </p>
                <p className="text-sm">
                  {watched
                    ? `${ingestStageLabel(watched.progress)}…`
                    : "Uploading…"}
                </p>
                <IngestBar
                  fraction={
                    watched ? ingestStageFraction(watched.progress) : null
                  }
                />
                {remaining !== null && (
                  <p className="text-muted-foreground text-xs">
                    {formatRemaining(remaining)}
                  </p>
                )}
              </div>
            ) : (
              <>
                <VehiclePicker
                  value={vehicleId}
                  onValueChange={(id) => setVehicleId(id)}
                  triggerClassName="w-full text-xs"
                />
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="application/pdf"
                  className="hidden"
                  onChange={(event) =>
                    setFile(event.target.files?.[0] ?? null)
                  }
                />
                <div className="flex items-center gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => fileInputRef.current?.click()}
                  >
                    Browse…
                  </Button>
                  <span className="text-muted-foreground min-w-0 flex-1 truncate text-xs">
                    {file ? file.name : "No file selected"}
                  </span>
                </div>
                <Input
                  value={displayName}
                  onChange={(event) => setDisplayName(event.target.value)}
                  placeholder="Manual name, e.g. Rhino 700 service manual"
                />
                <Textarea
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  placeholder="Description (optional)"
                  className="min-h-12"
                />

                {error && <p className="text-destructive text-sm">{error}</p>}
                {done && (
                  <p className="text-muted-foreground text-sm">
                    {done.display_name} is ready: {done.page_count} pages,{" "}
                    {done.chunk_count} chunks.
                  </p>
                )}
              </>
            )}

            <DialogFooter>
              <Button
                type="submit"
                disabled={locked || !vehicleId || !file || !displayName.trim()}
              >
                {busy ? "Uploading…" : watching ? "Processing…" : "Upload"}
              </Button>
            </DialogFooter>
          </form>

          {!locked && manuals.length > 0 && (
            <div className="flex flex-col gap-1.5">
              <p className="text-muted-foreground text-xs font-medium">
                Manuals for this vehicle
              </p>
              <ul className="flex max-h-40 flex-col gap-1 overflow-y-auto">
                {manuals.map((manual) => (
                  <li
                    key={manual.manual_id}
                    className="flex items-center justify-between gap-2 text-sm"
                  >
                    <span className="min-w-0 truncate">{manual.display_name}</span>
                    <span className="text-muted-foreground shrink-0">
                      {statusText(manual)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {!open && watching && (
        <Button
          variant="outline"
          onClick={() => setOpen(true)}
          className="fixed top-16 left-1/2 z-50 -translate-x-1/2 shadow-lg"
        >
          <LoaderCircleIcon className="text-primary animate-spin" />
          Manual upload in progress…
        </Button>
      )}
    </>
  );
}