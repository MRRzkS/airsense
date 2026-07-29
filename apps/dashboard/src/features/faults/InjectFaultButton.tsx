import { useMutation, useQueryClient } from "@tanstack/react-query";
import { LoaderCircle, RotateCcw, Zap } from "lucide-react";

import { RateLimitedError, injectFault, resetFaults } from "@/lib/api";
import { cn } from "@/lib/utils";

interface InjectFaultButtonProps {
  deviceId: string | null;
}

export function InjectFaultButton({ deviceId }: InjectFaultButtonProps) {
  const queryClient = useQueryClient();
  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["fleet"] });
    void queryClient.invalidateQueries({ queryKey: ["tickets"] });
  };

  const inject = useMutation({
    mutationFn: (target: string) => injectFault(target),
    onSuccess: invalidate,
  });
  const reset = useMutation({ mutationFn: resetFaults, onSuccess: invalidate });

  const busy = inject.isPending || reset.isPending;
  const disabled = deviceId === null || busy;

  return (
    <div className="flex flex-col items-end gap-1">
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => reset.mutate()}
          disabled={busy}
          title="Return every device to healthy"
          className={cn(
            "inline-flex h-9 items-center gap-1.5 rounded-md border border-border px-2.5",
            "font-mono text-xs text-muted-foreground transition-colors",
            "hover:text-foreground focus-visible:outline-none focus-visible:ring-2",
            "focus-visible:ring-ring disabled:opacity-50",
          )}
        >
          <RotateCcw className="size-3.5" aria-hidden />
          Reset
        </button>

        <button
          type="button"
          onClick={() => deviceId && inject.mutate(deviceId)}
          disabled={disabled}
          // Amber rather than the destructive red: ALERT is red, and the
          // control that causes an alert must not look like the alert itself.
          className={cn(
            "inline-flex h-9 items-center gap-2 rounded-md px-3.5 font-mono text-xs font-medium",
            "bg-state-watch text-background transition-[filter,opacity]",
            "hover:brightness-110 focus-visible:outline-none focus-visible:ring-2",
            "focus-visible:ring-state-watch focus-visible:ring-offset-2",
            "focus-visible:ring-offset-background disabled:opacity-50",
          )}
        >
          {inject.isPending ? (
            <LoaderCircle className="size-4 animate-spin" aria-hidden />
          ) : (
            <Zap className="size-4" aria-hidden />
          )}
          Inject Fault
        </button>
      </div>

      <p aria-live="polite" className="h-4 font-mono text-[0.6875rem] text-muted-foreground">
        {inject.isError &&
          (inject.error instanceof RateLimitedError
            ? "rate limited — wait a moment"
            : "simulator unreachable")}
        {inject.isSuccess && !inject.isPending && `${deviceId} released into fault ramp`}
      </p>
    </div>
  );
}
