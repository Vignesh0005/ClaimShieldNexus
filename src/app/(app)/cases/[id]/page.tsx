"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { logAudit, useAssignCase, useAudit, useCase, useCounterfactual, useEvidence, useNetwork, useTimeline } from "@/lib/api";
import type { CaseDetail, CaseStatus } from "@/lib/types";
import { STATUS_LABEL, inr, score } from "@/lib/utils";
import { useAuthStore } from "@/stores";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { ErrorState, Loading } from "@/components/ui/state";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AuditTimeline } from "@/components/nexus/audit-timeline";
import { BriefViewer } from "@/components/nexus/brief-viewer";
import { CounterfactualPanel } from "@/components/nexus/counterfactual-panel";
import { DecisionPanel } from "@/components/nexus/decision-panel";
import { EvidenceCard, MemberHarmPanel } from "@/components/nexus/evidence";
import { NetworkGraph } from "@/components/nexus/network-graph";
import { HarmBadge, RiskBadge, SignalTag } from "@/components/nexus/risk-badge";
import { SignalBreakdown, TwoAxisRisk } from "@/components/nexus/two-axis-risk";

const TABS = ["overview", "evidence", "network", "timeline", "brief", "counterfactual", "decision"] as const;
type Tab = (typeof TABS)[number];
const TAB_LABEL: Record<Tab, string> = { overview: "Overview", evidence: "Evidence", network: "Network", timeline: "Timeline", brief: "Brief", counterfactual: "Counterfactual", decision: "Decision" };
const WORKFLOW_STATUSES: CaseStatus[] = ["pending_review", "in_review", "needs_info"];
const ASSIGNEES = ["A. Sharma", "J. Okafor", "L. Chen", "Unassigned"];

function Query<T>({ q, children }: { q: { data: T | undefined; isLoading: boolean; error: unknown; refetch: () => void }; children: (data: T) => React.ReactNode }) {
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorState error={q.error} onRetry={q.refetch} />;
  return q.data ? <>{children(q.data)}</> : null;
}

function CaseHeader({ item }: { item: CaseDetail }) {
  const canAssign = useAuthStore((s) => s.can("case.assign"));
  const assign = useAssignCase(item.id);
  const facts: [string, React.ReactNode][] = [
    ["Risk", <RiskBadge key="r" score={item.risk} level={item.level} />],
    ["Amount at risk (INR)", <span key="a" className="num font-semibold">{inr(item.amount)}</span>],
    ["Members", <span key="m" className="num font-semibold">{item.members}</span>],
    ["Member harm", <HarmBadge key="h" score={item.harm} level={item.harmLevel} />],
    ["Evidence", <span key="e" className="num font-semibold">{score(item.evidence)} {item.evidence >= 0.8 ? "Strong" : item.evidence >= 0.6 ? "Moderate" : "Limited"}</span>],
  ];
  return (
    <Card className="glass-panel p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-xs text-muted-foreground">
            <Link href="/cases" className="text-link underline-offset-4 hover:underline">
              Cases
            </Link>{" "}
            / <span className="id">{item.id}</span>
          </p>
          <h1 className="mt-1 text-xl font-semibold">
            Case <span className="id">{item.id}</span>
          </h1>
          <p className="mt-1 text-sm">
            {item.providerName} (<span className="id">{item.providerId}</span>), {item.specialty}
          </p>
        </div>
        <div className="grid grid-cols-2 gap-2">
          {WORKFLOW_STATUSES.includes(item.status) ? (
            <Select
              label="Status"
              className="w-52"
              value={item.status}
              disabled={!canAssign || assign.isPending}
              onValueChange={(v) => assign.mutate({ status: v })}
              options={WORKFLOW_STATUSES.map((s) => ({ value: s, label: STATUS_LABEL[s] }))}
            />
          ) : (
            <div role="status" className="flex h-9 w-52 items-center rounded-md border bg-card px-3 text-sm">
              {STATUS_LABEL[item.status]}
            </div>
          )}
          <Select
            label="Assigned to"
            className="w-40"
            value={item.assignee}
            disabled={!canAssign || assign.isPending}
            onValueChange={(v) => assign.mutate({ assignee: v })}
            options={ASSIGNEES.map((a) => ({ value: a, label: a }))}
          />
        </div>
      </div>
      <dl className="mt-4 flex flex-wrap gap-x-8 gap-y-3 border-t pt-3 text-sm">
        {facts.map(([k, v]) => (
          <div key={k}>
            <dt className="text-xs text-muted-foreground">{k}</dt>
            <dd className="mt-0.5">{v}</dd>
          </div>
        ))}
      </dl>
    </Card>
  );
}

function Overview({ item }: { item: CaseDetail }) {
  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Suspicion against evidence</CardTitle>
          </CardHeader>
          <CardContent>
            <TwoAxisRisk item={item} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Signal breakdown</CardTitle>
          </CardHeader>
          <CardContent>
            <SignalBreakdown signals={item.signals} />
          </CardContent>
        </Card>
      </div>
      <Card>
        <CardContent className="grid gap-6 md:grid-cols-2">
          <div>
            <h3 className="text-sm font-semibold">Top flags</h3>
            <ul className="mt-2 divide-y text-sm">
              {[...item.flags].sort((a, b) => b.score - a.score).map((f) => (
                <li key={f.id} className="flex items-center justify-between gap-3 py-1.5">
                  <span className="flex items-center gap-2">
                    <SignalTag kind={f.kind} /> {f.name}
                  </span>
                  <span className="num font-medium">{score(f.score)}</span>
                </li>
              ))}
            </ul>
          </div>
          <MemberHarmPanel factors={item.harmFactors} score={item.harm} level={item.harmLevel} />
        </CardContent>
      </Card>
      {item.modelWarning ? (
        <p role="note" className="rounded-md border border-amber-500/60 bg-amber-500/10 p-3 text-sm">
          <span className="font-medium">{item.modelWarning}</span> The ML score on this case comes from that model; rule, graph and temporal findings do not depend on it.
        </p>
      ) : null}
      <Card>
        <CardHeader>
          <div>
            <CardTitle>Similar cases</CardTitle>
            <p className="text-xs text-muted-foreground">Earlier claims from other providers that were billed alike and flagged for the same reasons. Shown for comparison; not part of the risk score.</p>
          </div>
        </CardHeader>
        <CardContent>
          {item.similarCases?.length ? (
            <ul className="divide-y text-sm">
              {item.similarCases.map((s) => (
                <li key={s.claimId} className="grid grid-cols-[1fr_auto] items-center gap-x-4 gap-y-0.5 py-2 sm:grid-cols-[minmax(0,14rem)_1fr_auto_auto]">
                  <span className="id font-medium">{s.claimId}</span>
                  <span className="text-muted-foreground">
                    {s.flag}
                    {s.providerId ? <span className="id"> at {s.providerId}</span> : null}
                  </span>
                  <span className="num">
                    {Math.round(s.similarity * 100)}% similar
                  </span>
                  {s.caseId ? (
                    <Link href={`/cases/${s.caseId}`} className="id text-link underline-offset-4 hover:underline">
                      {s.caseId} ({STATUS_LABEL[s.status as CaseStatus] ?? s.status ?? "open"})
                    </Link>
                  ) : (
                    <span />
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">No similar earlier claims from other providers are on file for this case.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function EvidenceTab({ id }: { id: string }) {
  return (
    <Query q={useEvidence(id)}>
      {(data) => (
        <div className="space-y-4">
          <h2 className="sr-only">Evidence trail</h2>
          {data.items.map((e) => (
            <EvidenceCard key={e.id} item={e} />
          ))}
        </div>
      )}
    </Query>
  );
}

function TimelineTab({ id }: { id: string }) {
  return (
    <Query q={useTimeline(id)}>
      {(events) => (
        <ol className="relative ml-2 space-y-5 border-l pl-6">
          {events.map((e) => (
            <li key={e.id} className="relative">
              <span className="absolute -left-[1.85rem] top-1.5 size-2.5 rounded-full border-2 border-background bg-evidence" aria-hidden />
              <div className="flex flex-wrap items-center gap-2">
                <time dateTime={e.date} className="id text-muted-foreground">
                  {e.date}
                </time>
                <SignalTag kind={e.kind} />
              </div>
              <h3 className="mt-1 text-sm font-semibold">{e.title}</h3>
              <p className="max-w-[75ch] text-sm text-muted-foreground">{e.detail}</p>
            </li>
          ))}
        </ol>
      )}
    </Query>
  );
}

function NetworkTab({ id }: { id: string }) {
  return <Query q={useNetwork(id)}>{(data) => <NetworkGraph data={data} />}</Query>;
}

function CounterfactualTab({ id }: { id: string }) {
  return <Query q={useCounterfactual(id)}>{(data) => <CounterfactualPanel data={data} />}</Query>;
}

export default function CaseDetailPage({ params }: { params: { id: string } }) {
  const id = decodeURIComponent(params.id);
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();
  const requested = search.get("tab") as Tab | null;
  const tab: Tab = requested && TABS.includes(requested) ? requested : "overview";
  const caseQ = useCase(id);
  const audit = useAudit(id);
  const logged = useRef(new Set<string>());
  const exists = !!caseQ.data;
  const refetchAudit = audit.refetch;

  useEffect(() => {
    if (!exists) return;
    const action = tab === "evidence" ? "Viewed evidence" : tab === "network" ? "Viewed network graph" : tab === "brief" ? "Viewed brief" : tab === "overview" ? "Opened case" : null;
    if (!action || logged.current.has(action)) return;
    logged.current.add(action);
    logAudit(action, id).then(() => refetchAudit());
  }, [tab, id, exists, refetchAudit]);

  if (caseQ.isLoading) return <Loading label="Loading case" />;
  if (caseQ.error || !caseQ.data) {
    return (
      <div className="space-y-3">
        <ErrorState error={caseQ.error ?? new Error("Case not found.")} onRetry={() => caseQ.refetch()} />
        <p className="text-sm text-muted-foreground">Cases belong to one tenant. If you switched tenants, this case may not exist in the current one.</p>
        <Button asChild variant="outline">
          <Link href="/cases">Back to all cases</Link>
        </Button>
      </div>
    );
  }
  const item = caseQ.data;

  return (
    <div className="space-y-4">
      <CaseHeader item={item} />
      <Tabs value={tab} onValueChange={(v) => router.replace(`${pathname}?tab=${v}`, { scroll: false })}>
        <TabsList aria-label="Case sections">
          {TABS.map((t) => (
            <TabsTrigger key={t} value={t}>
              {TAB_LABEL[t]}
            </TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value="overview">
          <Overview item={item} />
        </TabsContent>
        <TabsContent value="evidence">
          <EvidenceTab id={id} />
        </TabsContent>
        <TabsContent value="network">
          <NetworkTab id={id} />
        </TabsContent>
        <TabsContent value="timeline">
          <TimelineTab id={id} />
        </TabsContent>
        <TabsContent value="brief">
          <BriefViewer caseId={id} />
        </TabsContent>
        <TabsContent value="counterfactual">
          <CounterfactualTab id={id} />
        </TabsContent>
        <TabsContent value="decision">
          <div className="space-y-6">
            <Card className="p-4 sm:p-5">
              <h2 className="mb-3 text-base font-semibold">
                Auditor decision for <span className="id">{id}</span>
              </h2>
              <DecisionPanel item={item} />
            </Card>
            <Card className="p-4 sm:p-5">
              <h2 className="mb-2 text-base font-semibold">Audit trail</h2>
              <Query q={audit}>{(events) => <AuditTimeline events={events} />}</Query>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
