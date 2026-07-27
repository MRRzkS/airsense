import { type Reading, formatScore } from "@/lib/api";
import { cn } from "@/lib/utils";

interface DeviceListProps {
  devices: string[];
  latest: Record<string, Reading | undefined>;
  selected: string | null;
  onSelect: (deviceId: string) => void;
}

function ScoreBar({ health }: { health: number | null }) {
  return (
    <span className="block h-0.5 w-full overflow-hidden rounded-full bg-muted" aria-hidden>
      <span
        className="block h-full bg-state-watch transition-[width] duration-500"
        style={{ width: `${(health ?? 0) * 100}%` }}
      />
    </span>
  );
}

export function DeviceList({ devices, latest, selected, onSelect }: DeviceListProps) {
  if (devices.length === 0) {
    return (
      <p className="px-1 py-6 text-xs text-muted-foreground">
        No devices reporting yet. Start the stack with{" "}
        <code className="text-foreground">make up</code>.
      </p>
    );
  }

  return (
    <ul className="space-y-1">
      {devices.map((deviceId) => {
        const reading = latest[deviceId];
        const health = reading?.health_index ?? null;
        const active = deviceId === selected;
        return (
          <li key={deviceId}>
            <button
              type="button"
              onClick={() => onSelect(deviceId)}
              aria-current={active ? "true" : undefined}
              className={cn(
                "w-full space-y-1.5 rounded-md border px-3 py-2 text-left transition-colors",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                active
                  ? "border-primary/50 bg-primary/10"
                  : "border-transparent hover:border-border hover:bg-card",
              )}
            >
              <span className="flex items-baseline gap-2">
                <span className="font-mono text-xs font-medium">{deviceId}</span>
                <span className="tabular ml-auto font-mono text-xs text-muted-foreground">
                  {formatScore(health)}
                </span>
              </span>
              <ScoreBar health={health} />
            </button>
          </li>
        );
      })}
    </ul>
  );
}
