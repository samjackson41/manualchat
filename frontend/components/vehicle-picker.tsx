"use client";

import { useEffect, useState, type FormEvent } from "react";
import { PlusIcon } from "lucide-react";
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
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useVehicles } from "@/app/vehicle-runtime";

// Sentinel value for the "Add vehicle" entry at the bottom of the list.
const ADD_VEHICLE = "__add_vehicle__";

export function VehiclePicker({
  value,
  onValueChange,
  triggerClassName,
}: {
  value: string | null;
  onValueChange: (id: string) => void;
  triggerClassName?: string;
}) {
  const { vehicles, addVehicle } = useVehicles();
  const [addOpen, setAddOpen] = useState(false);

  function handleSelect(next: string) {
    if (next === ADD_VEHICLE) {
      setAddOpen(true);
      return;
    }
    onValueChange(next);
  }

  async function handleAdd(name: string) {
    const vehicle = await addVehicle(name);
    onValueChange(vehicle.vehicle_id);
  }

  return (
    <>
      <Select
        value={value ?? null}
        items={vehicles.map((vehicle) => ({
          value: vehicle.vehicle_id,
          label: vehicle.display_name,
        }))}
        onValueChange={(next) => {
          if (next) handleSelect(next);
        }}
      >
        <SelectTrigger
          aria-label="Vehicle selector"
          className={triggerClassName ?? "w-44"}
        >
          <SelectValue placeholder="Pick a vehicle" />
        </SelectTrigger>
        <SelectContent>
          {vehicles.map((vehicle) => (
            <SelectItem key={vehicle.vehicle_id} value={vehicle.vehicle_id}>
              {vehicle.display_name}
            </SelectItem>
          ))}
          <SelectSeparator />
          <SelectItem value={ADD_VEHICLE}>
            <span className="text-primary flex items-center gap-2">
              <PlusIcon className="size-4" />
              Add vehicle
            </span>
          </SelectItem>
        </SelectContent>
      </Select>
      <AddVehicleDialog
        open={addOpen}
        onOpenChange={setAddOpen}
        onAdd={handleAdd}
      />
    </>
  );
}

function AddVehicleDialog({
  open,
  onOpenChange,
  onAdd,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAdd: (name: string) => Promise<unknown>;
}) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // The dialog stays mounted, so clear the field each time it opens.
  useEffect(() => {
    if (open) {
      setName("");
      setBusy(false);
      setError(null);
    }
  }, [open]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    setBusy(true);
    setError(null);
    try {
      await onAdd(trimmed);
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add vehicle");
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add a vehicle</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit} className="flex flex-col gap-3">
          <Input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="e.g. 2023 Civic"
            autoFocus
          />
          {error && <p className="text-destructive text-sm">{error}</p>}
          <DialogFooter>
            <Button type="submit" disabled={busy || !name.trim()}>
              Add
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}