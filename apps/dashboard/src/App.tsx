import { useQuery } from "@tanstack/react-query";
import { Wind } from "lucide-react";
import { useMemo, useState } from "react";

import { DeviceList } from "@/features/devices/DeviceList";
import { ChannelTiles } from "@/features/telemetry/ChannelTiles";
import { TelemetryChart } from "@/features/telemetry/TelemetryChart";
import { useDeviceSeries, useTelemetryStream } from "@/features/telemetry/useTelemetry";
import {
  COMPRESSOR_CURRENT,
  type ChannelSpec,
  type Reading,
  fetchFleet,
  fetchHistory,
} from "@/lib/api";
import { cn } from "@/lib/utils";

function ConnectionBadge({ connected }: { connected: boolean }) {
  return (
    <span className="flex items-center gap-1.5 font-mono text-xs text-muted-foreground">
      <span
        className={cn(
          "size-1.5 rounded-full",
          connected ? "bg-state-normal" : "bg-state-alert",
        )}
        aria-hidden
      />
      {connected ? "streaming" : "disconnected"}
    </span>
  );
}

export default function App() {
  const { byDevice, connected } = useTelemetryStream();
  const [selected, setSelected] = useState<string | null>(null);
  const [channel, setChannel] = useState<ChannelSpec>(COMPRESSOR_CURRENT);

  const fleet = useQuery({ queryKey: ["fleet"], queryFn: fetchFleet, refetchInterval: 10_000 });

  const devices = useMemo(() => {
    const ids = new Set<string>(Object.keys(byDevice));
    for (const reading of fleet.data ?? []) {
      ids.add(reading.device_id);
    }
    return [...ids].sort();
  }, [byDevice, fleet.data]);

  const active = selected ?? devices[0] ?? null;

  const history = useQuery({
    queryKey: ["history", active],
    queryFn: () => fetchHistory(active ?? ""),
    enabled: active !== null,
    staleTime: Infinity,
  });

  const series = useDeviceSeries(active, history.data, byDevice);

  const latest = useMemo(() => {
    const map: Record<string, Reading | undefined> = {};
    for (const reading of fleet.data ?? []) {
      map[reading.device_id] = reading;
    }
    for (const [deviceId, readings] of Object.entries(byDevice)) {
      const last = readings.at(-1);
      if (last) {
        map[deviceId] = last;
      }
    }
    return map;
  }, [byDevice, fleet.data]);

  return (
    <div className="min-h-dvh bg-background font-sans text-foreground">
      <header className="flex items-center justify-between border-b border-border px-6 py-3.5">
        <div className="flex items-center gap-2.5">
          <Wind className="size-5 text-primary" aria-hidden />
          <span className="font-mono text-sm font-medium tracking-tight">airsense</span>
          <span className="text-xs text-muted-foreground">fleet console</span>
        </div>
        <ConnectionBadge connected={connected} />
      </header>

      <main className="mx-auto grid max-w-6xl gap-4 px-6 py-6 lg:grid-cols-[minmax(0,15rem)_minmax(0,1fr)]">
        <aside>
          <h2 className="px-1 pb-2 text-[0.6875rem] uppercase tracking-wide text-muted-foreground">
            Fleet
          </h2>
          <DeviceList
            devices={devices}
            latest={latest}
            selected={active}
            onSelect={setSelected}
          />
        </aside>

        <section className="space-y-3">
          <div className="flex items-baseline gap-2">
            <h1 className="font-mono text-sm font-medium">{active ?? "No device selected"}</h1>
            <span className="tabular text-xs text-muted-foreground">
              {series.length} samples
            </span>
          </div>

          <ChannelTiles reading={series.at(-1)} />
          <TelemetryChart series={series} channel={channel} onChannelChange={setChannel} />
        </section>
      </main>
    </div>
  );
}
