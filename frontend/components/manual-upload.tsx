"use client";

import { useState, type FormEvent } from "react";
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { MANUAL_KINDS, uploadManual, type ManualKind } from "@/lib/api";
import { useVehicles } from "@/app/vehicle-runtime";

const KIND_LABELS: Record<ManualKind, string> = {
  oem: "OEM service manual",
  aftermarket: "Aftermarket guide",
  supplement: "Supplement",
  other: "Other",
};

export function ManualUpload() {
  const { activeVehicleId } = useVehicles();
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [kind, setKind] = useState<ManualKind>("oem");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  function reset() {
    setFile(null);
    setDisplayName("");
    setKind("oem");
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
      await uploadManual({
        file,
        vehicleId: activeVehicleId,
        displayName: trimmed,
        kind,
      });
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
              <Select
                value={kind}
                onValueChange={(value) => {
                  if (value) setKind(value as ManualKind);
                }}
              >
                <SelectTrigger aria-label="Manual kind" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {MANUAL_KINDS.map((option) => (
                    <SelectItem key={option} value={option}>
                      {KIND_LABELS[option]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

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
        </DialogContent>
      </Dialog>
    </>
  );
}