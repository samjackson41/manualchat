"use client";

import { useEffect, useState, type FormEvent } from "react";
import { UploadIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  listManuals,
  uploadManual,
  type Manual,
} from "@/lib/api";
import { useVehicles } from "@/app/vehicle-runtime";

// Ingest runs in the background after the upload, so the list below refreshes
// while any manual is still processing.
const POLL_MS = 3000;

function statusText(manual: Manual): string {
  if (manual.status === "processing") return "Processing…";
  if (manual.status === "ready") return `Ready, ${manual.page_count} pages`;
  return "Ingest failed";
}

export function ManualUpload() {
  const { activeVehicleId } = useVehicles();
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [manuals, setManuals] = useState<Manual[]>([]);
  const anyProcessing = manuals.some((manual) => manual.status === "processing");

  useEffect(() => {
    if (!open || !activeVehicleId) {
      setManuals([]);
      return;
    }
    let cancelled = false;
    listManuals()
      .then((all) => {
        if (!cancelled) {
          setManuals(
            all.filter((manual) => manual.vehicle_id === activeVehicleId),
          );
        }
      })
      .catch(() => {
        // The list is a convenience. A failed refresh must not block an upload.
      });
    return () => {
      cancelled = true;
    };
  }, [open, activeVehicleId]);

  useEffect(() => {
    if (!open || !activeVehicleId || !anyProcessing) return;
    const timer = setInterval(() => {
      listManuals()
        .then((all) =>
          setManuals(
            all.filter((manual) => manual.vehicle_id === activeVehicleId),
          ),
        )
        .catch(() => {
          // Keep the last known list when a refresh fails.
        });
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [open, activeVehicleId, anyProcessing]);

  function reset() {
    setFile(null);
    setDisplayName("");
    setDescription("");
    setBusy(false);
    setError(null);
    setDone(false);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const trimmed = displayName.trim();
    if (!activeVehicleId || !file || !trimmed) return;
    setBusy(true);
    setError(null);
    try {
      const manual = await uploadManual({
        file,
        vehicleId: activeVehicleId,
        displayName: trimmed,
        description: description.trim() || undefined,
      });
      setManuals((previous) => [
        manual,
        ...previous.filter((item) => item.manual_id !== manual.manual_id),
      ]);
      setDone(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
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

          {activeVehicleId ? (
            <form onSubmit={submit} className="flex flex-col gap-3">
              <input
                type="file"
                accept="application/pdf"
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              />
              <Input
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                placeholder="Manual name, e.g. Rhino 700 service manual"
              />
              <Input
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="Description (optional), e.g. 2009 factory service manual"
              />

              {error && <p className="text-sm text-destructive">{error}</p>}
              {done && (
                <p className="text-sm text-muted-foreground">
                  Manual uploaded.
                </p>
              )}

              <DialogFooter>
                <Button
                  type="submit"
                  disabled={!file || !displayName.trim() || busy}
                >
                  Upload
                </Button>
              </DialogFooter>
            </form>
          ) : (
            <p className="text-sm text-muted-foreground">
              Add a vehicle before uploading a manual.
            </p>
          )}

          {manuals.length > 0 && (
            <div className="flex flex-col gap-1.5">
              <p className="text-xs font-medium text-muted-foreground">
                Manuals for this vehicle
              </p>
              <ul className="flex max-h-40 flex-col gap-1 overflow-y-auto">
                {manuals.map((manual) => (
                  <li
                    key={manual.manual_id}
                    className="flex items-center justify-between gap-2 text-sm"
                  >
                    <span className="truncate">{manual.display_name}</span>
                    <span className="shrink-0 text-muted-foreground">
                      {statusText(manual)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}