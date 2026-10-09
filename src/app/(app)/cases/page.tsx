"use client";

import { useMemo } from "react";
import Link from "next/link";
import { useCases } from "@/lib/api";
import type { CaseStatus, RiskLevel } from "@/lib/types";
import { RISK_LABEL, STATUS_LABEL, inr } from "@/lib/utils";
import { useCaseStore } from "@/stores";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/form";
import { Select } from "@/components/ui/select";
import { Empty, ErrorState, Loading, PageHeader } from "@/components/ui/state";
import { Table, Td, Th, Tr } from "@/components/ui/table";
import { HarmBadge, RiskBadge } from "@/components/nexus/risk-badge";

export default function CasesPage() {
  const { data, isLoading, error, refetch } = useCases();
  const { severity, status, search, set } = useCaseStore();

  const rows = useMemo(() => {
    const q = search.trim().toLowerCase();
    return (data ?? []).filter(
      (c) =>
        (severity === "all" || c.level === severity) &&
        (status === "all" || c.status === status) &&
        (!q || [c.id, c.providerId, c.providerName, c.specialty, c.rule, c.assignee].some((v) => v.toLowerCase().includes(q))),
    );
  }, [data, severity, status, search]);

  return (
    <>
      <PageHeader title="Cases" description="Every flagged cluster for this tenant, including those outside current review capacity." />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Input
          type="search"
          aria-label="Search cases"
          placeholder="Search by case, provider, specialty or flag"
          className="w-full sm:w-80"
          value={search}
          onChange={(e) => set({ search: e.target.value })}
        />
        <Select
          label="Filter by severity"
          className="w-44"
          value={severity}
          onValueChange={(v) => set({ severity: v as RiskLevel | "all" })}
          options={[{ value: "all", label: "All severity" }, ...(["critical", "high", "medium", "low"] as RiskLevel[]).map((l) => ({ value: l, label: RISK_LABEL[l] }))]}
        />
        <Select
          label="Filter by status"
          className="w-56"
          value={status}
          onValueChange={(v) => set({ status: v })}
          options={[{ value: "all", label: "All statuses" }, ...(Object.keys(STATUS_LABEL) as CaseStatus[]).map((s) => ({ value: s, label: STATUS_LABEL[s] }))]}
        />
        <span className="num ml-auto text-sm text-muted-foreground">
          {rows.length} of {data?.length ?? 0} shown
        </span>
      </div>
      {isLoading ? <Loading /> : null}
      {error ? <ErrorState error={error} onRetry={() => refetch()} /> : null}
      {data && rows.length === 0 ? <Empty title="No cases match">Change the search text or clear a filter.</Empty> : null}
      {rows.length ? (
        <Card className="overflow-hidden">
          <Table>
            <caption className="sr-only">Flagged cases</caption>
            <thead>
              <tr>
                <Th>Case ID</Th>
                <Th>Provider</Th>
                <Th>Specialty</Th>
                <Th>Primary flag</Th>
                <Th>Risk</Th>
                <Th className="text-right">Amount</Th>
                <Th className="text-right">Members</Th>
                <Th>Harm</Th>
                <Th>Status</Th>
                <Th>Assigned to</Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <Tr key={c.id}>
                  <Td>
                    <Link href={`/cases/${c.id}`} className="id font-medium text-link underline-offset-4 hover:underline">
                      {c.id}
                    </Link>
                  </Td>
                  <Td className="id">{c.providerId}</Td>
                  <Td>{c.specialty}</Td>
                  <Td>{c.rule}</Td>
                  <Td>
                    <RiskBadge score={c.risk} level={c.level} />
                  </Td>
                  <Td className="num text-right">{inr(c.amount)}</Td>
                  <Td className="num text-right">{c.members}</Td>
                  <Td>
                    <HarmBadge score={c.harm} level={c.harmLevel} />
                  </Td>
                  <Td>{STATUS_LABEL[c.status]}</Td>
                  <Td>{c.assignee}</Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        </Card>
      ) : null}
    </>
  );
}
