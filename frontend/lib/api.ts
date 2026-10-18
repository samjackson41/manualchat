// Typed calls to the ManualChat backend. Field names stay snake_case to match
// the wire format exactly, so there is no mapping layer to drift.

const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

export type ModelOption = { id: string; label: string };

export const MANUAL_KINDS = ["oem", "aftermarket", "supplement", "other"] as const;
export type ManualKind = (typeof MANUAL_KINDS)[number];

export type Vehicle = {
  vehicle_id: string;
  user_id: string;
  display_name: string;
  created_at: string;
};

export type Manual = {
  manual_id: string;
  vehicle_id: string;
  display_name: string;
  source_filename: string;
  kind: ManualKind;
  status: "processing" | "ready" | "error";
  created_at: string;
};

type ChatResponse = { reply: string; model: string };

async function errorDetail(res: Response): Promise<string> {
  const data = await res.json().catch(() => null);
  return typeof data?.detail === "string"
    ? data.detail
    : `Request failed (${res.status})`;
}

export async function getModels(): Promise<{
  default: string;
  options: ModelOption[];
}> {
  const res = await fetch(`${BACKEND_URL}/models`);
  if (!res.ok) throw new Error(await errorDetail(res));
  return res.json();
}

export async function getVehicles(): Promise<Vehicle[]> {
  const res = await fetch(`${BACKEND_URL}/vehicles`);
  if (!res.ok) throw new Error(await errorDetail(res));
  return res.json();
}

export async function createVehicle(display_name: string): Promise<Vehicle> {
  const res = await fetch(`${BACKEND_URL}/vehicles`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ display_name }),
  });
  if (!res.ok) throw new Error(await errorDetail(res));
  return res.json();
}

export async function renameVehicle(
  vehicle_id: string,
  display_name: string,
): Promise<Vehicle> {
  const res = await fetch(`${BACKEND_URL}/vehicles/${vehicle_id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ display_name }),
  });
  if (!res.ok) throw new Error(await errorDetail(res));
  return res.json();
}

export async function deleteVehicle(vehicle_id: string): Promise<void> {
  const res = await fetch(`${BACKEND_URL}/vehicles/${vehicle_id}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(await errorDetail(res));
}

export async function listManuals(): Promise<Manual[]> {
  const res = await fetch(`${BACKEND_URL}/manuals`);
  if (!res.ok) throw new Error(await errorDetail(res));
  return res.json();
}

export async function uploadManual(input: {
  file: File;
  vehicleId: string;
  displayName: string;
  kind: ManualKind;
}): Promise<Manual> {
  const form = new FormData();
  form.append("file", input.file);
  form.append("vehicle_id", input.vehicleId);
  form.append("display_name", input.displayName);
  form.append("kind", input.kind);
  const res = await fetch(`${BACKEND_URL}/manuals`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) throw new Error(await errorDetail(res));
  return res.json();
}

export async function chat(
  input: { query: string; model?: string; vehicleId?: string },
  signal?: AbortSignal,
): Promise<ChatResponse> {
  const res = await fetch(`${BACKEND_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query: input.query,
      model: input.model,
      vehicle_id: input.vehicleId,
    }),
    signal,
  });
  if (!res.ok) throw new Error(await errorDetail(res));
  return res.json();
}