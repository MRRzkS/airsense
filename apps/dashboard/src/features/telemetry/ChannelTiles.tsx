import { CHANNELS, type Reading, formatValue } from "@/lib/api";

interface ChannelTilesProps {
  reading: Reading | undefined;
}

export function ChannelTiles({ reading }: ChannelTilesProps) {
  return (
    <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
      {CHANNELS.map((spec) => (
        <div key={spec.key} className="rounded-md border border-border bg-card px-3 py-2.5">
          <dt className="truncate text-[0.6875rem] leading-4 text-muted-foreground">
            {spec.label}
          </dt>
          <dd className="tabular mt-0.5 font-mono text-base leading-6">
            {reading ? formatValue(reading[spec.key], spec) : "—"}
            <span className="ml-1 text-xs text-muted-foreground">{spec.unit}</span>
          </dd>
        </div>
      ))}
    </dl>
  );
}
