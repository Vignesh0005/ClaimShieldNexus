"use client";

import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useHealth } from "@/lib/api";
import { timeAgo } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorState, Loading, PageHeader } from "@/components/ui/state";
import { Table, Td, Th, Tr } from "@/components/ui/table";
import { AXIS_TICK, GRID_STROKE, TOOLTIP_STYLE } from "@/components/nexus/charts";
import { StatusPill } from "@/components/nexus/risk-badge";
import { RoleGate } from "@/components/shell/app-shell";

const LABEL = { operational: "Operational", degraded: "Degraded", down: "Unavailable" };
const ms = (v: number | null | undefined) => (v === null || v === undefined ? "Not yet measured" : `${Math.round(v)} ms`);
const count = (v: number | null | undefined) => (v === null || v === undefined ? "Not yet measured" : v.toLocaleString("en-IN"));

export default function HealthPage() {
  const { data, isLoading, error, refetch, isFetching } = useHealth();
  const perf = data?.performance;
  return (
    <RoleGate allow={["admin"]}>
      <PageHeader
        title="System health"
        description="Status of the detection pipeline and measured performance of this API process. Checked every 30 seconds."
        actions={
          <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
            {isFetching ? "Checking" : "Check now"}
          </Button>
        }
      />
      {isLoading ? <Loading /> : null}
      {error ? <ErrorState error={error} onRetry={() => refetch()} /> : null}
      {data ? (
        <div className="space-y-4">
          <dl className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Card className="p-4">
              <dt className="text-sm text-muted-foreground">Overall status</dt>
              <dd className="mt-2">
                <StatusPill tone={data.status === "operational" ? "good" : "warn"}>{data.status === "operational" ? "All checks passing" : "At least one check failing"}</StatusPill>
              </dd>
              <dd className="mt-2 text-xs text-muted-foreground">Checked {timeAgo(data.checkedAt)}</dd>
            </Card>
            <Card className="p-4">
              <dt className="text-sm text-muted-foreground">Detection latency (p50 / p95 / p99)</dt>
              <dd className="num mt-1 text-lg font-semibold">{perf?.samples ? `${ms(perf.p50)} / ${ms(perf.p95)} / ${ms(perf.p99)}` : "Not yet measured"}</dd>
              <dd className="text-xs text-muted-foreground">{perf?.samples ? `Last ${perf.samples} claims in this process` : "No claims processed since this process started"}</dd>
            </Card>
            <Card className="p-4">
              <dt className="text-sm text-muted-foreground">Claims processed, last minute</dt>
              <dd className="num mt-1 text-2xl font-semibold">{count(perf ? perf.perMinute : data.ingest?.perMinute)}</dd>
              {perf?.perMinuteAvg5 !== null && perf?.perMinuteAvg5 !== undefined ? <dd className="num text-xs text-muted-foreground">{perf.perMinuteAvg5} per minute over 5 minutes</dd> : null}
            </Card>
            <Card className="p-4">
              <dt className="text-sm text-muted-foreground">Claims waiting for detection</dt>
              <dd className="num mt-1 text-2xl font-semibold">{count(perf ? perf.backlog : data.ingest?.backlog)}</dd>
              {perf ? <dd className="text-xs text-muted-foreground">Processing mode: {perf.mode}</dd> : null}
            </Card>
          </dl>
          {perf?.note ? <p className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">{perf.note}</p> : null}

          <Card className="overflow-hidden">
            <Table>
              <caption className="sr-only">Service checks</caption>
              <thead>
                <tr>
                  <Th>Check</Th>
                  <Th>Status</Th>
                  <Th className="text-right">Response time</Th>
                  <Th>Detail</Th>
                </tr>
              </thead>
              <tbody>
                {data.services.map((s) => (
                  <Tr key={s.name}>
                    <Td className="font-medium">{s.name}</Td>
                    <Td>
                      <StatusPill tone={s.status === "operational" ? "good" : "warn"}>{LABEL[s.status]}</StatusPill>
                    </Td>
                    <Td className="num text-right">{s.latencyMs} ms</Td>
                    <Td className="whitespace-normal text-muted-foreground">{s.note ?? (s.uptime !== null ? `${s.uptime.toFixed(2)}% uptime, 30 days` : "")}</Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          </Card>

          {data.latency.length > 1 ? (
            <Card>
              <CardHeader>
                <div>
                  <CardTitle>Detection latency by minute</CardTitle>
                  <CardDescription>Milliseconds per claim, for minutes in which claims were processed.</CardDescription>
                </div>
              </CardHeader>
              <CardContent>
                <div className="h-60" role="img" aria-label={`Line chart of detection latency. Latest p50 ${data.latency[data.latency.length - 1].p50} ms, p95 ${data.latency[data.latency.length - 1].p95} ms.`}>
                  <ResponsiveContainer>
                    <LineChart data={data.latency} margin={{ left: 0, right: 12, top: 8 }}>
                      <CartesianGrid stroke={GRID_STROKE} strokeDasharray="2 4" vertical={false} />
                      <XAxis dataKey="t" tick={AXIS_TICK} stroke={GRID_STROKE} minTickGap={32} />
                      <YAxis tick={AXIS_TICK} stroke={GRID_STROKE} width={52} unit=" ms" />
                      <Tooltip {...TOOLTIP_STYLE} formatter={(v: number) => `${v} ms`} />
                      <Legend wrapperStyle={{ fontSize: 12 }} />
                      <Line type="monotone" name="p50" dataKey="p50" stroke="#047857" strokeWidth={2} dot={false} isAnimationActive={false} />
                      <Line type="monotone" name="p95" dataKey="p95" stroke="#334155" strokeWidth={2} strokeDasharray="5 4" dot={false} isAnimationActive={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>
          ) : null}
        </div>
      ) : null}
    </RoleGate>
  );
}
