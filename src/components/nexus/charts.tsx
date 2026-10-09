"use client";

import { useEffect, useRef } from "react";
import { useTheme } from "next-themes";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import type { RiskLevel } from "@/lib/types";
import { num, RISK_HEX, RISK_LABEL } from "@/lib/utils";

export const AXIS_TICK = { fill: "hsl(var(--muted-foreground))", fontSize: 11 };
export const GRID_STROKE = "hsl(var(--grid))";
export const TOOLTIP_STYLE = {
  contentStyle: { background: "hsl(var(--popover))", border: "1px solid hsl(var(--border))", borderRadius: 6, fontSize: 12, color: "hsl(var(--popover-foreground))" },
  itemStyle: { color: "hsl(var(--popover-foreground))" },
  labelStyle: { color: "hsl(var(--muted-foreground))" },
};

export function RiskDonut({ data }: { data: { level: RiskLevel; count: number }[] }) {
  const total = data.reduce((s, d) => s + d.count, 0);
  return (
    <div className="grid items-center gap-4 sm:grid-cols-[minmax(0,11rem)_1fr]">
      <div className="relative h-44" role="img" aria-label={`Alerts by risk level: ${data.map((d) => `${RISK_LABEL[d.level]} ${d.count}`).join(", ")}`}>
        <ResponsiveContainer>
          <PieChart>
            <Pie data={data} dataKey="count" nameKey="level" innerRadius="62%" outerRadius="95%" paddingAngle={2} stroke="none" isAnimationActive={false}>
              {data.map((d) => (
                <Cell key={d.level} fill={RISK_HEX[d.level]} />
              ))}
            </Pie>
            <Tooltip {...TOOLTIP_STYLE} formatter={(v: number, name: string) => [num(v), RISK_LABEL[name as RiskLevel]]} />
          </PieChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <span className="num text-xl font-semibold">{num(total)}</span>
          <span className="text-xs text-muted-foreground">alerts</span>
        </div>
      </div>
      <dl className="space-y-1.5 text-sm">
        {data.map((d) => (
          <div key={d.level} className="flex items-center justify-between gap-3">
            <dt className="flex items-center gap-2">
              <span className="size-2.5 rounded-full" style={{ background: RISK_HEX[d.level] }} aria-hidden />
              {RISK_LABEL[d.level]}
            </dt>
            <dd className="num font-medium">
              {num(d.count)} <span className="font-normal text-muted-foreground">({total ? Math.round((d.count / total) * 100) : 0}%)</span>
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

// Thin wrapper over Plotly, loaded on demand because the bundle is large.
export function Plot({ data, layout, label, height = 320 }: { data: unknown[]; layout?: Record<string, unknown>; label: string; height?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const { resolvedTheme } = useTheme();
  useEffect(() => {
    let cancelled = false;
    const el = ref.current;
    if (!el) return;
    const text = "#334155";
    const grid = "#CBD5E1";
    import("plotly.js-dist-min").then((mod) => {
      if (cancelled) return;
      const Plotly = mod.default;
      Plotly.react(
        el,
        data,
        {
          paper_bgcolor: "rgba(0,0,0,0)",
          plot_bgcolor: "rgba(0,0,0,0)",
          font: { family: "var(--font-inter), system-ui, sans-serif", size: 11, color: text },
          margin: { l: 130, r: 16, t: 8, b: 90 },
          xaxis: { gridcolor: grid, linecolor: grid, tickangle: -35 },
          yaxis: { gridcolor: grid, linecolor: grid, automargin: true },
          height,
          ...layout,
        },
        { displayModeBar: false, responsive: true },
      );
    });
    return () => {
      cancelled = true;
    };
  }, [data, layout, resolvedTheme, height]);
  useEffect(() => {
    const el = ref.current;
    return () => {
      if (el) import("plotly.js-dist-min").then((mod) => mod.default.purge(el));
    };
  }, []);
  return <div ref={ref} role="img" aria-label={label} style={{ minHeight: height }} />;
}
