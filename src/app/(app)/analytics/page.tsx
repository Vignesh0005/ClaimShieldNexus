"use client";

import { useMemo } from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useAnalytics } from "@/lib/api";
import { inr, inrCompact } from "@/lib/utils";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorState, Loading, PageHeader } from "@/components/ui/state";
import { Table, Td, Th, Tr } from "@/components/ui/table";
import { AXIS_TICK, GRID_STROKE, Plot, TOOLTIP_STYLE } from "@/components/nexus/charts";

const short = (m: string) => ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][Number(m.slice(5)) - 1] + " " + m.slice(2, 4);

export default function AnalyticsPage() {
  const { data, isLoading, error, refetch } = useAnalytics();

  const heat = useMemo(
    () =>
      data
        ? [
            {
              type: "heatmap",
              z: data.heatmap.z,
              x: data.heatmap.specialties,
              y: data.heatmap.schemes,
              colorscale: [
                [0, "rgba(4,120,87,0.06)"],
                [1, "#334155"],
              ],
              xgap: 2,
              ygap: 2,
              hovertemplate: "%{y}<br>%{x}<br>%{z} cases<extra></extra>",
              colorbar: { thickness: 10, title: { text: "Cases", side: "right" } },
            },
          ]
        : [],
    [data],
  );

  return (
    <>
      <PageHeader title="Executive analytics" description="Detection volume, review outcomes and investigator workload for this tenant. Figures the system does not track are marked as not yet measured." />
      {isLoading ? <Loading /> : null}
      {error ? <ErrorState error={error} onRetry={() => refetch()} /> : null}
      {data ? (
        <div className="space-y-4">
          <dl className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {[
              ["Amount identified (INR)", inrCompact(data.totals.identified), "Billed amount on claims routed to cases"],
              ["Amount recovered (INR)", data.totals.recovered === null ? "Not yet measured" : inrCompact(data.totals.recovered), data.totals.recovered === null ? "Recoveries are not tracked by this system" : `${Math.round((data.totals.recovered / (data.totals.identified || 1)) * 100)}% of identified`],
              ["Reviewer-confirmed rate", data.totals.precision === null ? "Not yet measured" : `${Math.round(data.totals.precision * 100)}%`, data.totals.precision === null ? "No confirm or false-positive decisions recorded yet" : `Confirmed share of decided cases${data.totals.decisions ? ` (${data.totals.decisions} decisions)` : ""}`],
              ["Days to decision", data.totals.avgDaysToDecision === null ? "Not yet measured" : data.totals.avgDaysToDecision.toFixed(1), "Average from case opening to recorded decision"],
            ].map(([label, value, note]) => (
              <Card key={label} className="p-4">
                <dt className="text-sm text-muted-foreground">{label}</dt>
                <dd className="num mt-1 text-2xl font-semibold">{value}</dd>
                <dd className="mt-1 text-xs text-muted-foreground">{note}</dd>
              </Card>
            ))}
          </dl>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <div>
                  <CardTitle>Amounts identified and recovered (INR)</CardTitle>
                  <CardDescription>Monthly totals.</CardDescription>
                </div>
              </CardHeader>
              <CardContent>
                <div className="h-64" role="img" aria-label={`Area chart of monthly amounts identified and recovered in INR. Latest month: ${inr(data.monthly[data.monthly.length - 1]?.identified ?? 0)} identified.`}>
                  <ResponsiveContainer>
                    <AreaChart data={data.monthly} margin={{ left: 0, right: 8, top: 8 }}>
                      <CartesianGrid stroke={GRID_STROKE} strokeDasharray="2 4" vertical={false} />
                      <XAxis dataKey="month" tickFormatter={short} tick={AXIS_TICK} stroke={GRID_STROKE} />
                      <YAxis tickFormatter={(v) => inrCompact(v)} tick={AXIS_TICK} stroke={GRID_STROKE} width={105} />
                      <Tooltip {...TOOLTIP_STYLE} formatter={(v: number) => inr(v)} labelFormatter={short} />
                      <Legend wrapperStyle={{ fontSize: 12 }} />
                      <Area type="monotone" name="Identified" dataKey="identified" stroke="#047857" fill="#047857" fillOpacity={0.18} strokeWidth={2} isAnimationActive={false} />
                      <Area type="monotone" name="Recovered" dataKey="recovered" stroke="#10B981" fill="#10B981" fillOpacity={0.25} strokeWidth={2} isAnimationActive={false} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <div>
                  <CardTitle>Reviewer-confirmed rate</CardTitle>
                  <CardDescription>Share of routed cases that reviewers confirmed for referral.{data.precision.length ? "" : " Not yet measured by month: there is no monthly decision history."}</CardDescription>
                </div>
              </CardHeader>
              <CardContent>
                <div className="h-64" role="img" aria-label={`Line chart of reviewer-confirmed rate by month, ${data.precision.length ? `from ${Math.round(data.precision[0].precision * 100)}% to ${Math.round(data.precision[data.precision.length - 1].precision * 100)}%` : "no monthly history yet"}.`}>
                  <ResponsiveContainer>
                    <LineChart data={data.precision} margin={{ left: 0, right: 8, top: 8 }}>
                      <CartesianGrid stroke={GRID_STROKE} strokeDasharray="2 4" vertical={false} />
                      <XAxis dataKey="month" tickFormatter={short} tick={AXIS_TICK} stroke={GRID_STROKE} />
                      <YAxis domain={[0, 1]} tickFormatter={(v) => `${Math.round(v * 100)}%`} tick={AXIS_TICK} stroke={GRID_STROKE} width={44} />
                      <Tooltip {...TOOLTIP_STYLE} formatter={(v: number) => `${Math.round(v * 100)}%`} labelFormatter={short} />
                      <Legend wrapperStyle={{ fontSize: 12 }} />
                      <Line type="monotone" name="Confirmed" dataKey="precision" stroke="#047857" strokeWidth={2} dot={false} isAnimationActive={false} />
                      <Line type="monotone" name="False positive" dataKey="falsePositive" stroke="#94A3B8" strokeWidth={2} strokeDasharray="5 4" dot={false} isAnimationActive={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <div>
                  <CardTitle>Open cases by primary flag</CardTitle>
                  <CardDescription>Billed amount under review.</CardDescription>
                </div>
              </CardHeader>
              <CardContent>
                <div className="h-72" role="img" aria-label={`Bar chart of billed amount by primary flag. Largest: ${data.bySignal[0]?.scheme ?? "none"}, ${inr(data.bySignal[0]?.amount ?? 0)}.`}>
                  <ResponsiveContainer>
                    <BarChart data={data.bySignal} layout="vertical" margin={{ left: 8, right: 16 }}>
                      <CartesianGrid stroke={GRID_STROKE} strokeDasharray="2 4" horizontal={false} />
                      <XAxis type="number" tickFormatter={(v) => inrCompact(v)} tick={AXIS_TICK} stroke={GRID_STROKE} />
                      <YAxis type="category" dataKey="scheme" tick={AXIS_TICK} stroke={GRID_STROKE} width={130} />
                      <Tooltip {...TOOLTIP_STYLE} formatter={(v: number) => inr(v)} cursor={{ fill: "hsl(var(--muted))" }} />
                      <Bar name="Billed amount" dataKey="amount" fill="#047857" radius={[0, 3, 3, 0]} isAnimationActive={false} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <div>
                  <CardTitle>Flags by specialty</CardTitle>
                  <CardDescription>Number of open cases for each flag and provider specialty.</CardDescription>
                </div>
              </CardHeader>
              <CardContent>
                <Plot data={heat} height={288} label="Heatmap of open case counts by primary flag and provider specialty. The same counts are available from the cases list using the search box." />
              </CardContent>
            </Card>
          </div>

          <Card className="overflow-hidden">
            <CardHeader className="pb-3">
              <CardTitle>Investigator workload</CardTitle>
            </CardHeader>
            <Table>
              <thead>
                <tr>
                  <Th>Investigator</Th>
                  <Th className="text-right">Open cases</Th>
                  <Th className="text-right">Closed</Th>
                  <Th className="text-right">Average hours per case</Th>
                </tr>
              </thead>
              <tbody>
                {data.workload.map((w) => (
                  <Tr key={w.investigator}>
                    <Td>{w.investigator}</Td>
                    <Td className="num text-right">{w.open}</Td>
                    <Td className="num text-right">{w.closed}</Td>
                    <Td className="num text-right">{w.avgHours === null ? "Not yet measured" : w.avgHours.toFixed(1)}</Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          </Card>
        </div>
      ) : null}
    </>
  );
}
