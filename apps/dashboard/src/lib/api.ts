export const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export interface Reading {
  device_id: string;
  recorded_at: string;
  sequence: number;
  compressor_current_a: number;
  discharge_pressure_kpa: number;
  suction_temperature_c: number;
  ambient_temperature_c: number;
  vibration_rms_mm_s: number;
}

export interface ChannelSpec {
  key: keyof Omit<Reading, "device_id" | "recorded_at" | "sequence">;
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
