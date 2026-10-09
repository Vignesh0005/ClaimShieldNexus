"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Download } from "lucide-react";
import { useAudit } from "@/lib/api";
import { dateTime, downloadText, toCsv } from "@/lib/utils";
import { useAuthStore } from "@/stores";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/form";
import { Select } from "@/components/ui/select";
import { Empty, ErrorState, Loading, PageHeader } from "@/components/ui/state";
import { Table, Td, Th, Tr } from "@/components/ui/table";

export default function AuditPage() {
  const { data, isLoading, error, refetch } = useAudit();
  const canExport = useAuthStore((s) => s.can("export"));
  const [actor, setActor] = useState("all");
  const [q, setQ] = useState("");

  const actors = useMemo(() => [...new Set((data ?? []).map((e) => e.actor))].sort(), [data]);
  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return (data ?? [])
      .filter((e) => (actor === "all" || e.actor === actor) && (!needle || [e.action, e.caseId ?? "", e.detail ?? ""].some((v) => v.toLowerCase().includes(needle))))
      .sort((a, b) => b.ts.localeCompare(a.ts));
  }, [data, actor, q]);

  return (
    <>
      <PageHeader
        title="Audit trail"
        description="Every view, export, configuration change and decision for this tenant, newest first. Entries cannot be edited or removed."
        actions={
          <Button
            variant="outline"
            size="sm"
            disabled={!canExport || !rows.length}
            onClick={() => downloadText("audit-trail.csv", toCsv(rows.map((e) => ({ timestamp_utc: e.ts, actor: e.actor, action: e.action, case_id: e.caseId ?? "", detail: e.detail ?? "" }))))}
          >
            <Download /> Export CSV
          </Button>
        }
      />
      <div className="mb-4 flex flex-wrap gap-2">
        <Input type="search" aria-label="Search audit events" placeholder="Search by action, case or detail" className="w-full sm:w-80" value={q} onChange={(e) => setQ(e.target.value)} />
        <Select label="Filter by actor" className="w-44" value={actor} onValueChange={setActor} options={[{ value: "all", label: "All actors" }, ...actors.map((a) => ({ value: a, label: a }))]} />
      </div>
      {isLoading ? <Loading /> : null}
      {error ? <ErrorState error={error} onRetry={() => refetch()} /> : null}
      {data && !rows.length ? <Empty title="No audit events match">Change the search text or actor filter.</Empty> : null}
      {rows.length ? (
        <Card className="overflow-hidden">
          <Table>
            <caption className="sr-only">Audit events</caption>
            <thead>
              <tr>
                <Th>Time (UTC)</Th>
                <Th>Actor</Th>
                <Th>Action</Th>
                <Th>Case</Th>
                <Th>Detail</Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((e) => (
                <Tr key={e.id}>
                  <Td className="id text-muted-foreground">{dateTime(e.ts)}</Td>
                  <Td className="id">{e.actor}</Td>
                  <Td>{e.action}</Td>
                  <Td>
                    {e.caseId ? (
                      <Link href={`/cases/${e.caseId}?tab=decision`} className="id text-link underline-offset-4 hover:underline">
                        {e.caseId}
                      </Link>
                    ) : null}
                  </Td>
                  <Td className="max-w-md truncate whitespace-normal text-muted-foreground">{e.detail}</Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        </Card>
      ) : null}
    </>
  );
}
