import { useEffect, useMemo, useState } from "react";

import { API_URL, type Reading } from "@/lib/api";

export const MAX_POINTS = 240;

interface StreamState {
  byDevice: Record<string, Reading[]>;
  connected: boolean;
}

/**
 * Subscribe to the ingest service's SSE feed.
 *
 * Call this once, near the root: each invocation opens its own EventSource,
 * and the browser caps concurrent connections per origin.
 */
export function useTelemetryStream(): StreamState {
  const [byDevice, setByDevice] = useState<Record<string, Reading[]>>({});
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const source = new EventSource(`${API_URL}/stream`);

    source.addEventListener("open", () => setConnected(true));
    source.addEventListener("error", () => setConnected(false));
    source.addEventListener("reading", (event) => {
      const reading = JSON.parse((event as MessageEvent<string>).data) as Reading;
      setConnected(true);
      setByDevice((current) => {
        const existing = current[reading.device_id] ?? [];
        return { ...current, [reading.device_id]: [...existing, reading].slice(-MAX_POINTS) };
      });
    });

    return () => source.close();
  }, []);

  return { byDevice, connected };
}

/**
 * Merge backfilled history with the live tail for one device.
 *
 * The two overlap whenever the stream connects before history resolves, so
 * `sequence` deduplicates rather than timestamps: the simulator stamps a whole
 * tick with one clock reading, which makes timestamps non-unique by design.
 */
export function useDeviceSeries(
  deviceId: string | null,
  history: Reading[] | undefined,
  live: Record<string, Reading[]>,
): Reading[] {
  return useMemo(() => {
    if (deviceId === null) {
      return [];
    }
    const seen = new Set<number>();
    const merged: Reading[] = [];
    for (const reading of [...(history ?? []), ...(live[deviceId] ?? [])]) {
      if (seen.has(reading.sequence)) {
        continue;
      }
      seen.add(reading.sequence);
      merged.push(reading);
    }
    return merged.slice(-MAX_POINTS);
  }, [deviceId, history, live]);
}
