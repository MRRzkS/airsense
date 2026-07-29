import { useQuery } from "@tanstack/react-query";
import { Wind } from "lucide-react";
import { useMemo, useState } from "react";

import { TicketPanel } from "@/features/crm/TicketPanel";
import { DeviceList } from "@/features/devices/DeviceList";
import { StateBadge } from "@/features/devices/StateBadge";
import { InjectFaultButton } from "@/features/faults/InjectFaultButton";
import { ChannelTiles } from "@/features/telemetry/ChannelTiles";
import { TelemetryChart } from "@/features/telemetry/TelemetryChart";
import { useDeviceSeries, useTelemetryStream } from "@/features/telemetry/useTelemetry";
import {
  COMPRESSOR_CURRENT,
  type ChannelSpec,
  type Reading,
  fetchFleet,
  fetchHistory,
  formatScore,
} from "@/lib/api";
import { cn } from "@/lib/utils";

function ConnectionBadge({ connected }: { connected: boolean }) {
  return (
    <span className="flex items-center gap-1.5 font-mono text-xs text-muted-foreground">
      <span
        className={cn("size-1.5 rounded-full", connected ? "bg-state-normal" : "bg-state-alert")}
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

  const current = series.at(-1);

  return (
    <div className="min-h-dvh bg-background font-sans text-foreground">
      <header className="flex items-center justify-between border-b border-border px-6 py-3.5">
        <div className="flex items-center gap-2.5">
          <Wind className="size-5 text-primary" aria-hidden />
          <span className="font-mono text-sm font-medium tracking-tight">airsense</span>
          <span className="text-xs text-muted-foreground">fleet console</span>
        </div>
        <div className="flex items-center gap-4">
          <ConnectionBadge connected={connected} />
          <InjectFaultButton deviceId={active} />
        </div>
      </header>

      <main className="mx-auto grid max-w-[92rem] gap-5 px-6 py-6 lg:grid-cols-[minmax(0,14rem)_minmax(0,1fr)_minmax(0,18rem)]">
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
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="font-mono text-sm font-medium">{active ?? "No device selected"}</h1>
            <StateBadge condition={current?.condition ?? "NORMAL"} />
            <span className="tabular text-xs text-muted-foreground">{series.length} samples</span>
            <span className="ml-auto flex items-baseline gap-1.5">
              <span className="text-[0.6875rem] text-muted-foreground">degradation</span>
              <span className="tabular font-mono text-lg leading-none text-state-watch">
                {formatScore(current?.health_index ?? null)}
              </span>
            </span>
          </div>

          <ChannelTiles reading={current} />
          <TelemetryChart series={series} channel={channel} onChannelChange={setChannel} />
        </section>

        <TicketPanel />
      </main>
    </div>
  );
}
