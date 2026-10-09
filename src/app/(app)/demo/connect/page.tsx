"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Check, CircleDashed, Loader2 } from "lucide-react";
import { api, useCases } from "@/lib/api";
import type { HealthData } from "@/lib/types";
import { cn, inr } from "@/lib/utils";
import { useTenantStore } from "@/stores";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { PageHeader } from "@/components/ui/state";
import { OverlayBubble } from "@/components/nexus/overlay-bubble";
import { RiskBadge } from "@/components/nexus/risk-badge";

const SYSTEMS = ["Legacy mainframe claims (flat file)", "Core claims platform (event stream)", "Clearinghouse feed (X12 837)"];
const STEPS = ["Open a secure connection", "Read the field layout", "Apply your saved field mapping", "Stream the first claims", "Score claims as they arrive"];

type Row = { id: string; provider: string; amount: number; risk: number };

export default function ConnectPage() {
  const tenantId = useTenantStore((s) => s.tenantId);
  const mapped = useTenantStore((s) => s.fieldMapping.filter((m) => m.target).length);
  const { data: cases } = useCases();
  const [system, setSystem] = useState(SYSTEMS[0]);
  const [stage, setStage] = useState(-1);
  const [rows, setRows] = useState<Row[]>([]);
  const [error, setError] = useState("");
  const [picked, setPicked] = useState<string | null>(null);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(() => () => timers.current.forEach(clearTimeout), []);

  const top = cases?.[0];
  const running = stage >= 0 && stage < STEPS.length;
  const done = stage >= STEPS.length;

  const connect = async () => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
    setRows([]);
    setError("");
    setStage(0);
    try {
      await api<HealthData>("/health");
    } catch (e) {
      setStage(-1);
      setError(`The connection could not be opened: ${e instanceof Error ? e.message : "request failed"}. Try again.`);
      return;
    }
    const sample: Row[] = (cases ?? []).slice(0, 4).map((c, i) => ({ id: `CLM-2025-00${421 + i * 17}`, provider: c.providerId, amount: Math.round(c.amount / c.members / 3), risk: c.risk }));
    const filler: Row[] = [0.08, 0.12, 0.05, 0.21].map((risk, i) => ({ id: `CLM-2025-01${102 + i * 9}`, provider: `PRV-${2013 + i * 13}`, amount: 180 + i * 95, risk }));
    const stream = [filler[0], sample[0], filler[1], filler[2], sample[1], filler[3], sample[2], sample[3]].filter(Boolean);
    STEPS.forEach((_, i) => timers.current.push(setTimeout(() => setStage(i + 1), 700 * (i + 1))));
    stream.forEach((r, i) => timers.current.push(setTimeout(() => setRows((prev) => [r, ...prev]), 700 * 4 + 350 * (i + 1))));
  };

  const IdButton = ({ id }: { id: string }) => (
    <button
      type="button"
      onClick={() => setPicked(id)}
      aria-label={`Look up ${id} in ClaimShield`}
      className={cn("id rounded-sm border border-dashed border-slate-500 px-1 hover:border-electric hover:bg-electric/10", picked === id && "border-solid border-electric bg-electric/15")}
    >
      {id}
    </button>
  );

  return (
    <>
      <PageHeader
        title="Connect a tenant"
        description="Watch a claims system connect and its first claims receive scores. Then see how the same scores appear inside an existing claims screen."
      />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="p-4 sm:p-5">
          <h2 className="text-base font-semibold">1. Connect a claims system</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Connecting as tenant <span className="id">{tenantId}</span> with {mapped} mapped fields. Nothing is written back to the source system.
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <Select label="Source system" className="min-w-0 flex-1" value={system} onValueChange={setSystem} disabled={running} options={SYSTEMS.map((s) => ({ value: s, label: s }))} />
            <Button onClick={connect} disabled={running}>
              {running ? "Connecting" : done ? "Connect again" : "Connect"}
            </Button>
          </div>
          <ol className="mt-4 space-y-2 text-sm" aria-live="polite">
            {STEPS.map((s, i) => {
              const state = stage > i ? "done" : stage === i ? "running" : "idle";
              return (
                <li key={s} className={cn("flex items-center gap-2", state === "idle" && "text-muted-foreground")}>
                  {state === "done" ? <Check className="size-4 text-emerald-700 dark:text-emerald-300" aria-hidden /> : state === "running" ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <CircleDashed className="size-4" aria-hidden />}
                  {s}
                  <span className="sr-only">{state === "done" ? ", complete" : state === "running" ? ", in progress" : ""}</span>
                </li>
              );
            })}
          </ol>
          {error ? (
            <p role="alert" className="mt-3 rounded-md border border-red-600/40 bg-red-600/5 p-3 text-sm">
              {error}
            </p>
          ) : null}
          {done ? (
            <p className="mt-4 rounded-md border border-emerald-500/40 bg-emerald-500/10 p-3 text-sm">
              Connected to {system}. Scored claims are arriving.{" "}
              <Link href="/dashboard" className="font-medium text-link underline-offset-4 hover:underline">
                Open the dashboard
              </Link>
            </p>
          ) : null}
        </Card>

        <Card className="p-4 sm:p-5">
          <h2 className="text-base font-semibold">First claims scored</h2>
          {rows.length === 0 ? (
            <p className="mt-2 text-sm text-muted-foreground">Claims appear here once the connection is streaming.</p>
          ) : (
            <ul className="mt-3 divide-y text-sm">
              {rows.map((r) => (
                <li key={r.id} className="grid grid-cols-[1fr_auto_auto] items-center gap-3 py-1.5">
                  <span>
                    <span className="id font-medium">{r.id}</span> <span className="id text-muted-foreground">{r.provider}</span>
                  </span>
                  <span className="num">{inr(r.amount)}</span>
                  <RiskBadge score={r.risk} />
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <h2 className="mt-8 text-base font-semibold">2. See scores inside your existing claims screen</h2>
      <p className="mt-1 max-w-[75ch] text-sm text-muted-foreground">
        The browser extension adds a ClaimShield summary to the claims system your team already uses. Select any outlined ID below to look it up. In the extension you can also hold Alt and draw a circle around an ID.
      </p>
      <div className="relative mt-3 min-h-[25rem] overflow-hidden rounded-lg border-2 border-slate-400 bg-[#E8E4D8] p-4 font-mono text-sm text-slate-900 sm:p-6">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2 border-b-2 border-slate-500 pb-2">
          <span className="font-bold">CLAIMS INQUIRY - SCREEN CI04</span>
          <span>Mock legacy claims system</span>
        </div>
        <dl className="grid max-w-xl grid-cols-[9rem_1fr] gap-y-2">
          <dt>CLAIM ID</dt>
          <dd>
            <IdButton id="CLM-2025-00421" />
          </dd>
          <dt>MEMBER</dt>
          <dd>
            <IdButton id="MBR-8821" />
          </dd>
          <dt>PROVIDER</dt>
          <dd>
            <IdButton id={top?.providerId ?? "PRV-1042"} />
          </dd>
          <dt>SVC DATE</dt>
          <dd>2025-01-08</dd>
          <dt>PROC CODE</dt>
          <dd>99215</dd>
          <dt>BILLED AMT</dt>
          <dd>12,400.00</dd>
          <dt>STATUS</dt>
          <dd>PAID</dd>
          <dt>RELATED CASE</dt>
          <dd>{top ? <IdButton id={top.id} /> : "NONE"}</dd>
        </dl>
        <p className="mt-6 text-xs text-slate-700">PF3=EXIT PF7=PREV PF8=NEXT</p>
        <div className="font-sans">
          <OverlayBubble entityId={picked} onClose={() => setPicked(null)} />
        </div>
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        To try the real extension, load the <span className="font-mono">extension</span> folder from this project as an unpacked extension in Chrome.
      </p>
    </>
  );
}
