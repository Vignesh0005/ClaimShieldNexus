"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { Download, Printer, UserRoundPlus } from "lucide-react";
import { api, logAudit, useQueue } from "@/lib/api";
import type { Brief, CaseSummary, RiskLevel } from "@/lib/types";
import { cn, downloadText, RISK_LABEL, STATUS_LABEL, toCsv, inr } from "@/lib/utils";
import { useAuthStore, useCaseStore, useQueueStore, type CaseSort } from "@/stores";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { Empty, ErrorState, Loading, PageHeader } from "@/components/ui/state";
import { Table, Td, Th, Tr } from "@/components/ui/table";
import { CapacityOptimizer } from "@/components/nexus/capacity-optimizer";
import { HarmBadge, RiskBadge, StatusPill } from "@/components/nexus/risk-badge";

const ASSIGNEES = ["A. Sharma", "J. Okafor", "L. Chen"];

function printBriefs(briefs: Brief[]) {
  const w = window.open("", "_blank");
  if (!w) return false;
  const esc = (s: string) => s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c]!);
  const list = (items: string[]) => `<ul>${items.map((i) => `<li>${esc(i)}</li>`).join("")}</ul>`;
  w.document.write(
    `<title>SIU briefs</title><style>body{font:12px/1.5 system-ui,sans-serif;margin:32px;color:#0f172a}article{page-break-after:always}h1{font-size:16px}h2{font-size:12px;border-bottom:1px solid #cbd5e1;margin-top:14px}.d{background:#fef3c7;padding:4px 8px;font-size:11px}</style>` +
      briefs
        .map(
          (b) =>
            `<article><p class="d">${esc(b.disclaimer)}</p><h1>SIU investigation brief: ${esc(b.caseId)}</h1><p>Provider: ${esc(b.provider)}<br>Risk score: ${esc(b.riskLine)}<br>Potential amount (INR): ${inr(b.amount)}<br>Members affected: ${b.members}<br>Member harm score: ${esc(b.harmLine)}</p><h2>Evidence</h2>${list(b.evidence)}<h2>Timeline</h2>${list(b.timeline)}<h2>Limitations</h2>${list(b.limitations)}<h2>Recommended action</h2><p>${esc(b.recommendedAction)}</p></article>`,
        )
        .join(""),
  );
  w.document.close();
  w.focus();
  w.print();
  return true;
}

function CasePreview({ item, inCapacity }: { item: CaseSummary | undefined; inCapacity: boolean }) {
  if (!item) return <p className="text-sm text-muted-foreground">Move focus to a row, or hover over it, to preview the case here.</p>;
  const rows: [string, React.ReactNode][] = [
    ["Provider", <span key="p" className="id">{item.providerId}</span>],
    ["Specialty", item.specialty],
    ["Primary flag", item.rule],
    ["Risk", <RiskBadge key="r" score={item.risk} level={item.level} />],
    ["Member harm", <HarmBadge key="h" score={item.harm} level={item.harmLevel} />],
    ["Amount", inr(item.amount)],
    ["Members", item.members],
    ["Review time", `${item.hours} hours`],
    ["Status", STATUS_LABEL[item.status]],
    ["Assigned to", item.assignee],
  ];
  return (
    <>
      <p className="id text-base font-semibold">{item.id}</p>
      <p className="mt-1">{inCapacity ? <StatusPill tone="good">Fits current capacity</StatusPill> : <StatusPill>Outside current capacity</StatusPill>}</p>
      <dl className="mt-3 divide-y text-sm">
        {rows.map(([k, v]) => (
          <div key={k} className="flex items-center justify-between gap-3 py-1.5">
            <dt className="text-muted-foreground">{k}</dt>
            <dd className="num text-right">{v}</dd>
          </div>
        ))}
      </dl>
      <Button asChild className="mt-4 w-full">
        <Link href={`/cases/${item.id}`}>Open case</Link>
      </Button>
    </>
  );
}

export default function QueuePage() {
  const qc = useQueryClient();
  const { investigators, hours, checked, toggle, setChecked } = useQueueStore();
  const { severity, rule, sort, selectedCaseId, set } = useCaseStore();
  const canExport = useAuthStore((s) => s.can("export"));
  const canAssign = useAuthStore((s) => s.can("case.assign"));
  const { data, isLoading, error, refetch } = useQueue({ investigators, hours });
  const [assignee, setAssignee] = useState(ASSIGNEES[0]);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);

  const rank = useMemo(() => new Map((data?.cases ?? []).map((c, i) => [c.id, i + 1])), [data]);
  const rules = useMemo(() => [...new Set((data?.cases ?? []).map((c) => c.rule))].sort(), [data]);
  const selected = useMemo(() => new Set(data?.selected ?? []), [data]);

  const rows = useMemo(() => {
    let r = (data?.cases ?? []).filter((c) => (severity === "all" || c.level === severity) && (rule === "all" || c.rule === rule));
    if (sort === "amount") r = [...r].sort((a, b) => b.amount - a.amount);
    if (sort === "harm") r = [...r].sort((a, b) => b.harm - a.harm);
    return r;
  }, [data, severity, rule, sort]);

  const targets = checked.length ? checked.filter((id) => rank.has(id)) : (data?.selected ?? []);
  const targetLabel = checked.length ? `${targets.length} checked` : `${targets.length} in capacity`;
  const allChecked = rows.length > 0 && rows.every((c) => checked.includes(c.id));

  const exportCsv = () => {
    const out = (data?.cases ?? [])
      .filter((c) => targets.includes(c.id))
      .map((c) => ({ rank: rank.get(c.id)!, case_id: c.id, provider_id: c.providerId, risk: c.risk, level: c.level, amount_inr: c.amount, harm: c.harm, hours: c.hours, status: c.status, assignee: c.assignee }));
    downloadText("siu-queue.csv", toCsv(out));
    logAudit("Exported queue as CSV", undefined, `${out.length} cases`);
    setStatus(`Exported ${out.length} cases to siu-queue.csv.`);
  };

  const print = async () => {
    setBusy(true);
    setStatus(`Preparing ${targets.length} briefs.`);
    try {
      const briefs = await Promise.all(targets.map((id) => api<Brief>(`/cases/${id}/brief`, { method: "POST", body: { type: "technical" } })));
      setStatus(printBriefs(briefs) ? `Opened ${briefs.length} briefs for printing.` : "The print window was blocked. Allow pop-ups for this site and try again.");
    } catch (e) {
      setStatus(`Briefs could not be prepared: ${e instanceof Error ? e.message : "request failed"}`);
    } finally {
      setBusy(false);
    }
  };

  const bulkAssign = async () => {
    setBusy(true);
    try {
      await Promise.all(targets.map((id) => api(`/cases/${id}/assign`, { method: "POST", body: { assignee, actor: useAuthStore.getState().user?.id } })));
      await qc.invalidateQueries();
      setStatus(`Assigned ${targets.length} cases to ${assignee}.`);
      setChecked([]);
    } catch (e) {
      setStatus(`Cases could not be assigned: ${e instanceof Error ? e.message : "request failed"}`);
    } finally {
      setBusy(false);
    }
  };

  const preview = data?.cases.find((c) => c.id === selectedCaseId);

  return (
    <>
      <PageHeader title="SIU investigation queue" description="Flagged clusters ranked by priority. Cases marked as in capacity fit the review hours set below." />
      {error ? <ErrorState error={error} onRetry={() => refetch()} /> : null}
      <div className="space-y-4">
        <CapacityOptimizer data={data} />

        <div className="flex flex-wrap items-center gap-2">
          <Select
            label="Filter by rule"
            className="w-52"
            value={rule}
            onValueChange={(v) => set({ rule: v })}
            options={[{ value: "all", label: "All rules" }, ...rules.map((r) => ({ value: r, label: r }))]}
          />
          <Select
            label="Filter by severity"
            className="w-44"
            value={severity}
            onValueChange={(v) => set({ severity: v as RiskLevel | "all" })}
            options={[{ value: "all", label: "All severity" }, ...(["critical", "high", "medium", "low"] as RiskLevel[]).map((l) => ({ value: l, label: RISK_LABEL[l] }))]}
          />
          <Select
            label="Sort"
            className="w-48"
            value={sort}
            onValueChange={(v) => set({ sort: v as CaseSort })}
            options={[
              { value: "priority", label: "Sort: priority" },
              { value: "amount", label: "Sort: amount" },
              { value: "harm", label: "Sort: member harm" },
            ]}
          />
          <span className="num ml-auto text-sm text-muted-foreground">
            {rows.length} of {data?.total ?? 0} shown
          </span>
        </div>

        {isLoading ? <Loading /> : null}
        {data ? (
          <div className="grid gap-4 wide:grid-cols-[minmax(0,1fr)_20rem]">
            <Card className="overflow-hidden">
              {rows.length === 0 ? (
                <Empty title="No cases match these filters">Clear a filter to see more of the queue.</Empty>
              ) : (
                <Table>
                  <caption className="sr-only">SIU queue ranked by priority</caption>
                  <thead>
                    <tr>
                      <Th className="w-8">
                        <input
                          type="checkbox"
                          aria-label="Select all shown cases"
                          checked={allChecked}
                          onChange={() => setChecked(allChecked ? checked.filter((id) => !rows.some((c) => c.id === id)) : [...new Set([...checked, ...rows.map((c) => c.id)])])}
                        />
                      </Th>
                      <Th className="text-right">#</Th>
                      <Th>Case ID</Th>
                      <Th>Provider</Th>
                      <Th>Risk</Th>
                      <Th className="text-right">Amount</Th>
                      <Th>Harm</Th>
                      <Th className="text-right">Hours</Th>
                      <Th>Capacity</Th>
                      <Th>Assigned to</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((c) => (
                      <Tr
                        key={c.id}
                        className={cn(!selected.has(c.id) && "text-muted-foreground", selectedCaseId === c.id && "bg-primary/5")}
                        onMouseEnter={() => set({ selectedCaseId: c.id })}
                        onFocus={() => set({ selectedCaseId: c.id })}
                      >
                        <Td>
                          <input type="checkbox" aria-label={`Select ${c.id}`} checked={checked.includes(c.id)} onChange={() => toggle(c.id)} />
                        </Td>
                        <Td className="num text-right">{rank.get(c.id)}</Td>
                        <Td>
                          <Link href={`/cases/${c.id}`} className="id font-medium text-link underline-offset-4 hover:underline">
                            {c.id}
                          </Link>
                        </Td>
                        <Td className="id">{c.providerId}</Td>
                        <Td>
                          <RiskBadge score={c.risk} level={c.level} />
                        </Td>
                        <Td className="num text-right">{inr(c.amount)}</Td>
                        <Td>
                          <HarmBadge score={c.harm} level={c.harmLevel} />
                        </Td>
                        <Td className="num text-right">{c.hours}</Td>
                        <Td>{selected.has(c.id) ? <StatusPill tone="good">In capacity</StatusPill> : <span className="text-xs">Not selected</span>}</Td>
                        <Td>{c.assignee}</Td>
                      </Tr>
                    ))}
                  </tbody>
                </Table>
              )}
            </Card>
            <Card className="sticky top-0 hidden h-fit p-4 wide:block" aria-label="Case preview">
              <h2 className="mb-2 text-sm font-semibold">Case preview</h2>
              <CasePreview item={preview} inCapacity={!!preview && selected.has(preview.id)} />
            </Card>
          </div>
        ) : null}

        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm text-muted-foreground">Apply to {targetLabel}:</span>
          <Button variant="outline" size="sm" onClick={exportCsv} disabled={!canExport || !targets.length}>
            <Download /> Export CSV
          </Button>
          <Button variant="outline" size="sm" onClick={print} disabled={!canExport || !targets.length || busy}>
            <Printer /> Print briefs
          </Button>
          <Select label="Assign to" className="h-8 w-36 text-xs" value={assignee} onValueChange={setAssignee} options={ASSIGNEES.map((a) => ({ value: a, label: a }))} disabled={!canAssign} />
          <Button variant="outline" size="sm" onClick={bulkAssign} disabled={!canAssign || !targets.length || busy}>
            <UserRoundPlus /> Bulk assign
          </Button>
        </div>
        <p aria-live="polite" className="min-h-5 text-sm text-muted-foreground">
          {status || (!canExport ? "Your role cannot export or assign cases." : "")}
        </p>
      </div>
    </>
  );
}
