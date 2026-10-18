"use client";

import { useState, type FormEvent } from "react";
import { PencilIcon, TrashIcon } from "lucide-react";
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
          vehicleName={activeVehicle.display_name}
          onRename={(name) => renameVehicle(activeVehicle.vehicle_id, name)}
          onDelete={() => removeVehicle(activeVehicle.vehicle_id)}
        />
      )}
    </div>
  );
}

function ManageVehicleDialog({
  vehicleName,
  onRename,
  onDelete,
}: {
  vehicleName: string;
  onRename: (name: string) => Promise<unknown>;
  onDelete: () => Promise<unknown>;
}) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState(vehicleName);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submitRename(event: FormEvent) {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed || trimmed === vehicleName) {
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

  return (
    <>
      <Button
        variant="outline"
        size="icon"
        aria-label="Manage vehicle"
        onClick={() => {
          setName(vehicleName);
          setOpen(true);
        }}
      >
        <PencilIcon />
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Manage vehicle</DialogTitle>
          </DialogHeader>
          <form onSubmit={submitRename} className="flex flex-col gap-3">
            <Input
              value={name}
              onChange={(event) => setName(event.target.value)}
              aria-label="Vehicle name"
            />
            {error && <p className="text-sm text-destructive">{error}</p>}
            <div className="flex items-center justify-between">
              <Button
                type="button"
                variant="destructive"
                disabled={busy}
                onClick={submitDelete}
              >
                <TrashIcon /> Delete
              </Button>
              <Button type="submit" variant="outline" disabled={busy}>
                Rename
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}