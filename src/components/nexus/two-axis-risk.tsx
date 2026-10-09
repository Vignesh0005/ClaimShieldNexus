"use client";

import { CartesianGrid, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from "recharts";
import type { CaseDetail } from "@/lib/types";
import { AXIS_TICK, GRID_STROKE, TOOLTIP_STYLE } from "./charts";
import { score } from "@/lib/utils";

export function TwoAxisRisk({ item }: { item: CaseDetail }) {
  const here = [{ suspicion: item.risk, evidence: item.evidence, id: item.id }];
  const quadrant =
    item.risk >= 0.6 && item.evidence >= 0.6
      ? "High suspicion with strong evidence."
      : item.risk >= 0.6
        ? "High suspicion, but evidence is limited."
        : item.evidence >= 0.6
          ? "Well-evidenced, with lower suspicion."
          : "Lower suspicion and limited evidence.";
  return (
    <figure>
      <div
        className="h-56"
        role="img"
        aria-label={`Scatter plot of suspicion against evidence strength. This case: suspicion ${score(item.risk)}, evidence ${score(item.evidence)}, shown against ${item.peers.length} other flagged clusters.`}
      >
        <ResponsiveContainer>
          <ScatterChart margin={{ top: 8, right: 12, bottom: 18, left: -8 }}>
            <CartesianGrid stroke={GRID_STROKE} strokeDasharray="2 4" />
            <XAxis type="number" dataKey="suspicion" domain={[0, 1]} tickCount={6} tickFormatter={score} tick={AXIS_TICK} stroke={GRID_STROKE} label={{ value: "Suspicion", position: "insideBottom", offset: -10, ...AXIS_TICK }} />
            <YAxis type="number" dataKey="evidence" domain={[0, 1]} tickCount={6} tickFormatter={score} tick={AXIS_TICK} stroke={GRID_STROKE} label={{ value: "Evidence", angle: -90, position: "insideLeft", offset: 18, ...AXIS_TICK }} />
            <ZAxis range={[36, 36]} />
            <ReferenceLine x={0.6} stroke="#94A3B8" strokeDasharray="4 4" />
            <ReferenceLine y={0.6} stroke="#94A3B8" strokeDasharray="4 4" />
            <Tooltip {...TOOLTIP_STYLE} cursor={{ strokeDasharray: "3 3" }} formatter={(v: number) => score(v)} />
            <Scatter name="Other clusters" data={item.peers} fill="#94A3B8" fillOpacity={0.55} isAnimationActive={false} />
            <Scatter name={item.id} data={here} fill="#DC2626" stroke="#fff" strokeWidth={1.5} shape="diamond" isAnimationActive={false}>
            </Scatter>
          </ScatterChart>
        </ResponsiveContainer>
      </div>
      <figcaption className="mt-1 text-xs text-muted-foreground">
        <span className="mr-1 inline-block size-2 rotate-45 bg-risk-critical align-middle" aria-hidden /> This case: suspicion{" "}
        <span className="num font-medium text-foreground">{score(item.risk)}</span>, evidence{" "}
        <span className="num font-medium text-foreground">{score(item.evidence)}</span>. {quadrant} Dashed lines mark the 60% routing threshold.
      </figcaption>
    </figure>
  );
}

export function SignalBreakdown({ signals }: { signals: CaseDetail["signals"] }) {
  const rows: [string, number][] = [
    ["Rules", signals.rule],
    ["ML", signals.ml],
    ["Graph", signals.graph],
    ["Temporal", signals.temporal],
  ];
  return (
    <dl className="space-y-2.5">
      {rows.map(([label, v]) => (
        <div key={label} className="grid grid-cols-[4.5rem_1fr_2.5rem] items-center gap-3 text-sm">
          <dt className="text-muted-foreground">{label}</dt>
          <dd className="h-2.5 overflow-hidden rounded-sm bg-secondary" aria-hidden>
            <div className="h-full rounded-sm bg-evidence" style={{ width: `${v * 100}%` }} />
          </dd>
          <dd className="num text-right font-medium">{score(v)}</dd>
        </div>
      ))}
    </dl>
  );
}
