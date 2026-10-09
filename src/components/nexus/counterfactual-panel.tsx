import type { Counterfactual } from "@/lib/types";
import { riskLevel, score } from "@/lib/utils";
import { Card } from "@/components/ui/card";
import { RiskBadge, StatusPill } from "./risk-badge";

export function CounterfactualPanel({ data }: { data: Counterfactual }) {
  return (
    <div className="space-y-4">
      <p className="max-w-[75ch] text-sm text-muted-foreground">
        Each scenario re-scores the case with one input changed. Use them to see which signals the score depends on. The baseline score is{" "}
        <span className="num font-medium text-foreground">{score(data.baseline)}</span> and cases are routed to the queue at{" "}
        <span className="num font-medium text-foreground">{score(data.threshold)}</span> or above.
      </p>
      <ul className="grid gap-3 lg:grid-cols-2">
        {data.scenarios.map((s) => {
          const delta = s.newRisk - data.baseline;
          return (
            <li key={s.id}>
              <Card className="h-full p-4">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <h3 className="text-sm font-semibold">{s.label}</h3>
                  <StatusPill tone={s.wouldRoute ? "warn" : "good"}>{s.wouldRoute ? "Would still be routed" : "Would not be routed"}</StatusPill>
                </div>
                <p className="mt-1 text-sm text-muted-foreground">{s.description}</p>
                <div className="relative mt-4 h-2.5 rounded-sm bg-secondary" aria-hidden>
                  <div className="absolute inset-y-0 left-0 rounded-sm bg-slate-400/60" style={{ width: `${data.baseline * 100}%` }} />
                  <div className="absolute inset-y-0 left-0 rounded-sm bg-evidence" style={{ width: `${s.newRisk * 100}%` }} />
                  <div className="absolute -inset-y-1 w-px bg-foreground" style={{ left: `${data.threshold * 100}%` }} />
                </div>
                <p className="mt-3 flex flex-wrap items-center gap-2 text-sm">
                  <RiskBadge score={data.baseline} level={riskLevel(data.baseline)} />
                  <span className="text-muted-foreground">becomes</span>
                  <RiskBadge score={s.newRisk} level={riskLevel(s.newRisk)} />
                  <span className="num text-muted-foreground">({delta > 0 ? "+" : ""}{Math.round(delta * 100)} points)</span>
                </p>
              </Card>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
