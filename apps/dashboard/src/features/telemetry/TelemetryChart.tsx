import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { CHANNELS, type ChannelSpec, type Reading, formatClock } from "@/lib/api";
import { cn } from "@/lib/utils";

interface TelemetryChartProps {
  series: Reading[];
  channel: ChannelSpec;
  onChannelChange: (channel: ChannelSpec) => void;
}

function LegendKey({ colour, label }: { colour: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5 font-mono text-[0.6875rem] text-muted-foreground">
      <span className="h-0.5 w-3 rounded-full" style={{ background: colour }} aria-hidden />
      {label}
    </span>
  );
}

export function TelemetryChart({ series, channel, onChannelChange }: TelemetryChartProps) {
  const points = series.map((reading) => ({
    clock: formatClock(reading.recorded_at),
    value: reading[channel.key],
    score: reading.health_index,
  }));

  return (
    <div className="rounded-lg border border-border bg-card">
      <div className="flex flex-wrap items-center gap-1 border-b border-border px-3 py-2">
        {CHANNELS.map((spec) => (
          <button
            key={spec.key}
            type="button"
            onClick={() => onChannelChange(spec)}
            aria-pressed={spec.key === channel.key}
            className={cn(
              "rounded px-2 py-1 font-mono text-[0.6875rem] transition-colors",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              spec.key === channel.key
                ? "bg-primary/15 text-primary"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {spec.label}
          </button>
        ))}
        <div className="ml-auto flex items-center gap-3">
          <LegendKey colour="hsl(var(--primary))" label={channel.unit} />
          <LegendKey colour="hsl(var(--state-watch))" label="degradation" />
        </div>
      </div>

      <div className="h-72 px-2 py-3">
        {points.length === 0 ? (
          <p className="grid h-full place-items-center text-xs text-muted-foreground">
            Waiting for telemetry…
          </p>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={points} margin={{ top: 4, right: 8, bottom: 0, left: 4 }}>
              <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="2 4" vertical={false} />
              <XAxis
                dataKey="clock"
                tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
                stroke="hsl(var(--border))"
                minTickGap={48}
              />
              <YAxis
                yAxisId="channel"
                domain={["auto", "auto"]}
                width={52}
                tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
                stroke="hsl(var(--border))"
              />
              <YAxis
                yAxisId="score"
                orientation="right"
                domain={[0, 1]}
                width={38}
                tickFormatter={(value: number) => `${Math.round(value * 100)}`}
                tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
                stroke="hsl(var(--border))"
              />
              <Tooltip
                contentStyle={{
                  background: "hsl(var(--popover))",
                  border: "1px solid hsl(var(--border))",
                  borderRadius: 6,
                  fontFamily: "IBM Plex Mono, monospace",
                  fontSize: 12,
                }}
                labelStyle={{ color: "hsl(var(--muted-foreground))" }}
                formatter={(value, name) => {
                  const numeric = typeof value === "number" ? value : null;
                  if (name === "score") {
                    return numeric === null
                      ? ["warming up", "Degradation"]
                      : [`${Math.round(numeric * 100)}%`, "Degradation"];
                  }
                  return [
                    `${(numeric ?? 0).toFixed(channel.precision)} ${channel.unit}`,
                    channel.label,
                  ];
                }}
              />
              <Line
                yAxisId="channel"
                type="monotone"
                dataKey="value"
                stroke="hsl(var(--primary))"
                strokeWidth={1.5}
                dot={false}
                // A new point lands every second; re-animating the whole path
                // each time reads as jitter rather than motion.
                isAnimationActive={false}
              />
              <Line
                yAxisId="score"
                type="monotone"
                dataKey="score"
                stroke="hsl(var(--state-watch))"
                strokeWidth={2}
                dot={false}
                // Leaves a gap rather than interpolating across the samples
                // taken before the device had a full feature window.
                connectNulls={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
