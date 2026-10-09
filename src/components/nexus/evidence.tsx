import Link from "next/link";
import { Check } from "lucide-react";
import type { EvidenceItem } from "@/lib/types";
import { Card } from "@/components/ui/card";
import { SignalTag } from "./risk-badge";
import { score as percent } from "@/lib/utils";

export function EvidenceCard({ item }: { item: EvidenceItem }) {
  const headingId = `ev-${item.id}`;
  return (
    <Card className="border-l-4 border-l-evidence">
      <article aria-labelledby={headingId} className="p-4">
        <header className="flex flex-wrap items-center justify-between gap-2 border-b pb-3">
          <div className="flex items-center gap-2">
            <SignalTag kind={item.kind} />
            <h3 id={headingId} className="text-sm font-semibold">
              {item.title}
            </h3>
            <span className="id text-muted-foreground">{item.id}</span>
          </div>
          <p className="text-sm">
            <span className="text-muted-foreground">{item.scoreLabel} </span>
            <span className="num font-semibold">{percent(item.score)}</span>
          </p>
        </header>
        <p className="mt-3 max-w-[75ch] text-sm">{item.summary}</p>
        <p className="mt-3 text-xs font-medium text-muted-foreground">{item.rowsTitle}</p>
        <dl className="mt-1 divide-y text-sm">
          {item.rows.map((r) => (
            <div key={r.label} className="grid grid-cols-[minmax(0,11rem)_1fr_auto] items-baseline gap-3 py-1.5">
              <dt className="flex items-center gap-1.5 font-mono text-xs">
                {r.match ? <Check className="size-3.5 shrink-0 text-emerald-700 dark:text-emerald-300" aria-label="Matches" /> : null}
                <span className="truncate">{r.label}</span>
              </dt>
              <dd className="id min-w-0 break-words">{r.value}</dd>
              {r.delta ? <dd className="num text-xs font-medium text-primary">{r.delta}</dd> : <span />}
            </div>
          ))}
        </dl>
        <footer className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs">
          {item.source ? <span className="text-muted-foreground">Source: <span className="font-mono">{item.source}</span></span> : <span />}
          {item.link ? (
            <Link href={item.link.href} className="font-medium text-link underline-offset-4 hover:underline">
              {item.link.label}
            </Link>
          ) : null}
        </footer>
      </article>
    </Card>
  );
}

export function MemberHarmPanel({ factors, score, level }: { factors: string[]; score: number; level: string }) {
  return (
    <div>
      <h3 className="text-sm font-semibold">Member harm factors</h3>
      <p className="mt-0.5 text-xs text-muted-foreground">
        Harm score <span className="num font-medium text-foreground">{percent(score)}</span> ({level === "Med" ? "Medium" : level}). Higher scores move a case up the queue.
      </p>
      <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
        {factors.map((f) => (
          <li key={f}>{f}</li>
        ))}
      </ul>
    </div>
  );
}
