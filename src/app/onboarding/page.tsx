"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Check, CircleDashed, Copy, KeyRound, Loader2, X } from "lucide-react";
import { api } from "@/lib/api";
import type { HealthData, Tenant } from "@/lib/types";
import { cn, score } from "@/lib/utils";
import { useHydrated, useTenantStore } from "@/stores";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Field, Input, Label, Switch } from "@/components/ui/form";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/state";
import { FieldMappingTable, REQUIRED_FIELDS } from "@/components/nexus/field-mapping";
import { PublicHeader } from "@/components/shell/public-header";

const STEPS = ["Company info", "API key", "Field mapping", "Output config", "Test connection"];
const REGIONS = ["US East", "US Central", "US West"];

function makeKey() {
  const bytes = new Uint8Array(24);
  crypto.getRandomValues(bytes);
  return "csn_test_" + Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

type Check = { label: string; state: "idle" | "running" | "pass" | "fail"; detail?: string };

export default function OnboardingPage() {
  const router = useRouter();
  const hydrated = useHydrated();
  const { config, setConfig, fieldMapping, setFieldMapping, setTenant } = useTenantStore();
  const step = Math.min(config.onboardingStep, STEPS.length - 1);
  const [apiKey, setApiKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [saved, setSaved] = useState("");
  const [error, setError] = useState("");
  const [checks, setChecks] = useState<Check[]>([
    { label: "Reach the ClaimShield API", state: "idle" },
    { label: "Authenticate with your API key", state: "idle" },
    { label: "Send one sample claim using your field mapping", state: "idle" },
    { label: "Receive a score", state: "idle" },
  ]);
  const [testing, setTesting] = useState(false);
  const [tenant, setTenantRecord] = useState<Tenant | null>(null);

  const go = (n: number) => {
    setError("");
    setSaved("");
    setConfig({ onboardingStep: n });
  };

  const missing = REQUIRED_FIELDS.filter((f) => !fieldMapping.some((m) => m.target === f && m.source.trim()));

  const validate = (): string => {
    if (step === 0) {
      if (!config.companyName.trim()) return "Enter your company name to continue.";
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(config.contactEmail)) return "Enter a contact email address, like name@plan.com.";
    }
    if (step === 1 && !config.apiKeyPreview) return "Generate an API key to continue.";
    if (step === 2 && missing.length) return `Map the required fields to continue: ${missing.join(", ")}.`;
    if (step === 3 && config.output.delivery === "webhook" && !/^https:\/\/.+/.test(config.output.webhookUrl)) return "Enter a webhook URL that starts with https://, or choose a different delivery method.";
    return "";
  };

  const next = () => {
    const problem = validate();
    if (problem) return setError(problem);
    go(step + 1);
  };

  const runTest = async () => {
    setTesting(true);
    setError("");
    const set = (i: number, patch: Partial<Check>) => setChecks((c) => c.map((x, j) => (j === i ? { ...x, ...patch } : x)));
    setChecks((c) => c.map((x) => ({ ...x, state: "idle", detail: undefined })));
    try {
      set(0, { state: "running" });
      const health = await api<HealthData>("/health");
      set(0, { state: "pass", detail: `Ingest API responded in ${health.services[0].latencyMs} ms` });
      set(1, { state: "running" });
      const created = await api<Tenant>("/admin/tenants", { method: "POST", body: { name: config.companyName, region: config.region, claimsPerMonth: Number(config.claimsPerMonth.replace(/\D/g, "")) } });
      setTenantRecord(created);
      set(1, { state: "pass", detail: `Key ${config.apiKeyPreview} accepted for tenant ${created.id}` });
      set(2, { state: "running" });
      const sample = Object.fromEntries(fieldMapping.filter((m) => m.target).map((m) => [m.target, m.target.endsWith("amount") ? 240 : `TEST-${m.target.toUpperCase()}`]));
      const res = await api<{ claimId: string; risk: number; level: string; latencyMs: number }>("/claims/ingest", { method: "POST", body: sample, tenantId: created.id });
      set(2, { state: "pass", detail: `Accepted ${fieldMapping.filter((m) => m.target).length} mapped fields` });
      set(3, { state: "pass", detail: `Risk ${score(res.risk)} (${res.level}) returned in ${res.latencyMs} ms` });
    } catch (e) {
      setChecks((c) => c.map((x) => (x.state === "running" ? { ...x, state: "fail", detail: e instanceof Error ? e.message : "Request failed" } : x)));
      setError("The connection test did not complete. Check the failed step and run the test again.");
    } finally {
      setTesting(false);
    }
  };

  const passed = checks.every((c) => c.state === "pass");

  const finish = () => {
    if (tenant) setTenant(tenant.id);
    setConfig({ onboardingStep: 0 });
    router.push("/dashboard");
  };

  if (!hydrated) {
    return (
      <div className="p-6">
        <Skeleton className="h-64" />
      </div>
    );
  }

  return (
    <div className="min-h-dvh">
      <PublicHeader minimal />
      <main id="main" className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
        <h1 className="text-xl font-semibold">Set up your tenant</h1>
        <ol className="mt-5 flex items-center" aria-label="Setup progress">
          {STEPS.map((s, i) => (
            <li key={s} className={cn("flex items-center", i < STEPS.length - 1 && "flex-1")} aria-current={i === step ? "step" : undefined}>
              <button
                type="button"
                disabled={i > step}
                onClick={() => go(i)}
                className="flex items-center gap-2 rounded-md disabled:cursor-not-allowed"
                aria-label={`Step ${i + 1}: ${s}${i < step ? ", completed" : ""}`}
              >
                <span
                  className={cn(
                    "num flex size-7 shrink-0 items-center justify-center rounded-full border text-xs font-semibold",
                    i < step && "border-primary bg-primary text-primary-foreground",
                    i === step && "border-primary text-foreground ring-2 ring-primary/40",
                    i > step && "text-muted-foreground",
                  )}
                >
                  {i < step ? <Check className="size-3.5" aria-hidden /> : i + 1}
                </span>
                <span className={cn("hidden text-sm md:inline", i === step ? "font-medium" : "text-muted-foreground")}>{s}</span>
              </button>
              {i < STEPS.length - 1 ? <span className={cn("mx-2 h-px flex-1", i < step ? "bg-primary" : "bg-border")} aria-hidden /> : null}
            </li>
          ))}
        </ol>

        <Card className="mt-6 p-5 sm:p-6">
          <h2 className="text-lg font-semibold">
            Step {step + 1}: {STEPS[step]}
          </h2>

          {step === 0 ? (
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <Field label="Company name" htmlFor="company">
                <Input id="company" value={config.companyName} onChange={(e) => setConfig({ companyName: e.target.value })} autoComplete="organization" />
              </Field>
              <Field label="Contact email" htmlFor="contact" hint="Setup and incident notices go here.">
                <Input id="contact" type="email" value={config.contactEmail} onChange={(e) => setConfig({ contactEmail: e.target.value })} autoComplete="email" />
              </Field>
              <Field label="Data region" htmlFor="region">
                <Select id="region" label="Data region" value={config.region} onValueChange={(v) => setConfig({ region: v })} options={REGIONS.map((r) => ({ value: r, label: r }))} />
              </Field>
              <Field label="Claims per month (estimate)" htmlFor="volume">
                <Input id="volume" inputMode="numeric" placeholder="250,000" value={config.claimsPerMonth} onChange={(e) => setConfig({ claimsPerMonth: e.target.value })} />
              </Field>
            </div>
          ) : null}

          {step === 1 ? (
            <div className="mt-4 space-y-4">
              <p className="max-w-[70ch] text-sm text-muted-foreground">
                Your claims system uses this key to send events. The full key is shown once. Store it in your secrets manager; ClaimShield keeps only the last four characters.
              </p>
              {apiKey ? (
                <div className="rounded-md border border-amber-500/50 bg-amber-500/5 p-3">
                  <Label htmlFor="apikey">Test API key</Label>
                  <div className="mt-1.5 flex gap-2">
                    <Input id="apikey" readOnly value={apiKey} className="font-mono text-xs" onFocus={(e) => e.currentTarget.select()} />
                    <Button
                      variant="outline"
                      onClick={async () => {
                        await navigator.clipboard.writeText(apiKey).catch(() => undefined);
                        setCopied(true);
                      }}
                    >
                      <Copy /> {copied ? "Copied" : "Copy key"}
                    </Button>
                  </div>
                  <p className="mt-2 text-xs text-muted-foreground">Copy it now. You will not be able to see this key again after leaving this step.</p>
                </div>
              ) : config.apiKeyPreview ? (
                <p className="text-sm">
                  A key ending in <span className="id font-semibold">{config.apiKeyPreview.slice(-4)}</span> is active. Generating a new key replaces it.
                </p>
              ) : null}
              <Button
                variant={config.apiKeyPreview ? "outline" : "default"}
                onClick={() => {
                  const k = makeKey();
                  setApiKey(k);
                  setCopied(false);
                  setConfig({ apiKeyPreview: `csn_test_...${k.slice(-4)}` });
                  setError("");
                }}
              >
                <KeyRound /> {config.apiKeyPreview ? "Generate a new key" : "Generate API key"}
              </Button>
            </div>
          ) : null}

          {step === 2 ? (
            <div className="mt-4 space-y-3">
              <p className="text-sm text-muted-foreground">Map your claims system fields to ClaimShield fields.</p>
              <FieldMappingTable mapping={fieldMapping} onChange={setFieldMapping} />
            </div>
          ) : null}

          {step === 3 ? (
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <Field label="How cases reach your team" htmlFor="delivery">
                <Select
                  id="delivery"
                  label="Delivery method"
                  value={config.output.delivery}
                  onValueChange={(v) => setConfig({ output: { ...config.output, delivery: v as typeof config.output.delivery } })}
                  options={[
                    { value: "webhook", label: "Webhook to your case system" },
                    { value: "queue-only", label: "ClaimShield queue only" },
                    { value: "sftp", label: "Daily file over SFTP" },
                  ]}
                />
              </Field>
              <Field label="Score format" htmlFor="format">
                <Select
                  id="format"
                  label="Score format"
                  value={config.output.scoreFormat}
                  onValueChange={(v) => setConfig({ output: { ...config.output, scoreFormat: v as "0-1" | "0-100" } })}
                  options={[
                    { value: "0-1", label: "0.00 to 1.00" },
                    { value: "0-100", label: "0 to 100" },
                  ]}
                />
              </Field>
              {config.output.delivery === "webhook" ? (
                <Field label="Webhook URL" htmlFor="webhook" hint="Routed cases are posted here as JSON." className="sm:col-span-2">
                  <Input id="webhook" type="url" placeholder="https://cases.yourplan.com/hooks/claimshield" value={config.output.webhookUrl} onChange={(e) => setConfig({ output: { ...config.output, webhookUrl: e.target.value } })} />
                </Field>
              ) : null}
              <div className="flex items-center justify-between gap-4 rounded-md border p-3 sm:col-span-2">
                <div>
                  <Label htmlFor="brief">Include the investigation brief</Label>
                  <p className="text-xs text-muted-foreground">Attach the plain-language brief to each routed case.</p>
                </div>
                <Switch id="brief" checked={config.output.includeBrief} onCheckedChange={(v) => setConfig({ output: { ...config.output, includeBrief: v } })} />
              </div>
              <p className="text-sm text-muted-foreground sm:col-span-2">
                ClaimShield only sends cases for review. It never pends, denies or adjusts a claim in your system.
              </p>
            </div>
          ) : null}

          {step === 4 ? (
            <div className="mt-4 space-y-4">
              <p className="text-sm text-muted-foreground">Sends one synthetic claim through the pipeline using your settings. Nothing is written to your claims system.</p>
              <ul className="divide-y rounded-md border">
                {checks.map((c) => (
                  <li key={c.label} className="flex items-start gap-3 px-3 py-2.5 text-sm">
                    {c.state === "pass" ? <Check className="mt-0.5 size-4 text-emerald-700 dark:text-emerald-300" aria-hidden /> : null}
                    {c.state === "fail" ? <X className="mt-0.5 size-4 text-red-700 dark:text-red-300" aria-hidden /> : null}
                    {c.state === "running" ? <Loader2 className="mt-0.5 size-4 animate-spin" aria-hidden /> : null}
                    {c.state === "idle" ? <CircleDashed className="mt-0.5 size-4 text-muted-foreground" aria-hidden /> : null}
                    <span>
                      {c.label}
                      <span className="sr-only">: {c.state === "pass" ? "passed" : c.state === "fail" ? "failed" : c.state === "running" ? "running" : "not run"}</span>
                      {c.detail ? <span className="block text-xs text-muted-foreground">{c.detail}</span> : null}
                    </span>
                  </li>
                ))}
              </ul>
              <Button variant={passed ? "outline" : "default"} onClick={runTest} disabled={testing}>
                {testing ? "Testing connection" : passed ? "Run test again" : "Test connection"}
              </Button>
            </div>
          ) : null}

          <div aria-live="polite" className="mt-4 min-h-5 text-sm">
            {error ? <p role="alert" className="text-red-700 dark:text-red-300">{error}</p> : null}
            {saved ? <p className="text-muted-foreground">{saved}</p> : null}
          </div>

          <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t pt-4">
            <Button variant="ghost" disabled={step === 0} onClick={() => go(step - 1)}>
              Back
            </Button>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setSaved("Draft saved in this browser. You can close this page and continue later.")}>
                Save draft
              </Button>
              {step < STEPS.length - 1 ? (
                <Button onClick={next}>Next: {STEPS[step + 1]}</Button>
              ) : (
                <Button onClick={finish} disabled={!passed}>
                  Finish setup
                </Button>
              )}
            </div>
          </div>
        </Card>
      </main>
    </div>
  );
}
