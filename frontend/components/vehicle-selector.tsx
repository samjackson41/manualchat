"use client";

import { useEffect, useState, type FormEvent } from "react";
import { CheckIcon, PencilIcon, TrashIcon, XIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useVehicles } from "@/app/vehicle-runtime";
import { VehiclePicker } from "@/components/vehicle-picker";
import { forgetManualBytes } from "@/lib/pdf-cache";
import { ingestStatusText } from "@/lib/ingest-progress";
import {
  deleteManual,
  listManuals,
  renameManual,
  setManualEnabled,
  type Manual,
  type Vehicle,
} from "@/lib/api";

const POLL_MS = 3000;

function manualStatusText(manual: Manual): string {
  if (manual.status === "processing")
    return ingestStatusText(manual.progress);
  if (manual.status === "ready")
    return `Ready, ${manual.page_count} pages, ${manual.chunk_count} chunks`;
  return "Ingest failed";
}

export function VehicleSelector() {
  const {
    vehicles,
    activeVehicleId,
    selectVehicle,
    renameVehicle,
    removeVehicle,
  } = useVehicles();

  const activeVehicle = vehicles.find(
    (v) => v.vehicle_id === activeVehicleId,
  );

  return (
    <div className="flex items-center gap-1.5">
      <VehiclePicker value={activeVehicleId} onValueChange={selectVehicle} />

      {activeVehicle && (
        <ManageVehicleDialog
          vehicle={activeVehicle}
          onRename={(name) => renameVehicle(activeVehicle.vehicle_id, name)}
          onDelete={() => removeVehicle(activeVehicle.vehicle_id)}
        />
      )}
    </div>
  );
}

function ManageVehicleDialog({
  vehicle,
  onRename,
  onDelete,
}: {
  vehicle: Vehicle;
  onRename: (name: string) => Promise<unknown>;
  onDelete: () => Promise<unknown>;
}) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState(vehicle.display_name);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [manuals, setManuals] = useState<Manual[]>([]);
  const [manualError, setManualError] = useState<string | null>(null);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [busyManualId, setBusyManualId] = useState<string | null>(null);
  // The manual whose title is showing as an editable field, and the draft name.
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");

  const anyProcessing = manuals.some((manual) => manual.status === "processing");

  // Refresh on open, then poll while any manual is still processing.
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    async function load() {
      try {
        const all = await listManuals();
        if (cancelled) return;
        setManuals(all.filter((m) => m.vehicle_id === vehicle.vehicle_id));
        setManualError(null);
      } catch {
        if (!cancelled) setManualError("Could not load manuals");
      }
    }
    load();
    if (!anyProcessing) return () => {
      cancelled = true;
    };
    const timer = setInterval(load, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [open, anyProcessing, vehicle.vehicle_id]);

  async function submitRename(event: FormEvent) {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed || trimmed === vehicle.display_name) {
      setOpen(false);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await onRename(trimmed);
      setOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not rename vehicle");
    } finally {
      setBusy(false);
    }
  }

  async function submitDelete() {
    setBusy(true);
    setError(null);
    try {
      await onDelete();
      setOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete vehicle");
      setBusy(false);
    }
  }

  async function toggleManual(manual: Manual) {
    setBusyManualId(manual.manual_id);
    setManualError(null);
    try {
      const updated = await setManualEnabled(manual.manual_id, !manual.enabled);
      setManuals((prev) =>
        prev.map((m) => (m.manual_id === updated.manual_id ? updated : m)),
      );
    } catch (err) {
      setManualError(
        err instanceof Error ? err.message : "Could not update manual",
      );
    } finally {
      setBusyManualId(null);
    }
  }

  async function removeManual(manual: Manual) {
    setBusyManualId(manual.manual_id);
    setManualError(null);
    try {
      await deleteManual(manual.manual_id);
      // The viewer must not serve the deleted manual's bytes from its caches.
      await forgetManualBytes(manual.manual_id);
      setManuals((prev) => prev.filter((m) => m.manual_id !== manual.manual_id));
      setConfirmId(null);
    } catch (err) {
      setManualError(
        err instanceof Error ? err.message : "Could not delete manual",
      );
    } finally {
      setBusyManualId(null);
    }
  }

  function startManualRename(manual: Manual) {
    setRenamingId(manual.manual_id);
    setRenameValue(manual.display_name);
  }

  function cancelManualRename() {
    setRenamingId(null);
    setRenameValue("");
  }

  async function submitManualRename(manual: Manual) {
    const trimmed = renameValue.trim();
    // An empty or unchanged draft is not a rename, so close without a request.
    if (!trimmed || trimmed === manual.display_name) {
      cancelManualRename();
      return;
    }
    setBusyManualId(manual.manual_id);
    setManualError(null);
    try {
      const updated = await renameManual(manual.manual_id, trimmed);
      setManuals((prev) =>
        prev.map((m) => (m.manual_id === updated.manual_id ? updated : m)),
      );
      cancelManualRename();
    } catch (err) {
      setManualError(
        err instanceof Error ? err.message : "Could not rename manual",
      );
    } finally {
      setBusyManualId(null);
    }
  }

  return (
    <>
      <Button
        variant="outline"
        size="icon"
        aria-label="Manage vehicle"
        onClick={() => {
          setName(vehicle.display_name);
          setConfirmId(null);
          cancelManualRename();
          setOpen(true);
        }}
      >
        <PencilIcon />
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Manage vehicle</DialogTitle>
          </DialogHeader>
          <form onSubmit={submitRename} className="flex gap-2">
            <Input
              value={name}
              onChange={(event) => setName(event.target.value)}
              aria-label="Vehicle name"
            />
            <Button type="submit" variant="outline" disabled={busy}>
              Rename
            </Button>
          </form>
          <div className="min-w-0 space-y-0.5 break-words text-xs text-muted-foreground">
            <p>Vehicle ID: {vehicle.vehicle_id}</p>
            <p>User ID: {vehicle.user_id}</p>
            <p>
              Created:{" "}
              {new Date(vehicle.created_at).toLocaleString(undefined, {
                dateStyle: "medium",
                timeStyle: "short",
              })}
            </p>
          </div>
          <div className="flex min-w-0 flex-col gap-2">
            <p className="text-sm font-medium">Manuals</p>
            {manualError && (
              <p className="text-sm text-destructive">{manualError}</p>
            )}
            {manuals.length === 0 && !manualError && (
              <p className="text-sm text-muted-foreground">No manuals yet.</p>
            )}
            <ul className="flex max-h-[40vh] min-w-0 flex-col gap-2 overflow-y-auto">
              {manuals.map((manual) => (
                <li
                  key={manual.manual_id}
                  className="flex min-w-0 items-center justify-between gap-2 rounded-md border p-2"
                >
                  <div className="min-w-0">
                    {renamingId === manual.manual_id ? (
                      <form
                        className="flex items-center gap-1"
                        onSubmit={(event) => {
                          event.preventDefault();
                          void submitManualRename(manual);
                        }}
                      >
                        <Input
                          value={renameValue}
                          onChange={(event) => setRenameValue(event.target.value)}
                          onKeyDown={(event) => {
                            if (event.key === "Escape") cancelManualRename();
                          }}
                          autoFocus
                          aria-label={`New name for ${manual.display_name}`}
                          className="h-7 min-w-0 flex-1 text-sm"
                        />
                        <Button
                          type="submit"
                          variant="ghost"
                          size="icon-xs"
                          aria-label={`Save name for ${manual.display_name}`}
                          disabled={busyManualId !== null}
                        >
                          <CheckIcon />
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon-xs"
                          aria-label="Cancel rename"
                          onClick={cancelManualRename}
                        >
                          <XIcon />
                        </Button>
                      </form>
                    ) : (
                      <div className="flex min-w-0 items-center gap-1">
                        <p className="truncate text-sm font-medium">
                          {manual.display_name}
                        </p>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon-xs"
                          aria-label={`Rename ${manual.display_name}`}
                          disabled={busyManualId !== null}
                          onClick={() => startManualRename(manual)}
                        >
                          <PencilIcon />
                        </Button>
                      </div>
                    )}
                    <p className="break-words text-xs text-muted-foreground">
                      {manual.description ? `${manual.description} · ` : ""}
                      {manualStatusText(manual)}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <EnabledSwitch
                      checked={manual.enabled}
                      disabled={busyManualId !== null}
                      label={
                        manual.enabled
                          ? `Disable ${manual.display_name}`
                          : `Enable ${manual.display_name}`
                      }
                      onToggle={() => toggleManual(manual)}
                    />
                    {confirmId === manual.manual_id ? (
                      <Button
                        type="button"
                        variant="destructive"
                        size="sm"
                        disabled={busyManualId !== null}
                        onClick={() => removeManual(manual)}
                      >
                        Confirm?
                      </Button>
                    ) : (
                      <Button
                        type="button"
                        variant="outline"
                        size="icon-sm"
                        aria-label={`Delete ${manual.display_name}`}
                        disabled={busyManualId !== null}
                        onClick={() => setConfirmId(manual.manual_id)}
                      >
                        <TrashIcon />
                      </Button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <DialogFooter>
            <Button
              type="button"
              variant="destructive"
              disabled={busy}
              onClick={submitDelete}
            >
              <TrashIcon /> Delete vehicle
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

function EnabledSwitch({
  checked,
  disabled,
  label,
  onToggle,
}: {
  checked: boolean;
  disabled?: boolean;
  label: string;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={onToggle}
      className={`relative h-5 w-9 shrink-0 rounded-full transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
        checked ? "bg-primary" : "bg-muted"
      }`}
    >
      <span
        className={`absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-background shadow transition-transform ${
          checked ? "translate-x-4" : "translate-x-0"
        }`}
      />
    </button>
  );
}
