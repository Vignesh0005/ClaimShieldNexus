import type { AuditEvent } from "@/lib/types";
import { dateTime } from "@/lib/utils";
import { Empty } from "@/components/ui/state";

export function AuditTimeline({ events }: { events: AuditEvent[] }) {
  if (!events.length) return <Empty title="No audit events yet">Views and decisions on this case are recorded here.</Empty>;
  const ordered = [...events].sort((a, b) => a.ts.localeCompare(b.ts));
  return (
    <ol className="divide-y text-sm">
      {ordered.map((e) => (
        <li key={e.id} className="grid grid-cols-[9.5rem_5rem_1fr] gap-3 py-1.5 max-sm:grid-cols-1 max-sm:gap-0">
          <time dateTime={e.ts} className="id text-muted-foreground">
            {dateTime(e.ts)}
          </time>
          <span className="id">{e.actor}</span>
          <span>
            {e.action}
            {e.detail ? <span className="text-muted-foreground"> ({e.detail})</span> : null}
          </span>
        </li>
      ))}
    </ol>
  );
}
