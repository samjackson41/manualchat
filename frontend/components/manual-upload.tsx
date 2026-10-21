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
import { listManuals, uploadManual, type Manual } from "@/lib/api";
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
  const [vehicleId, setVehicleId] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [manuals, setManuals] = useState<Manual[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const submittingRef = useRef(false);
  const anyProcessing = manuals.some((manual) => manual.status === "processing");

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

  function reset() {
    setVehicleId(activeVehicleId);
    setFile(null);
    setDisplayName("");
    setDescription("");
    setBusy(false);
    setError(null);
    setDone(false);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (submittingRef.current) return;
    const trimmed = displayName.trim();
    if (!vehicleId || !file || !trimmed) return;
    submittingRef.current = true;
    setBusy(true);
    setError(null);
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
      setDone(true);
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

          {busy ? (
            <div className="flex flex-col items-center gap-3 py-6">
              <LoaderCircleIcon className="text-primary size-6 animate-spin" />
              <p className="text-sm">
                Uploading {file?.name ?? "manual"}…
              </p>
              <div className="bg-muted h-1.5 w-full overflow-hidden rounded-full">
                <div className="bg-primary h-full w-1/2 animate-pulse rounded-full" />
              </div>
            </div>
          ) : (
            <form onSubmit={submit} className="flex flex-col gap-3">
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
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
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
                  Manual uploaded.
                </p>
              )}

              <DialogFooter>
                <Button
                  type="submit"
                  disabled={!vehicleId || !file || !displayName.trim()}
                >
                  Upload
                </Button>
              </DialogFooter>
            </form>
          )}

          {!busy && manuals.length > 0 && (
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
                    <span className="truncate">{manual.display_name}</span>
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
    </>
  );
}