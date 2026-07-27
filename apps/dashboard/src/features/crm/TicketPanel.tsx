import { useQuery } from "@tanstack/react-query";
import { Inbox } from "lucide-react";

import { type Severity, type Ticket, fetchTickets, formatClock } from "@/lib/api";
import { cn } from "@/lib/utils";

const SEVERITY_TONE: Record<Severity, string> = {
  LOW: "text-muted-foreground border-border",
  MEDIUM: "text-state-watch border-state-watch/40",
  HIGH: "text-state-alert border-state-alert/40",
  CRITICAL: "text-state-alert border-state-alert bg-state-alert/10",
};

function TicketRow({ ticket }: { ticket: Ticket }) {
  const closed = ticket.status === "CLOSED";
  return (
    <li
      className={cn(
        "space-y-1 rounded-md border border-border bg-card px-3 py-2.5",
        closed && "opacity-55",
      )}
    >
      <div className="flex items-center gap-2">
        <span className="font-mono text-xs font-medium">{ticket.ticket_id}</span>
        <span
          className={cn(
            "rounded border px-1.5 py-0.5 font-mono text-[0.625rem] leading-4",
            SEVERITY_TONE[ticket.severity],
          )}
        >
          {ticket.severity}
        </span>
        <span className="ml-auto font-mono text-[0.625rem] text-muted-foreground">
          {closed ? "CLOSED" : "OPEN"}
        </span>
      </div>
      <div className="flex items-center gap-2 font-mono text-[0.6875rem] text-muted-foreground">
        <span className="text-foreground">{ticket.device_id}</span>
        <span>{ticket.diagnostic_code}</span>
        <span className="tabular ml-auto">{formatClock(ticket.updated_at)}</span>
      </div>
    </li>
  );
}

export function TicketPanel() {
  // Polled rather than streamed: tickets change on the order of minutes, and a
  // second SSE connection to carry a handful of rows would not pay for itself.
  const tickets = useQuery({
    queryKey: ["tickets"],
    queryFn: () => fetchTickets(),
    refetchInterval: 3_000,
  });

  const rows = tickets.data ?? [];

  return (
    <section className="space-y-2">
      <h2 className="flex items-center gap-2 px-1 text-[0.6875rem] uppercase tracking-wide text-muted-foreground">
        <Inbox className="size-3.5" aria-hidden />
        CRM — support tickets
        {rows.length > 0 && <span className="tabular ml-auto font-mono">{rows.length}</span>}
      </h2>

      {rows.length === 0 ? (
        <p className="rounded-md border border-dashed border-border px-3 py-6 text-center text-xs text-muted-foreground">
          No tickets. One opens automatically when a unit sustains an alert.
        </p>
      ) : (
        <ul className="space-y-1.5">
          {rows.map((ticket) => (
            <TicketRow key={ticket.ticket_id} ticket={ticket} />
          ))}
        </ul>
      )}
    </section>
  );
}
