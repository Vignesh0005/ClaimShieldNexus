"use client";

import { useMemo, useState } from "react";
import { useLogs } from "@/lib/api";
import { cn, dateTime } from "@/lib/utils";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/form";
import { Select } from "@/components/ui/select";
import { Empty, ErrorState, Loading, PageHeader } from "@/components/ui/state";
import { Table, Td, Th, Tr } from "@/components/ui/table";
import { RoleGate } from "@/components/shell/app-shell";

const LEVEL_CLASS = {
  info: "text-muted-foreground",
  warn: "font-semibold text-amber-800 dark:text-amber-200",
  error: "font-semibold text-red-700 dark:text-red-300",
};

export default function LogsPage() {
  const { data, isLoading, error, refetch } = useLogs();
  const [level, setLevel] = useState("all");
  const [service, setService] = useState("all");
  const [q, setQ] = useState("");
  const services = useMemo(() => [...new Set((data ?? []).map((l) => l.service))].sort(), [data]);
  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return (data ?? []).filter((l) => (level === "all" || l.level === level) && (service === "all" || l.service === service) && (!needle || l.message.toLowerCase().includes(needle) || l.tenantId.includes(needle)));
  }, [data, level, service, q]);

  return (
    <RoleGate allow={["admin"]}>
      <PageHeader title="System logs" description="Recent pipeline events across all tenants, newest first." />
      <div className="mb-4 flex flex-wrap gap-2">
        <Input type="search" aria-label="Search logs" placeholder="Search by message or tenant" className="w-full sm:w-80" value={q} onChange={(e) => setQ(e.target.value)} />
        <Select
          label="Filter by level"
          className="w-36"
          value={level}
          onValueChange={setLevel}
          options={[
            { value: "all", label: "All levels" },
            { value: "info", label: "Info" },
            { value: "warn", label: "Warning" },
            { value: "error", label: "Error" },
          ]}
        />
        <Select label="Filter by service" className="w-40" value={service} onValueChange={setService} options={[{ value: "all", label: "All services" }, ...services.map((s) => ({ value: s, label: s }))]} />
        <span className="num ml-auto self-center text-sm text-muted-foreground">{rows.length} entries</span>
      </div>
      {isLoading ? <Loading /> : null}
      {error ? <ErrorState error={error} onRetry={() => refetch()} /> : null}
      {data && !rows.length ? <Empty title="No log entries match">Change the search text or clear a filter.</Empty> : null}
      {rows.length ? (
        <Card className="overflow-hidden">
          <Table className="font-mono text-xs">
            <caption className="sr-only">System log entries</caption>
            <thead>
              <tr>
                <Th>Time (UTC)</Th>
                <Th>Level</Th>
                <Th>Service</Th>
                <Th>Tenant</Th>
                <Th>Message</Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((l) => (
                <Tr key={l.id}>
                  <Td className="text-muted-foreground">{dateTime(l.ts)}</Td>
                  <Td className={cn(LEVEL_CLASS[l.level])}>{l.level}</Td>
                  <Td>{l.service}</Td>
                  <Td>{l.tenantId}</Td>
                  <Td className="whitespace-normal">{l.message}</Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        </Card>
      ) : null}
    </RoleGate>
  );
}
