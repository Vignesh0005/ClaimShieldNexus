import type { HarmLevel, RiskLevel, SignalKind } from "@/lib/types";
import { cn, RISK_LABEL, riskLevel, score as percent } from "@/lib/utils";

// Text colours are darker (light mode) or lighter (dark mode) than the brand risk hues so they
// meet 4.5:1 contrast; the dot carries the exact brand colour. Level is always written out.
const TONE: Record<RiskLevel, string> = {
  critical: "border-red-600/40 bg-red-600/10 text-red-800 dark:text-red-200",
  high: "border-orange-600/40 bg-orange-600/10 text-orange-800 dark:text-orange-200",
  medium: "border-amber-500/50 bg-amber-500/10 text-amber-900 dark:text-amber-200",
  low: "border-emerald-500/40 bg-emerald-500/10 text-emerald-800 dark:text-emerald-200",
};

const DOT: Record<RiskLevel, string> = {
  critical: "bg-risk-critical",
  high: "bg-risk-high",
  medium: "bg-risk-medium",
  low: "bg-risk-low",
};

export function RiskBadge({ level, score, className, label }: { level?: RiskLevel; score?: number; className?: string; label?: string }) {
  const l = level ?? riskLevel(score ?? 0);
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-sm border px-1.5 py-0.5 text-xs font-medium", TONE[l], className)}>
      <span className={cn("size-2 rounded-full", DOT[l])} aria-hidden />
      {score !== undefined ? <span className="num">{percent(score)}</span> : null}
      <span>{label ?? RISK_LABEL[l]}</span>
    </span>
  );
}

const HARM_TO_RISK: Record<HarmLevel, RiskLevel> = { High: "critical", Med: "medium", Low: "low" };

export function HarmBadge({ level, score }: { level: HarmLevel; score: number }) {
  return <RiskBadge level={HARM_TO_RISK[level]} score={score} label={level === "Med" ? "Medium" : level} />;
}

const KIND_LABEL: Record<SignalKind | "case", string> = { rule: "Rule", ml: "ML", graph: "Graph", temporal: "Temporal", case: "Case" };

export function SignalTag({ kind }: { kind: SignalKind | "case" }) {
  return (
    <span className="inline-flex rounded-sm border border-evidence/40 bg-evidence/10 px-1.5 py-0.5 text-xs font-medium text-primary">
      {KIND_LABEL[kind]}
    </span>
  );
}

export function StatusPill({ children, tone = "neutral" }: { children: React.ReactNode; tone?: "neutral" | "good" | "warn" }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-sm border px-1.5 py-0.5 text-xs font-medium",
        tone === "neutral" && "bg-muted text-foreground",
        tone === "good" && "border-emerald-500/40 bg-emerald-500/10 text-emerald-800 dark:text-emerald-200",
        tone === "warn" && "border-amber-500/50 bg-amber-500/10 text-amber-900 dark:text-amber-200",
      )}
    >
      {children}
    </span>
  );
}
