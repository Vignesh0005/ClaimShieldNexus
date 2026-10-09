"use client";

import { useState } from "react";
import { Copy, FileDown } from "lucide-react";
import { logAudit, useBrief } from "@/lib/api";
import type { Brief } from "@/lib/types";
import { cn, inr, score } from "@/lib/utils";
import { useAuthStore } from "@/stores";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ErrorState, Loading } from "@/components/ui/state";

function briefText(b: Brief) {
  return [
    `SIU investigation brief: ${b.caseId}`,
    `Provider: ${b.provider}`,
    `Risk score: ${b.riskLine}`,
    `Potential amount (INR): ${inr(b.amount)}`,
    `Members affected: ${b.members}`,
    `Member harm score: ${b.harmLine}`,
    "",
    "Evidence",
    ...b.evidence.map((e, i) => `${i + 1}. ${e}`),
    "",
    "Timeline",
    ...b.timeline.map((t) => `- ${t}`),
    "",
    `Network context: ${b.network.text}`,
    `Confidence: ${score(b.confidence)}`,
    "",
    "Limitations",
    ...b.limitations.map((l) => `- ${l}`),
    "",
    `Recommended action: ${b.recommendedAction}`,
    "",
    b.disclaimer,
  ].join("\n");
}

function MiniGraph({ providers, members }: { providers: number; members: number }) {
  const cx = 110;
  const cy = 62;
  const ring = Array.from({ length: providers }, (_, i) => {
    const a = (i / providers) * Math.PI * 2 - Math.PI / 2;
    return { x: cx + Math.cos(a) * 34, y: cy + Math.sin(a) * 34 };
  });
  const shown = Math.min(members, 28);
  const dots = Array.from({ length: shown }, (_, i) => {
    const a = (i / shown) * Math.PI * 2;
    const r = 52 + (i % 3) * 5;
    return { x: cx + Math.cos(a) * r * 1.7, y: cy + Math.sin(a) * r * 0.95, to: ring[i % providers] };
  });
  return (
    <svg viewBox="0 0 220 124" className="h-32 w-full max-w-xs" role="img" aria-label={`Diagram of ${providers} providers in a referral loop connected to ${members} members`}>
      {dots.map((d, i) => (
        <line key={`l${i}`} x1={d.x} y1={d.y} x2={d.to.x} y2={d.to.y} stroke="#94A3B8" strokeOpacity="0.5" strokeWidth="0.6" />
      ))}
      {ring.map((p, i) => {
        const n = ring[(i + 1) % ring.length];
        return <line key={`r${i}`} x1={p.x} y1={p.y} x2={n.x} y2={n.y} stroke="#334155" strokeWidth="1.6" />;
      })}
      {dots.map((d, i) => (
        <circle key={`d${i}`} cx={d.x} cy={d.y} r="2.2" fill="#047857" />
      ))}
      {ring.map((p, i) => (
        <circle key={`p${i}`} cx={p.x} cy={p.y} r="5" fill="#DC2626" stroke="#fff" strokeWidth="1" />
      ))}
    </svg>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-5">
      <h3 className="border-b pb-1 text-sm font-semibold">{title}</h3>
      <div className="mt-2 text-sm">{children}</div>
    </section>
  );
}

export function BriefViewer({ caseId }: { caseId: string }) {
  const [type, setType] = useState<"technical" | "plain">("technical");
  const { data, isLoading, error, refetch } = useBrief(caseId, type);
  const canExport = useAuthStore((s) => s.can("export"));
  const [status, setStatus] = useState("");
  const [exporting, setExporting] = useState(false);

  const copy = async () => {
    if (!data) return;
    try {
      await navigator.clipboard.writeText(briefText(data));
      setStatus("Brief copied to clipboard.");
    } catch {
      setStatus("Copy failed. Your browser blocked clipboard access.");
    }
  };

  const exportPdf = async () => {
    if (!data) return;
    setExporting(true);
    setStatus("");
    try {
      const { downloadBriefPdf } = await import("./brief-pdf");
      await downloadBriefPdf(data);
      logAudit(`Exported brief as PDF (${type})`, caseId);
      setStatus("PDF downloaded.");
    } catch (e) {
      setStatus(`PDF export failed: ${e instanceof Error ? e.message : "unknown error"}`);
    } finally {
      setExporting(false);
    }
  };

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div role="radiogroup" aria-label="Brief version" className="inline-flex overflow-hidden rounded-md border">
          {(["technical", "plain"] as const).map((t) => (
            <button
              key={t}
              role="radio"
              aria-checked={type === t}
              onClick={() => setType(t)}
              className={cn("px-3 py-1.5 text-sm font-medium hover:bg-accent", type === t && "bg-primary text-primary-foreground hover:bg-primary")}
            >
              {t === "technical" ? "Technical" : "Plain language"}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={exportPdf} disabled={!data || !canExport || exporting} title={canExport ? undefined : "Your role cannot export"}>
            <FileDown /> {exporting ? "Preparing PDF" : "Export PDF"}
          </Button>
          <Button variant="outline" size="sm" onClick={copy} disabled={!data}>
            <Copy /> Copy
          </Button>
        </div>
      </div>
      <p aria-live="polite" className="mt-2 min-h-5 text-xs text-muted-foreground">
        {status}
      </p>

      {isLoading ? <Loading label="Generating brief" /> : null}
      {error ? <ErrorState error={error} onRetry={() => refetch()} /> : null}
      {data ? (
        <Card className="mx-auto max-w-3xl p-5 sm:p-8">
          <h2 className="text-lg font-semibold">
            Case <span className="id">{data.caseId}</span>
          </h2>
          <dl className="mt-3 grid gap-x-6 gap-y-1 text-sm sm:grid-cols-[11rem_1fr]">
            <dt className="text-muted-foreground">Provider</dt>
            <dd>{data.provider}</dd>
            <dt className="text-muted-foreground">Risk score</dt>
            <dd className="num">{data.riskLine}</dd>
            <dt className="text-muted-foreground">Potential amount (INR)</dt>
            <dd className="num">{inr(data.amount)}</dd>
            <dt className="text-muted-foreground">Members affected</dt>
            <dd className="num">{data.members}</dd>
            <dt className="text-muted-foreground">Member harm score</dt>
            <dd className="num">{data.harmLine}</dd>
          </dl>
          <Section title="Evidence">
            <ol className="list-decimal space-y-1 pl-5">
              {data.evidence.map((e) => (
                <li key={e}>{e}</li>
              ))}
            </ol>
          </Section>
          <Section title="Timeline">
            <ul className="list-disc space-y-1 pl-5">
              {data.timeline.map((t) => (
                <li key={t}>{t}</li>
              ))}
            </ul>
          </Section>
          <Section title="Network context">
            <MiniGraph providers={data.network.providers} members={data.network.members} />
            <p className="mt-1">{data.network.text}</p>
          </Section>
          <Section title="Confidence">
            <p className="num">{score(data.confidence)}</p>
          </Section>
          <Section title="Recommended action">
            <p className="max-w-[70ch]">{data.recommendedAction}</p>
          </Section>
        </Card>
      ) : null}
    </div>
  );
}
