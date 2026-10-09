"use client";

import Link from "next/link";
import { useFunnel } from "@/lib/api";
import { timeAgo, inrCompact } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorState, Loading, PageHeader } from "@/components/ui/state";
import { RiskDonut } from "@/components/nexus/charts";
import { FunnelChart } from "@/components/nexus/funnel-chart";
import { MetricCard } from "@/components/nexus/metric-card";
import { RiskBadge } from "@/components/nexus/risk-badge";

export default function DashboardPage() {
  const { data, isLoading, error, refetch } = useFunnel();
  return (
    <>
      <PageHeader title="Dashboard" description="Claims, alerts and cases for the selected tenant over the last 30 days." />
      {isLoading ? <Loading /> : null}
      {error ? <ErrorState error={error} onRetry={() => refetch()} /> : null}
      {data ? (
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {data.metrics.map((m) => (
              <MetricCard key={m.key} metric={m} />
            ))}
          </div>

          <Card>
            <CardHeader>
              <div>
                <CardTitle>Alert-to-case funnel</CardTitle>
                <CardDescription>How many items remain after each stage of triage.</CardDescription>
              </div>
              <Button asChild variant="outline" size="sm">
                <Link href="/queue">View the SIU queue</Link>
              </Button>
            </CardHeader>
            <CardContent>
              <FunnelChart stages={data.stages} />
              <p className="mt-3 text-sm">
                Reduction from claims to cases: <span className="num font-semibold">{data.reduction}%</span>
              </p>
            </CardContent>
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Risk distribution</CardTitle>
              </CardHeader>
              <CardContent>
                <RiskDonut data={data.riskDistribution} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <div>
                  <CardTitle>Top flagged providers</CardTitle>
                  <CardDescription>By total billed amount across open cases.</CardDescription>
                </div>
              </CardHeader>
              <CardContent>
                <ol className="divide-y text-sm">
                  {data.topProviders.map((p, i) => (
                    <li key={p.id} className="grid grid-cols-[1.5rem_1fr_auto_auto] items-center gap-3 py-2">
                      <span className="num text-muted-foreground">{i + 1}.</span>
                      <Link href={`/cases/${p.caseId}`} className="id font-medium text-link underline-offset-4 hover:underline">
                        {p.id}
                      </Link>
                      <span className="num font-medium">{inrCompact(p.amount)}</span>
                      <RiskBadge level={p.level} />
                    </li>
                  ))}
                </ol>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Recent activity</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="divide-y text-sm">
                {data.activity.map((a) => (
                  <li key={a.id} className="flex flex-wrap items-baseline justify-between gap-x-4 py-2">
                    <span>{a.text}</span>
                    <time dateTime={a.ts} className="text-xs text-muted-foreground">
                      {timeAgo(a.ts)}
                    </time>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </div>
      ) : null}
    </>
  );
}
