"use client";

import type { QueueData } from "@/lib/types";
import { inr, score } from "@/lib/utils";
import { useQueueStore } from "@/stores";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Slider } from "@/components/ui/form";

function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="num text-lg font-semibold">{value}</dd>
      {note ? <dd className="text-xs text-muted-foreground">{note}</dd> : null}
    </div>
  );
}

export function CapacityOptimizer({ data }: { data: QueueData | undefined }) {
  const { investigators, hours, setCapacity } = useQueueStore();
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Capacity optimizer</CardTitle>
          <CardDescription>Set the review time available this week. The queue selects the highest-priority cases that fit.</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
        <div className="space-y-4">
          <div>
            <div className="mb-1.5 flex justify-between text-sm">
              <span id="cap-inv">Investigators</span>
              <span className="num font-semibold">{investigators}</span>
            </div>
            <Slider thumbLabel="Investigators" min={1} max={12} step={1} value={[investigators]} onValueChange={([v]) => setCapacity({ investigators: v })} />
          </div>
          <div>
            <div className="mb-1.5 flex justify-between text-sm">
              <span>Hours each</span>
              <span className="num font-semibold">{hours}</span>
            </div>
            <Slider thumbLabel="Hours per investigator" min={4} max={40} step={2} value={[hours]} onValueChange={([v]) => setCapacity({ hours: v })} />
          </div>
        </div>
        <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4 lg:border-l lg:pl-6" aria-live="polite">
          <Stat label="Total capacity" value={`${investigators * hours} hours`} note={data ? `${data.usedHours} hours allocated` : undefined} />
          <Stat label="Selected cases" value={data ? `${data.selected.length} of ${data.total}` : "..."} />
          <Stat label="Expected recovery" value={data ? inr(data.expectedRecovery) : "..."} note="Amount weighted by evidence" />
          <Stat label="Member harm reduction" value={data ? score(data.harmReduction) : "..."} note="Share of harm-weighted exposure covered" />
        </dl>
      </CardContent>
    </Card>
  );
}
