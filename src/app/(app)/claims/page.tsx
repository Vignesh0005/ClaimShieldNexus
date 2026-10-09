"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { buildTestClaim } from "@/lib/adapters/claim.adapter";
import type { ClaimRow } from "@/lib/types";
import { inr, score } from "@/lib/utils";
import { useAuthStore, useTenantStore } from "@/stores";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Empty, ErrorState, Loading, PageHeader } from "@/components/ui/state";
import { Table, Td, Th, Tr } from "@/components/ui/table";
import { RiskBadge, StatusPill } from "@/components/nexus/risk-badge";

const COVERAGE: Record<string, string> = {
  COVERABLE: "Coverable",
  COVERABLE_WITH_CONDITIONS: "Coverable with conditions",
  COVERAGE_REVIEW_REQUIRED: "Coverage review required",
  NOT_COVERABLE: "Coverage issue — needs claims review",
};

function coverageBlocked(claim: ClaimRow) {
  return claim.status === "processed" && claim.risk === null &&
    (claim.coverageStatus === "NOT_COVERABLE" || claim.coverageStatus === "COVERAGE_REVIEW_REQUIRED");
}

function processingLabel(claim: ClaimRow) {
  if (claim.status === "failed") return "Processing failed";
  if (claim.status !== "processed") return "Processing";
  if (coverageBlocked(claim)) return "Completed — coverage review needed";
  return claim.risk === null ? "Completed — no score available" : "Completed — risk scored";
}

export default function ClaimsPage() {
  const tenantId = useTenantStore((s) => s.tenantId);
  const role = useAuthStore((s) => s.role);
  const qc = useQueryClient();
  const [last, setLast] = useState<ClaimRow | null>(null);
  const claims = useQuery({ queryKey: ["claims", tenantId, "list"], queryFn: () => api<ClaimRow[]>("/claims?limit=100") });
  const ingest = useMutation({
    mutationFn: () => api<ClaimRow>("/claims", { method: "POST", body: buildTestClaim(`CLM-UI-${Date.now().toString(36).toUpperCase()}`) }),
    onSuccess: (row) => {
      setLast(row);
      qc.invalidateQueries({ queryKey: ["claims"] });
      qc.invalidateQueries({ queryKey: ["funnel"] });
    },
  });

  return (
    <>
      <PageHeader
        title="Claims"
        description="The 100 highest-risk claims for this tenant, with their coverage outcome and risk score. A coverage outcome is never a fraud signal and never a denial."
        actions={
          <Button onClick={() => ingest.mutate()} disabled={ingest.isPending || role !== "admin"} title={role === "admin" ? undefined : "Only an Admin can send claims from this screen. Claims systems use an API key."}>
            {ingest.isPending ? "Sending claim" : "Send a test claim"}
          </Button>
        }
      />
      <div aria-live="polite" className="mb-3 text-sm">
        {last ? (
          <p className="rounded-md border border-emerald-500/40 bg-emerald-500/10 p-3">
            Claim <span className="id font-semibold">{last.id}</span> was received: coverage {COVERAGE[last.coverageStatus ?? ""] ?? "pending"}, risk{" "}
            <span className="num font-semibold">{last.risk === null ? "not scored" : score(last.risk)}</span>. {coverageBlocked(last) ? "Coverage checks stopped fraud assessment; claims review is needed." : processingLabel(last)}.
          </p>
        ) : null}
        {ingest.isError ? <p role="alert" className="rounded-md border border-red-600/40 bg-red-600/5 p-3">The claim was not ingested: {(ingest.error as Error).message}</p> : null}
      </div>
      {claims.isLoading ? <Loading /> : null}
      {claims.error ? <ErrorState error={claims.error} onRetry={() => claims.refetch()} /> : null}
      {claims.data && !claims.data.length ? <Empty title="No claims yet">Send a test claim, or connect a claims system.</Empty> : null}
      {claims.data?.length ? (
        <Card className="overflow-hidden">
          <Table>
            <caption className="sr-only">Claims</caption>
            <thead>
              <tr>
                <Th>Claim ID</Th>
                <Th>Member</Th>
                <Th>Provider</Th>
                <Th>Service date</Th>
                <Th className="text-right">Billed</Th>
                <Th>Coverage</Th>
                <Th>Risk</Th>
                <Th>Processing result</Th>
              </tr>
            </thead>
            <tbody>
              {[...(last && !claims.data.some((c) => c.id === last.id) ? [last] : []), ...claims.data].map((c) => (
                <Tr key={c.id} className={c.id === last?.id ? "bg-primary/5" : undefined}>
                  <Td className="id font-medium">{c.id}</Td>
                  <Td className="id">{c.memberId}</Td>
                  <Td className="id">{c.providerId}</Td>
                  <Td className="id">{c.serviceDate}</Td>
                  <Td className="num text-right">{inr(c.billed)}</Td>
                  <Td>{COVERAGE[c.coverageStatus ?? ""] ?? "Pending"}</Td>
                  <Td>{c.risk === null || c.level === null ? (
                    <div className="max-w-56 text-xs text-muted-foreground">
                      <span className="block font-medium">{c.status === "processing" ? "Awaiting assessment" : "Not scored"}</span>
                      {coverageBlocked(c) ? <span className="mt-1 block">Coverage checks stopped fraud assessment.</span> : c.status === "failed" ? <span className="mt-1 block">Processing failed before a score was available.</span> : null}
                    </div>
                  ) : <RiskBadge score={c.risk} level={c.level} />}</Td>
                  <Td>
                    <StatusPill tone={c.status === "failed" || coverageBlocked(c) || (c.status === "processed" && c.risk === null) ? "warn" : c.status === "processed" ? "good" : "neutral"}>{processingLabel(c)}</StatusPill>
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        </Card>
      ) : null}
    </>
  );
}
