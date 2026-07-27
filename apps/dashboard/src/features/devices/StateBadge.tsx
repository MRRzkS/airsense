import { CircleAlert, CircleCheck, TriangleAlert } from "lucide-react";

import type { DeviceCondition } from "@/lib/api";
import { cn } from "@/lib/utils";

// Icon as well as colour: condition must survive being read by someone who
// cannot distinguish the three hues, and by a greyscale screenshot.
const APPEARANCE: Record<
  DeviceCondition,
  { icon: typeof CircleCheck; className: string }
> = {
  NORMAL: { icon: CircleCheck, className: "text-state-normal border-state-normal/30" },
  WATCH: { icon: TriangleAlert, className: "text-state-watch border-state-watch/40" },
  ALERT: { icon: CircleAlert, className: "text-state-alert border-state-alert/50" },
};

export function StateBadge({
  condition,
  className,
}: {
  condition: DeviceCondition;
  className?: string;
}) {
  const { icon: Icon, className: tone } = APPEARANCE[condition];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded border px-1.5 py-0.5 font-mono text-[0.625rem] leading-4",
        tone,
        className,
      )}
    >
      <Icon className="size-3" aria-hidden />
      {condition}
    </span>
  );
}
