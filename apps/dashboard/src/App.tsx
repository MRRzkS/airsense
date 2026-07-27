import { useQuery } from "@tanstack/react-query";
import { CircleAlert, CircleCheck, LoaderCircle, Wind } from "lucide-react";

import { cn } from "@/lib/utils";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

interface Health {
  status: string;
  service: string;
  version: string;
  environment: string;
}

async function fetchHealth(): Promise<Health> {
  const response = await fetch(`${API_URL}/health`);
  if (!response.ok) {
    throw new Error(`ingest-api responded ${response.status}`);
  }
  return (await response.json()) as Health;
}

const PIPELINE: ReadonlyArray<{ stage: string; phase: string; live: boolean }> = [
  { stage: "device-simulator", phase: "P1", live: false },
  { stage: "MQTT broker", phase: "P1", live: false },
  { stage: "ingest-api", phase: "P0", live: true },
  { stage: "TimescaleDB", phase: "P1", live: false },
  { stage: "ONNX scoring", phase: "P2", live: false },
  { stage: "rules engine", phase: "P3", live: false },
  { stage: "TicketSink", phase: "P3", live: false },
];

function StatusDot({ ok }: { ok: boolean }) {
  return (
    <span
      className={cn("size-1.5 rounded-full", ok ? "bg-state-normal" : "bg-muted-foreground/40")}
      aria-hidden
    />
  );
}

export default function App() {
  const { data, isPending, isError, error } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    refetchInterval: 5_000,
  });

  return (
    <div className="min-h-dvh bg-background font-sans text-foreground">
      <header className="flex items-center justify-between border-b border-border px-6 py-3.5">
        <div className="flex items-center gap-2.5">
          <Wind className="size-5 text-primary" aria-hidden />
          <span className="font-mono text-sm font-medium tracking-tight">airsense</span>
          <span className="text-xs text-muted-foreground">fleet console</span>
        </div>
        <span className="rounded border border-border px-2 py-0.5 font-mono text-xs text-muted-foreground">
          {data?.environment ?? "—"}
        </span>
      </header>

      <main className="mx-auto grid max-w-5xl gap-4 px-6 py-8 md:grid-cols-2">
        <section className="rounded-lg border border-border bg-card p-5">
          <h1 className="text-sm font-semibold">ingest-api</h1>
          <p className="mt-1 text-xs text-muted-foreground">
            Polled every 5s from the dashboard origin, which also exercises CORS.
          </p>

          <div className="mt-4 flex items-center gap-2 font-mono text-sm">
            {isPending && (
              <>
                <LoaderCircle className="size-4 animate-spin text-muted-foreground" aria-hidden />
                <span className="text-muted-foreground">connecting…</span>
              </>
            )}
            {isError && (
              <>
                <CircleAlert className="size-4 text-state-alert" aria-hidden />
                <span className="text-state-alert">unreachable</span>
              </>
            )}
            {data && (
              <>
                <CircleCheck className="size-4 text-state-normal" aria-hidden />
                <span className="text-state-normal">{data.status}</span>
                <span className="tabular text-muted-foreground">v{data.version}</span>
              </>
            )}
          </div>

          {isError && (
            <p className="mt-3 font-mono text-xs leading-relaxed text-muted-foreground">
              {error.message}. Start the stack with{" "}
              <code className="text-foreground">make up</code>.
            </p>
          )}
        </section>

        <section className="rounded-lg border border-border bg-card p-5">
          <h2 className="text-sm font-semibold">Pipeline</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            Scaffolded in P0. Each stage lights up as its phase lands.
          </p>

          <ul className="mt-4 space-y-2">
            {PIPELINE.map((step) => (
              <li key={step.stage} className="flex items-center gap-2.5 font-mono text-xs">
                <StatusDot ok={step.live} />
                <span className={cn(step.live ? "text-foreground" : "text-muted-foreground")}>
                  {step.stage}
                </span>
                <span className="ml-auto tabular text-muted-foreground">{step.phase}</span>
              </li>
            ))}
          </ul>
        </section>
      </main>
    </div>
  );
}
