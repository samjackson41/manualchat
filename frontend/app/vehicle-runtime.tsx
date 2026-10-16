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
import {
  createVehicle,
  deleteVehicle,
  getVehicles,
  renameVehicle,
  type Vehicle,
} from "@/lib/api";

// The last chosen vehicle survives reloads; the choice is a scope, not data.
const ACTIVE_VEHICLE_KEY = "manualchat:active-vehicle";

type VehicleSelection = {
  vehicles: Vehicle[];
  activeVehicleId: string | null;
  loading: boolean;
  error: string | null;
  selectVehicle: (id: string) => void;
  addVehicle: (displayName: string) => Promise<Vehicle>;
  renameVehicle: (id: string, displayName: string) => Promise<void>;
  removeVehicle: (id: string) => Promise<void>;
};

const VehicleContext = createContext<VehicleSelection | null>(null);

export function useVehicles(): VehicleSelection {
  const ctx = useContext(VehicleContext);
  if (!ctx) {
    throw new Error("useVehicles must be used inside VehicleProvider");
  }
  return ctx;
}

export function VehicleProvider({ children }: { children: ReactNode }) {
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [activeVehicleId, setActiveVehicleId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getVehicles()
      .then((list) => {
        setVehicles(list);
        const persisted = localStorage.getItem(ACTIVE_VEHICLE_KEY);
        const active = list.some((v) => v.vehicle_id === persisted)
          ? persisted
          : (list[0]?.vehicle_id ?? null);
        setActiveVehicleId(active);
      })
      .catch(() => setError("Could not load vehicles"))
      .finally(() => setLoading(false));
  }, []);

  const selectVehicle = useCallback((id: string) => {
    setActiveVehicleId(id);
    localStorage.setItem(ACTIVE_VEHICLE_KEY, id);
  }, []);

  const addVehicle = useCallback(async (displayName: string) => {
    const vehicle = await createVehicle(displayName);
    setVehicles((prev) => [vehicle, ...prev]);
    setActiveVehicleId(vehicle.vehicle_id);
    localStorage.setItem(ACTIVE_VEHICLE_KEY, vehicle.vehicle_id);
    setError(null);
    return vehicle;
  }, []);

  const rename = useCallback(async (id: string, displayName: string) => {
    const updated = await renameVehicle(id, displayName);
    setVehicles((prev) =>
      prev.map((v) => (v.vehicle_id === id ? updated : v)),
    );
    setError(null);
  }, []);

  const remove = useCallback(
    async (id: string) => {
      await deleteVehicle(id);
      const next = vehicles.filter((v) => v.vehicle_id !== id);
      setVehicles(next);
      if (activeVehicleId === id) {
        const nextId = next[0]?.vehicle_id ?? null;
        setActiveVehicleId(nextId);
        if (nextId) {
          localStorage.setItem(ACTIVE_VEHICLE_KEY, nextId);
        } else {
          localStorage.removeItem(ACTIVE_VEHICLE_KEY);
        }
      }
      setError(null);
    },
    [vehicles, activeVehicleId],
  );

  const selection = useMemo<VehicleSelection>(
    () => ({
      vehicles,
      activeVehicleId,
      loading,
      error,
      selectVehicle,
      addVehicle,
      renameVehicle: rename,
      removeVehicle: remove,
    }),
    [
      vehicles,
      activeVehicleId,
      loading,
      error,
      selectVehicle,
      addVehicle,
      rename,
      remove,
    ],
  );

  return (
    <VehicleContext.Provider value={selection}>
      {children}
    </VehicleContext.Provider>
  );
}