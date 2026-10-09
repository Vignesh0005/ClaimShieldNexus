"use client";

import { useState } from "react";
import { useComplianceReport, useCoverageRules, useTenants } from "@/lib/api";
import { ROLE_LABEL, ROLE_SUMMARY } from "@/lib/permissions";
import type { Role } from "@/lib/types";
import { useAuthStore, useTenantStore, type Thresholds } from "@/stores";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Field, Input, Label, Slider, Switch } from "@/components/ui/form";
import { Select } from "@/components/ui/select";
import { ErrorState, Loading, PageHeader } from "@/components/ui/state";
import { ComplianceBanner } from "@/components/nexus/compliance-banner";
import { Table, Td, Th, Tr } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { FieldMappingTable } from "@/components/nexus/field-mapping";
import { RiskBadge, SignalTag, StatusPill } from "@/components/nexus/risk-badge";
import { score } from "@/lib/utils";

const RULES = [
  { id: "duplicate_billing", name: "Duplicate billing", description: "Same member, provider, date and procedure within 7 days.", kind: "rule" as const, weight: 0.9, on: true },
  { id: "upcoding_em_level", name: "Upcoding", description: "Level 4 and 5 evaluation codes above 3 times the specialty rate.", kind: "rule" as const, weight: 0.7, on: true },
  { id: "unbundled_components", name: "Unbundling", description: "Component codes billed where a bundled code applies.", kind: "rule" as const, weight: 0.6, on: true },
  { id: "impossible_day", name: "Impossible day", description: "More than 24 hours of timed services in one day.", kind: "temporal" as const, weight: 0.85, on: true },
  { id: "referral_loop", name: "Referral loop", description: "Closed referral cycle of 3 to 8 providers.", kind: "graph" as const, weight: 0.75, on: true },
  { id: "dme_no_prior_visit", name: "DME without prior visit", description: "Equipment billed with no qualifying visit in 90 days.", kind: "rule" as const, weight: 0.65, on: true },
  { id: "identity_distance", name: "Identity distance", description: "One member ID used more than 300 km apart within 4 hours.", kind: "temporal" as const, weight: 0.8, on: false },
];

const USERS: { id: string; name: string; email: string; role: Role; lastActive: string }[] = [
  { id: "ADM-002", name: "R. Alvarez", email: "r.alvarez@demo.claimshield.example", role: "admin", lastActive: "Today" },
  { id: "AUD-007", name: "A. Sharma", email: "a.sharma@demo.claimshield.example", role: "investigator", lastActive: "Today" },
  { id: "AUD-011", name: "J. Okafor", email: "j.okafor@demo.claimshield.example", role: "investigator", lastActive: "Yesterday" },
  { id: "AUD-004", name: "L. Chen", email: "l.chen@demo.claimshield.example", role: "investigator", lastActive: "2 days ago" },
  { id: "ANL-014", name: "M. Petrov", email: "m.petrov@demo.claimshield.example", role: "analyst", lastActive: "Today" },
  { id: "VWR-021", name: "S. Doyle", email: "s.doyle@demo.claimshield.example", role: "viewer", lastActive: "Last week" },
];

const INTEGRATIONS = [
  { id: "claims", name: "Claims event stream", description: "Receives claim events from your core claims platform.", on: true },
  { id: "webhook", name: "Case webhook", description: "Posts routed cases to your case management system.", on: true },
  { id: "sso", name: "Single sign-on", description: "Sign-in through your identity provider.", on: false },
  { id: "sftp", name: "Daily SFTP export", description: "Drops a file of routed cases each night.", on: false },
  { id: "extension", name: "Browser overlay", description: "Shows a risk summary inside your existing claims screens.", on: true },
];

function CoverageRulesTab() {
  const rules = useCoverageRules();
  const report = useComplianceReport();
  if (rules.isLoading) return <Loading />;
  if (rules.error) return <ErrorState error={rules.error} onRetry={() => rules.refetch()} />;
  return (
    <div className="space-y-4">
      <ComplianceBanner />
      {report.data ? (
        <dl className="grid gap-3 sm:grid-cols-3">
          <Card className="p-4">
            <dt className="text-sm text-muted-foreground">Authoritative rules</dt>
            <dd className="num mt-1 text-2xl font-semibold">{report.data.authoritative}</dd>
            <dd className="text-xs text-muted-foreground">
              {report.data.loadedRules} of {report.data.expectedRules} from {report.data.sourceDocument}
            </dd>
          </Card>
          <Card className="p-4">
            <dt className="text-sm text-muted-foreground">Illustrative rules</dt>
            <dd className="num mt-1 text-2xl font-semibold">{report.data.illustrative}</dd>
            <dd className="text-xs text-muted-foreground">Written for the demo, not transcribed from the document</dd>
          </Card>
          <Card className="p-4">
            <dt className="text-sm text-muted-foreground">Awaiting compliance review</dt>
            <dd className="num mt-1 text-2xl font-semibold">{report.data.needsReview}</dd>
            <dd className="text-xs text-muted-foreground">Plus {report.data.referenceData.length} sample code tables</dd>
          </Card>
        </dl>
      ) : null}
      {report.data?.sourceNote ? <p className="text-sm text-muted-foreground">{report.data.sourceNote}</p> : null}
      <Card className="overflow-hidden">
        <Table>
          <caption className="sr-only">Coverage rules and their provenance</caption>
          <thead>
            <tr>
              <Th>Rule</Th>
              <Th>Source section</Th>
              <Th>Provenance</Th>
            </tr>
          </thead>
          <tbody>
            {(rules.data?.rules ?? []).map((r) => (
              <Tr key={r.id}>
                <Td className="whitespace-normal">
                  <span className="font-medium">{r.name}</span> <span className="id text-muted-foreground">{r.id}</span>
                  <span className="block text-xs text-muted-foreground">{r.description}</span>
                </Td>
                <Td className="whitespace-normal">{r.sourceSection}</Td>
                <Td>
                  <StatusPill tone={r.authoritative ? "good" : "warn"}>{r.authoritative ? "Authoritative" : "Illustrative"}</StatusPill>
                </Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      </Card>
      {report.data ? (
        <Card className="overflow-hidden">
          <Table>
            <caption className="sr-only">Sample code tables used by detection rules</caption>
            <thead>
              <tr>
                <Th>Sample code table</Th>
                <Th>Used by</Th>
                <Th>Status</Th>
                <Th>Production source</Th>
              </tr>
            </thead>
            <tbody>
              {report.data.referenceData.map((d) => (
                <Tr key={d.name}>
                  <Td className="whitespace-normal">
                    <span className="font-medium">{d.name}</span> <span className="num text-muted-foreground">({d.entries} entries)</span>
                  </Td>
                  <Td>{d.usedBy}</Td>
                  <Td className="whitespace-normal">{d.disclaimer}</Td>
                  <Td className="whitespace-normal text-muted-foreground">{d.productionSource}</Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        </Card>
      ) : null}
    </div>
  );
}

function SavedNote({ text }: { text: string }) {
  return (
    <p aria-live="polite" className="min-h-5 text-sm text-muted-foreground">
      {text}
    </p>
  );
}

export default function SettingsPage() {
  const canEdit = useAuthStore((s) => s.can("settings.edit"));
  const canManageUsers = useAuthStore((s) => s.can("users.manage"));
  const { tenantId, config, setConfig, fieldMapping, setFieldMapping, thresholds, setThresholds } = useTenantStore();
  const tenants = useTenants();
  const tenant = tenants.data?.find((t) => t.id === tenantId);
  const [rules, setRules] = useState(RULES);
  const [users, setUsers] = useState(USERS);
  const [integrations, setIntegrations] = useState(INTEGRATIONS);
  const [note, setNote] = useState("");
  const [name, setName] = useState<string | null>(null);

  const setThreshold = (key: keyof Thresholds, v: number) => {
    const next = { ...thresholds, [key]: v };
    // Keep the bands ordered: medium < high < critical.
    if (next.medium >= next.high) key === "medium" ? (next.high = Math.min(0.94, v + 0.05)) : (next.medium = Math.max(0.05, v - 0.05));
    if (next.high >= next.critical) key === "critical" ? (next.high = Math.max(0.1, v - 0.05)) : (next.critical = Math.min(0.99, next.high + 0.05));
    setThresholds(next);
    setNote("Thresholds saved. New scores use them from the next ingest.");
  };

  return (
    <>
      <PageHeader title="Settings" description={canEdit ? "Configuration for the selected tenant." : "Configuration for the selected tenant. Your role can view these settings but cannot change them."} />
      <Tabs defaultValue="profile" onValueChange={() => setNote("")}>
        <TabsList aria-label="Settings sections">
          <TabsTrigger value="profile">Profile</TabsTrigger>
          <TabsTrigger value="mapping">Field mapping</TabsTrigger>
          <TabsTrigger value="rules">Rules config</TabsTrigger>
          <TabsTrigger value="coverage">Coverage rules</TabsTrigger>
          <TabsTrigger value="thresholds">Thresholds</TabsTrigger>
          <TabsTrigger value="users">Users and roles</TabsTrigger>
          <TabsTrigger value="integrations">Integrations</TabsTrigger>
        </TabsList>

        <TabsContent value="profile">
          <Card className="max-w-2xl p-5">
            <form
              className="grid gap-4 sm:grid-cols-2"
              onSubmit={(e) => {
                e.preventDefault();
                if (name !== null) setConfig({ companyName: name });
                setNote("Profile saved.");
              }}
            >
              <Field label="Tenant name" htmlFor="t-name">
                <Input id="t-name" disabled={!canEdit} value={name ?? (config.companyName || tenant?.name || "")} onChange={(e) => setName(e.target.value)} />
              </Field>
              <Field label="Tenant ID" htmlFor="t-id" hint="Used in API requests. Cannot be changed.">
                <Input id="t-id" readOnly value={tenantId} className="font-mono text-xs" />
              </Field>
              <Field label="Contact email" htmlFor="t-email">
                <Input id="t-email" type="email" disabled={!canEdit} value={config.contactEmail} onChange={(e) => setConfig({ contactEmail: e.target.value })} />
              </Field>
              <Field label="Data region" htmlFor="t-region">
                <Select id="t-region" label="Data region" disabled={!canEdit} value={config.region} onValueChange={(v) => setConfig({ region: v })} options={["US East", "US Central", "US West"].map((r) => ({ value: r, label: r }))} />
              </Field>
              <dl className="flex flex-wrap gap-x-8 gap-y-2 border-t pt-4 text-sm sm:col-span-2">
                <div>
                  <dt className="text-xs text-muted-foreground">Plan</dt>
                  <dd>{tenant?.plan ?? "Pilot"}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Claims</dt>
                  <dd className="num">{tenant?.claimsPerMonth != null ? tenant.claimsPerMonth.toLocaleString("en-IN") : "Not recorded"}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">API key</dt>
                  <dd className="id">{config.apiKeyPreview ?? "csn_live_...4f2a"}</dd>
                </div>
              </dl>
              <div className="sm:col-span-2">
                <Button type="submit" disabled={!canEdit}>
                  Save profile
                </Button>
              </div>
            </form>
          </Card>
        </TabsContent>

        <TabsContent value="mapping">
          <div className="max-w-3xl">
            <FieldMappingTable
              mapping={fieldMapping}
              readOnly={!canEdit}
              onChange={(m) => {
                setFieldMapping(m);
                setNote("Field mapping saved.");
              }}
            />
          </div>
        </TabsContent>

        <TabsContent value="rules">
          <Card className="overflow-hidden">
            <Table>
              <caption className="sr-only">Detection rules</caption>
              <thead>
                <tr>
                  <Th>Rule</Th>
                  <Th>Type</Th>
                  <Th className="w-64">Weight in score</Th>
                  <Th>Enabled</Th>
                </tr>
              </thead>
              <tbody>
                {rules.map((r, i) => (
                  <Tr key={r.id}>
                    <Td className="whitespace-normal">
                      <span className="font-medium">{r.name}</span> <span className="id text-muted-foreground">{r.id}</span>
                      <span className="block text-xs text-muted-foreground">{r.description}</span>
                    </Td>
                    <Td>
                      <SignalTag kind={r.kind} />
                    </Td>
                    <Td>
                      <div className="flex items-center gap-3">
                        <Slider
                          thumbLabel={`Weight for ${r.name}`}
                          min={0}
                          max={1}
                          step={0.05}
                          disabled={!canEdit || !r.on}
                          value={[r.weight]}
                          onValueChange={([v]) => {
                            setRules(rules.map((x, j) => (j === i ? { ...x, weight: v } : x)));
                            setNote(`Weight for ${r.name} set to ${v.toFixed(2)}.`);
                          }}
                        />
                        <span className="num w-9 text-right">{r.weight.toFixed(2)}</span>
                      </div>
                    </Td>
                    <Td>
                      <Switch
                        aria-label={`Enable ${r.name}`}
                        disabled={!canEdit}
                        checked={r.on}
                        onCheckedChange={(v) => {
                          setRules(rules.map((x, j) => (j === i ? { ...x, on: v } : x)));
                          setNote(`${r.name} ${v ? "enabled" : "disabled"}. The change is recorded in the audit trail.`);
                        }}
                      />
                    </Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          </Card>
        </TabsContent>

        <TabsContent value="coverage">
          <CoverageRulesTab />
        </TabsContent>

        <TabsContent value="thresholds">
          <Card className="max-w-2xl space-y-6 p-5">
            <p className="text-sm text-muted-foreground">Scores at or above each value fall into that band. Cases at or above the routing threshold are sent to the SIU queue for human review.</p>
            {(
              [
                ["critical", "Critical from", <RiskBadge key="c" level="critical" />],
                ["high", "High from", <RiskBadge key="h" level="high" />],
                ["medium", "Medium from", <RiskBadge key="m" level="medium" />],
                ["routing", "Route to queue from", <StatusPill key="r">Routing</StatusPill>],
              ] as [keyof Thresholds, string, React.ReactNode][]
            ).map(([key, label, badge]) => (
              <div key={key}>
                <div className="mb-2 flex items-center justify-between text-sm">
                  <span className="flex items-center gap-2">
                    {badge} {label}
                  </span>
                  <span className="num font-semibold">{score(thresholds[key])}</span>
                </div>
                <Slider thumbLabel={label} min={0.05} max={0.99} step={0.01} disabled={!canEdit} value={[thresholds[key]]} onValueChange={([v]) => setThreshold(key, v)} />
              </div>
            ))}
            <p className="text-xs text-muted-foreground">Below {score(thresholds.medium)} is Low. In this demo the mock scoring service keeps its default bands.</p>
          </Card>
        </TabsContent>

        <TabsContent value="users">
          {!canManageUsers ? <p className="mb-3 rounded-md border border-dashed p-3 text-sm">Only an Admin can change roles.</p> : null}
          <Card className="overflow-hidden">
            <Table>
              <caption className="sr-only">Users and roles</caption>
              <thead>
                <tr>
                  <Th>User</Th>
                  <Th>ID</Th>
                  <Th>Role</Th>
                  <Th>Last active</Th>
                </tr>
              </thead>
              <tbody>
                {users.map((u, i) => (
                  <Tr key={u.id}>
                    <Td>
                      <span className="font-medium">{u.name}</span>
                      <span className="block text-xs text-muted-foreground">{u.email}</span>
                    </Td>
                    <Td className="id">{u.id}</Td>
                    <Td>
                      <Select
                        label={`Role for ${u.name}`}
                        className="h-8 w-44 text-xs"
                        disabled={!canManageUsers}
                        value={u.role}
                        onValueChange={(v) => {
                          setUsers(users.map((x, j) => (j === i ? { ...x, role: v as Role } : x)));
                          setNote(`${u.name} is now ${ROLE_LABEL[v as Role]}.`);
                        }}
                        options={(Object.keys(ROLE_LABEL) as Role[]).map((r) => ({ value: r, label: ROLE_LABEL[r] }))}
                      />
                    </Td>
                    <Td className="text-muted-foreground">{u.lastActive}</Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          </Card>
          <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2 xl:grid-cols-4">
            {(Object.keys(ROLE_LABEL) as Role[]).map((r) => (
              <div key={r} className="rounded-md border p-3">
                <dt className="font-medium">{ROLE_LABEL[r]}</dt>
                <dd className="mt-0.5 text-xs text-muted-foreground">{ROLE_SUMMARY[r]}</dd>
              </div>
            ))}
          </dl>
        </TabsContent>

        <TabsContent value="integrations">
          <ul className="grid gap-3 md:grid-cols-2">
            {integrations.map((it, i) => (
              <li key={it.id}>
                <Card className="flex h-full items-start justify-between gap-4 p-4">
                  <div>
                    <Label htmlFor={`int-${it.id}`}>{it.name}</Label>
                    <p className="mt-0.5 text-sm text-muted-foreground">{it.description}</p>
                    <p className="mt-2">{it.on ? <StatusPill tone="good">Connected</StatusPill> : <StatusPill>Not connected</StatusPill>}</p>
                  </div>
                  <Switch
                    id={`int-${it.id}`}
                    disabled={!canEdit}
                    checked={it.on}
                    onCheckedChange={(v) => {
                      setIntegrations(integrations.map((x, j) => (j === i ? { ...x, on: v } : x)));
                      setNote(`${it.name} ${v ? "connected" : "disconnected"}.`);
                    }}
                  />
                </Card>
              </li>
            ))}
          </ul>
        </TabsContent>
      </Tabs>
      <div className="mt-3">
        <SavedNote text={note} />
      </div>
    </>
  );
}
