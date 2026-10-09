// Adapters for the remaining screens. Where the backend does not measure something the UI was
// designed to show, the value is passed through as null and the screen says "not yet measured".
import type {
  AnalyticsData,
  ComplianceReport,
  CoverageRules,
  Brief,
  Counterfactual,
  FeedbackEntry,
  GeoEvent,
  HealthData,
  InjectResult,
  LogEntry,
  ModelCard,
  NetworkData,
  OverlayInfo,
  SignalKind,
  Tenant,
  TimelineEvent,
} from "@/lib/types";
import type { BackendCaseDetail, BackendInject } from "./backend-types";
import { flagLabel } from "./case.adapter";
import { adaptLevel } from "./claim.adapter";
import { score } from "@/lib/utils";

type Json = any;

const month = (iso: string | null | undefined, fallback: string) => (iso ? iso.slice(0, 7) : fallback);
const cap = (s: string) => s.replace(/^./, (c) => c.toUpperCase());

export function adaptNetwork(b: Json): NetworkData {
  const now = new Date().toISOString().slice(0, 7);
  const from = month(b.range?.from, now);
  const to = month(b.range?.to, now);
  return {
    centerId: b.center_id ?? undefined,
    nodes: (b.nodes as Json[]).map((n) => ({
      id: n.id,
      label: n.type === "member" ? String(n.id).slice(0, 10) : n.label,
      type: n.type,
      inLoop: !!n.in_loop,
      claims: n.claims ?? 0,
      amount: n.amount ?? 0,
      firstSeen: month(n.first_seen, from),
    })),
    edges: (b.edges as Json[]).map((e) => ({ id: e.id, source: e.source, target: e.target, type: e.type === "referral" ? "referral" : "claim", date: month(e.date, from) })),
    range: { from, to },
  };
}

export function adaptTimeline(b: { events: Json[] }): TimelineEvent[] {
  const kinds = ["rule", "ml", "graph", "temporal", "case"];
  return b.events.map((e, i) => ({ id: `t${i}`, date: e.date, title: e.title, detail: e.detail, kind: (kinds.includes(e.kind) ? e.kind : "case") as SignalKind | "case" }));
}

export function adaptBrief(b: Json, type: "technical" | "plain"): Brief {
  const c = b.content;
  const harm = c.member_harm_score ?? 0;
  return {
    caseId: c.case_id,
    type,
    provider: c.provider,
    riskLine: `${score(Number(c.risk_score))} (${cap(c.severity)})`,
    amount: c.potential_dollars,
    members: c.members_affected,
    harmLine: `${score(harm)} (${harm >= 0.7 ? "High" : harm >= 0.5 ? "Medium" : "Low"})`,
    evidence: (c.evidence as Json[]).map((e) =>
      type === "plain" ? e.plain : `${cap(e.detector)}: ${e.label}, ${e.score_label} ${score(Number(e.score))}${e.detail ? `. ${e.detail}` : ""} (source: ${e.source})`,
    ),
    timeline: (c.timeline as Json[]).map((t) => `${t.date}: ${t.title}`),
    network: { providers: c.network.providers, members: c.network.members, text: c.network.text },
    confidence: c.confidence,
    limitations: c.limitations,
    recommendedAction: type === "plain" ? c.recommended_action_plain : c.recommended_action,
    disclaimer: c.disclaimer,
    generatedAt: b.generated_at ?? c.generated_at,
    enhancement: b.enhancement
      ? {
          model: b.enhancement.model,
          fallbackReason: b.enhancement.fallback_reason ?? null,
          narrative: b.enhancement.narrative ?? [],
          counterfactuals: b.enhancement.counterfactuals ?? [],
          plainLanguage: b.enhancement.plain_language ?? [],
          limitations: b.enhancement.limitations ?? [],
        }
      : null,
  };
}

export function adaptCounterfactual(b: Json): Counterfactual {
  return {
    baseline: b.baseline_risk,
    threshold: b.routing_threshold,
    scenarios: (b.scenarios as Json[]).map((s, i) => ({
      id: `cf${i}`,
      label: s.scenario,
      description: s.removes === "all" ? "Re-scored with every finding removed." : `Re-scored with the "${s.label}" finding removed and everything else unchanged.`,
      newRisk: s.counterfactual_risk,
      wouldRoute: s.would_still_route,
    })),
  };
}

// The UI asks "was this case worth reviewing?". The backend stores reviewer labels for training.
// "Not useful" maps to a false-positive label. "Useful" is NOT a confirmation, so it is stored
// without a training label rather than inventing one.
export function adaptFeedbackRequest(input: { caseId: string; useful: boolean; reasons: string[]; comment: string }) {
  return {
    case_id: input.caseId,
    decision: input.useful ? "needs_info" : "false_positive",
    notes: JSON.stringify({ useful: input.useful, reasons: input.reasons, comment: input.comment }),
  };
}

export function adaptFeedback(f: Json): FeedbackEntry {
  let parsed: { useful?: boolean; reasons?: string[]; comment?: string } = {};
  try {
    parsed = JSON.parse(f.notes ?? "{}");
  } catch {
    parsed = { comment: f.notes ?? "" };
  }
  return {
    id: f.feedback_id,
    caseId: f.case_id ?? "Unknown case",
    actor: f.reviewer ?? "unknown",
    ts: f.reviewed_at,
    useful: parsed.useful ?? f.decision !== "false_positive",
    reasons: parsed.reasons ?? [],
    comment: parsed.comment ?? "",
  };
}

export function adaptTenant(t: Json, counts?: { claims: number; cases: number }): Tenant {
  return {
    id: t.slug,
    name: t.name,
    plan: t.is_demo ? "Demo" : "Standard",
    region: "Not recorded",
    claimsPerMonth: counts ? counts.claims : null,
    users: null,
    status: t.active ? "active" : "suspended",
    createdAt: String(t.created_at).slice(0, 10),
  };
}

export function adaptModelCard(card: Json, versions: Json[]): ModelCard {
  const split = card.evaluation?.provider_split ?? null;
  const random = card.evaluation?.random_split ?? { precision: card.precision, recall: card.recall, f1: card.f1, roc_auc: card.roc_auc, pr_auc: card.pr_auc };
  const metric = (label: string, key: string) => ({ label, random: random?.[key] ?? null, providerSplit: split?.[key] ?? null });
  return {
    name: card.model_type ?? "model",
    version: card.version,
    type: card.explainability ?? "",
    trainedAt: String(card.trained_at ?? "").slice(0, 10),
    intendedUse: card.intended_use,
    outOfScope: card.out_of_scope ?? [],
    trainingData: card.training_data,
    trainingSamples: card.training_samples ?? null,
    syntheticWarning: card.warning ?? null,
    evaluation: [metric("F1", "f1"), metric("Precision", "precision"), metric("Recall", "recall"), metric("ROC AUC", "roc_auc"), metric("PR AUC", "pr_auc")],
    evaluationNote: card.evaluation?.note ?? null,
    providerSplitFolds: split?.folds ?? null,
    features: Object.entries((card.feature_importance ?? {}) as Record<string, number>).map(([name, importance]) => ({ name, importance })),
    biasAnalysis: card.bias_analysis ?? [],
    fairness: card.fairness ?? "Not yet measured.",
    limitations: card.limitations ?? [],
    history: versions.map((v) => ({ version: v.version, date: String(v.trained_at ?? "").slice(0, 10), note: `${v.is_deployed ? "Deployed. " : "Candidate, not deployed. "}${v.notes ?? ""}` })),
  };
}

export function adaptHealth(checks: { name: string; ok: boolean; ms: number; note?: string }[], perf: Json | null): HealthData {
  return {
    status: checks.every((c) => c.ok) ? "operational" : "degraded",
    checkedAt: new Date().toISOString(),
    services: checks.map((c) => ({ name: c.name, status: c.ok ? "operational" : "down", latencyMs: c.ms, uptime: null, note: c.note })),
    latency: (perf?.series ?? []).map((s: Json) => ({ t: s.minute, p50: s.p50_ms, p95: s.p95_ms })),
    performance: perf
      ? { samples: perf.samples, p50: perf.latency_ms?.p50 ?? null, p95: perf.latency_ms?.p95 ?? null, p99: perf.latency_ms?.p99 ?? null, perMinute: perf.throughput?.claims_last_minute ?? null, perMinuteAvg5: perf.throughput?.claims_per_minute_5m ?? null, backlog: perf.backlog ?? null, mode: perf.mode, note: perf.note }
      : null,
  };
}

export function adaptGeo(b: { events: Json[] }): GeoEvent[] {
  return b.events.map((e) => ({
    id: e.id,
    subject: e.subject,
    subjectType: "member",
    date: e.date,
    caseId: e.case_id ?? "",
    a: { city: e.a.city, lat: e.a.lat, lng: e.a.lng },
    b: { city: e.b.city, lat: e.b.lat, lng: e.b.lng },
    distanceKm: e.distance_km,
    minutesApart: null,
    level: adaptLevel(e.severity),
  }));
}

export function adaptAnalytics(b: Json): AnalyticsData {
  const flags: string[] = Array.from(new Set((b.heatmap as Json[]).map((h) => h.flag)));
  const specialties: string[] = Array.from(new Set((b.heatmap as Json[]).map((h) => h.specialty)));
  const z = flags.map((f) => specialties.map((s) => (b.heatmap as Json[]).find((h) => h.flag === f && h.specialty === s)?.cases ?? 0));
  return {
    monthly: (b.monthly as Json[]).map((m) => ({ month: m.month, alerts: m.alerts ?? 0, cases: m.cases_opened ?? 0, identified: m.identified ?? 0, recovered: null })),
    bySignal: (b.by_flag as Json[]).map((f) => ({ scheme: flagLabel(f.flag), cases: f.cases, amount: f.amount })),
    precision: [],
    heatmap: { schemes: flags.map(flagLabel), specialties, z },
    workload: (b.workload as Json[]).map((w) => ({ investigator: w.investigator, open: w.open, closed: w.closed, avgHours: w.avg_estimated_hours })),
    totals: { identified: b.dollars_identified, recovered: b.dollars_recovered, avgDaysToDecision: b.decisions.avg_days_to_decision, precision: b.decisions.reviewer_confirmed_rate, decisions: b.decisions.total },
  };
}

export function adaptLogs(b: { logs: Json[] }): LogEntry[] {
  return b.logs.map((l, i) => ({
    id: `log-${i}`,
    ts: l.timestamp ?? new Date().toISOString(),
    level: l.level === "warning" ? "warn" : l.level === "error" || l.level === "critical" ? "error" : "info",
    service: String(l.event ?? "app").split("_")[0],
    tenantId: l.tenant ?? "-",
    message: `${l.event}${Object.keys(l.fields ?? {}).length ? " " + Object.entries(l.fields).map(([k, v]) => `${k}=${v}`).join(" ") : ""}`,
  }));
}

const INJECT_KINDS = ["rule", "ml", "graph", "temporal"];

export function adaptInject(b: BackendInject, scheme: string): InjectResult {
  const flags = b.flags.filter((f) => INJECT_KINDS.includes(f.detector));
  return {
    scheme,
    claimId: b.claim_id,
    caseId: b.case_id,
    latencyMs: b.latency_ms,
    caughtBy: b.caught_by.filter((k) => INJECT_KINDS.includes(k)) as SignalKind[],
    flags: flags.map((f, i) => ({ id: `FLG-${i + 1}`, kind: f.detector as SignalKind, name: f.rule_name ?? f.model ?? f.pattern ?? "signal", score: f.confidence ?? f.score ?? 0 })),
  };
}

export function adaptOverlay(entityId: string, detail: BackendCaseDetail | null): OverlayInfo {
  if (!detail) return { id: entityId, risk: 0, level: "low", reasons: [], caseId: null };
  const risk = detail.risk_score ?? 0;
  return {
    id: entityId,
    risk,
    level: adaptLevel(detail.severity, risk),
    reasons: detail.flags.filter((f) => f.detector !== "ml" && f.detector !== "similarity").slice(0, 3).map((f) => ({ label: f.label, score: f.score })),
    caseId: detail.case_id,
  };
}

export function adaptCoverageRules(b: Json): CoverageRules {
  return {
    rules: (b.rules as Json[]).map((r) => ({
      id: r.rule_id,
      category: r.category,
      name: r.rule_name,
      description: r.description,
      sourceSection: r.source_section,
      sourceDocument: r.source_document,
      authoritative: !!r.authoritative,
      needsReview: !!r.needs_compliance_review,
      disclaimer: r.disclaimer ?? null,
      enabled: !!r.enabled,
    })),
    illustrative: b.illustrative ?? 0,
    notice: b.notice ?? null,
  };
}

export function adaptComplianceReport(b: Json): ComplianceReport {
  return {
    total: b.coverage_rules.total,
    authoritative: b.coverage_rules.authoritative,
    illustrative: b.coverage_rules.illustrative,
    needsReview: b.coverage_rules.needs_compliance_review,
    sourceDocument: b.authoritative_source.document,
    expectedRules: b.authoritative_source.expected_rules,
    loadedRules: b.authoritative_source.loaded_rules,
    sourceStatus: b.authoritative_source.status,
    sourceNote: b.authoritative_source.note ?? null,
    referenceData: (b.reference_data as Json[]).map((d) => ({ name: d.name, entries: d.entries, usedBy: d.used_by, authoritative: !!d.authoritative, disclaimer: d.disclaimer, productionSource: d.production_source })),
    notice: b.notice ?? null,
  };
}
