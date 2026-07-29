export const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
export const SIMULATOR_URL = import.meta.env.VITE_SIMULATOR_URL ?? "http://localhost:8001";

export class RateLimitedError extends Error {
  constructor() {
    super("Rate limited — wait a moment before injecting another fault.");
    this.name = "RateLimitedError";
  }
}

export interface Reading {
  device_id: string;
  recorded_at: string;
  sequence: number;
  compressor_current_a: number;
  discharge_pressure_kpa: number;
  suction_temperature_c: number;
  ambient_temperature_c: number;
  vibration_rms_mm_s: number;
  /** null while the device is still filling its first feature window. */
  health_index: number | null;
  condition: DeviceCondition;
}

export type DeviceCondition = "NORMAL" | "WATCH" | "ALERT";

export type Severity = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export interface Ticket {
  ticket_id: string;
  device_id: string;
  fault_class: string;
  diagnostic_code: string;
  severity: Severity;
  status: "OPEN" | "CLOSED";
  opened_at: string;
  updated_at: string;
  closed_at: string | null;
}

export function formatScore(health: number | null): string {
  return health === null ? "—" : `${Math.round(health * 100)}%`;
}

/** Sensor channels only — health_index and condition are derived, not measured. */
export type ChannelKey = keyof Omit<
  Reading,
  "device_id" | "recorded_at" | "sequence" | "health_index" | "condition"
>;

export interface ChannelSpec {
  key: ChannelKey;
  label: string;
  unit: string;
  precision: number;
}

// Named rather than indexed so consumers can default to it without asserting
// past `noUncheckedIndexedAccess`.
export const COMPRESSOR_CURRENT: ChannelSpec = {
  key: "compressor_current_a",
  label: "Compressor current",
  unit: "A",
  precision: 2,
};

export const CHANNELS: readonly ChannelSpec[] = [
  COMPRESSOR_CURRENT,
  { key: "discharge_pressure_kpa", label: "Discharge pressure", unit: "kPa", precision: 0 },
  { key: "suction_temperature_c", label: "Suction temp", unit: "°C", precision: 1 },
  { key: "ambient_temperature_c", label: "Ambient temp", unit: "°C", precision: 1 },
  { key: "vibration_rms_mm_s", label: "Vibration RMS", unit: "mm/s", precision: 2 },
];

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`);
  if (!response.ok) {
    throw new Error(`ingest-api responded ${response.status}`);
  }
  return (await response.json()) as T;
}

export function fetchFleet(): Promise<Reading[]> {
  return getJson<Reading[]>("/devices");
}

export function fetchHistory(deviceId: string, limit = 240): Promise<Reading[]> {
  return getJson<Reading[]>(`/devices/${deviceId}/readings?limit=${limit}`);
}

export function fetchTickets(limit = 20): Promise<Ticket[]> {
  return getJson<Ticket[]>(`/tickets?limit=${limit}`);
}

async function postSimulator<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${SIMULATOR_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  if (response.status === 429) {
    throw new RateLimitedError();
  }
  if (!response.ok) {
    throw new Error(`simulator responded ${response.status}`);
  }
  return (await response.json()) as T;
}

export function injectFault(deviceId: string): Promise<{ device_id: string; faulted: boolean }> {
  return postSimulator("/faults/inject", { device_id: deviceId });
}

export function resetFaults(): Promise<unknown> {
  return postSimulator("/faults/reset");
}

export function formatValue(value: number, spec: ChannelSpec): string {
  return value.toFixed(spec.precision);
}

export function formatClock(iso: string): string {
  return new Date(iso).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}
