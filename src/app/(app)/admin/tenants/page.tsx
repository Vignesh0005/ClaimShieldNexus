"use client";

import Link from "next/link";
import { useTenants } from "@/lib/api";
import { useTenantStore } from "@/stores";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ErrorState, Loading, PageHeader } from "@/components/ui/state";
import { Table, Td, Th, Tr } from "@/components/ui/table";
import { StatusPill } from "@/components/nexus/risk-badge";
import { RoleGate } from "@/components/shell/app-shell";

const STATUS = { active: ["Active", "good"], onboarding: ["Onboarding", "warn"], suspended: ["Suspended", "neutral"] } as const;

export default function TenantsPage() {
  const { data, isLoading, error, refetch } = useTenants();
  const { tenantId, setTenant } = useTenantStore();
  return (
    <RoleGate allow={["admin"]}>
      <PageHeader
        title="Tenants"
        description="Each tenant has its own claims, cases, users and configuration. Data is never shared between tenants."
        actions={
          <Button asChild>
            <Link href="/onboarding">Add a tenant</Link>
          </Button>
        }
      />
      {isLoading ? <Loading /> : null}
      {error ? <ErrorState error={error} onRetry={() => refetch()} /> : null}
      {data ? (
        <Card className="overflow-hidden">
          <Table>
            <caption className="sr-only">Tenants</caption>
            <thead>
              <tr>
                <Th>Tenant</Th>
                <Th>Plan</Th>
                <Th>Region</Th>
                <Th className="text-right">Claims</Th>
                <Th className="text-right">Users</Th>
                <Th>Status</Th>
                <Th>Created</Th>
                <Th>
                  <span className="sr-only">Actions</span>
                </Th>
              </tr>
            </thead>
            <tbody>
              {data.map((t) => (
                <Tr key={t.id}>
                  <Td>
                    <span className="font-medium">{t.name}</span>
                    <span className="id block text-muted-foreground">{t.id}</span>
                  </Td>
                  <Td>{t.plan}</Td>
                  <Td>{t.region}</Td>
                  <Td className="num text-right">{t.claimsPerMonth === null ? "Not recorded" : t.claimsPerMonth.toLocaleString("en-IN")}</Td>
                  <Td className="num text-right">{t.users ?? "Not recorded"}</Td>
                  <Td>
                    <StatusPill tone={STATUS[t.status][1]}>{STATUS[t.status][0]}</StatusPill>
                  </Td>
                  <Td className="id text-muted-foreground">{t.createdAt}</Td>
                  <Td className="text-right">
                    {t.id === tenantId ? (
                      <span className="text-xs text-muted-foreground">Current tenant</span>
                    ) : (
                      <Button size="sm" variant="outline" onClick={() => setTenant(t.id)}>
                        Switch to tenant
                      </Button>
                    )}
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        </Card>
      ) : null}
    </RoleGate>
  );
}
