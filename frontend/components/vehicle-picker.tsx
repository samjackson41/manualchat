"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
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
import { listManuals, type Manual } from "@/lib/api";
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
  const [manualsByVehicle, setManualsByVehicle] = useState<
    Record<string, Manual[]>
  >({});

  // Refresh on each open, so a manual uploaded elsewhere shows up next time.
  const refreshManuals = useCallback(async () => {
    const all = await listManuals();
    const grouped: Record<string, Manual[]> = {};
    for (const manual of all) {
      (grouped[manual.vehicle_id] ??= []).push(manual);
    }
    setManualsByVehicle(grouped);
  }, []);

  useEffect(() => {
    refreshManuals().catch(() => {
      // The sublist is a convenience; a failed load must not block selection.
    });
  }, [refreshManuals]);

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
        onOpenChange={(open) => {
          if (open) refreshManuals().catch(() => {});
        }}
      >
        <SelectTrigger
          aria-label="Vehicle selector"
          className={triggerClassName ?? "w-72 text-xs"}
        >
          <SelectValue placeholder="Pick a vehicle" />
        </SelectTrigger>
        <SelectContent>
          {vehicles.map((vehicle) => {
            const manuals = manualsByVehicle[vehicle.vehicle_id] ?? [];
            return (
              <SelectItem
                key={vehicle.vehicle_id}
                value={vehicle.vehicle_id}
                className="text-xs"
              >
                <div className="flex min-w-0 flex-col gap-0.5 py-0.5">
                  <span className="min-w-0 truncate font-semibold">
                    {vehicle.display_name}
                  </span>
                  {manuals.length > 0 && (
                    <div className="relative flex flex-col">
                      {manuals.map((manual, index) => {
                        const isLast = index === manuals.length - 1;
                        return (
                          <div
                            key={manual.manual_id}
                            className="relative flex h-5 min-w-0 items-center"
                          >
                            {/* the trunk continues past every elbow but the last */}
                            {!isLast && (
                              <span
                                aria-hidden
                                className="bg-muted-foreground/40 absolute top-1/2 left-2 h-1/2 w-px"
                              />
                            )}
                            {/* the elbow: a rounded corner swinging into the label */}
                            <span
                              aria-hidden
                              className="border-muted-foreground/40 absolute top-0 left-2 h-2.5 w-3 rounded-bl-sm border-b border-l"
                            />
                            <span className="text-muted-foreground! min-w-0 flex-1 truncate pl-6">
                              {manual.display_name}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </SelectItem>
            );
          })}
          <SelectSeparator />
          <SelectItem value={ADD_VEHICLE}>
            <span className="text-primary! flex items-center gap-2 text-xs">
              <PlusIcon className="text-primary! size-4" />
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