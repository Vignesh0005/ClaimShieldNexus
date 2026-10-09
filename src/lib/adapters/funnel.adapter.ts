import type { AuditEvent, FunnelData, Metric } from "@/lib/types";
import { inrCompact } from "@/lib/utils";
import type { BackendAuditEvent, BackendDashboard, BackendFunnel } from "./backend-types";
import { adaptLevel } from "./claim.adapter";

const ACTION_TEXT: Record<string, string> = {
  "case.created": "Case opened for review",
  "case.viewed": "Opened case",
  "case.evidence_viewed": "Viewed evidence",
  "case.network_viewed": "Viewed network graph",
  "case.assigned": "Assigned case",
  "case.status_changed": "Changed status",
  "case.decision": "Decision recorded",
  "case.line_decision": "Line decision recorded",
  "brief.generated": "Generated brief",
  "brief.enhanced": "Generated LLM-enhanced brief",
  "brief.exported": "Exported brief",
  "copilot.investigate": "Asked the copilot to explain the case",
  "copilot.ask": "Asked the copilot a question",
  "feedback.submitted": "Submitted feedback",
  "claim.ingested": "Claim ingested",
  "claim.reprocess_requested": "Requested reprocessing",
  "detection.run": "Ran detection",
  "demo.scheme_injected": "Injected a test scheme",
  "model.retrained": "Candidate model trained",
  "model.deployed": "Model deployed",
  "tenant.config_updated": "Changed tenant configuration",
  "tenant.field_mapping_updated": "Updated field mapping",
  "tenant.api_key_rotated": "Generated a new API key",
  "audit.exported": "Exported the audit log",
  "client.export.queue_csv": "Exported queue as CSV",
  "client.export.brief_pdf": "Downloaded brief as PDF",
  "client.print.briefs": "Printed briefs",
  "client.overlay.sent_to_siu": "Sent to SIU queue from overlay",
};

function detailText(details: Record<string, unknown> | null): string | undefined {
  if (!details) return undefined;
  const parts = Object.entries(details)
    .filter(([k, v]) => !["request_id", "ms", "client_reported"].includes(k) && v !== null && v !== "" && typeof v !== "object")
    .map(([k, v]) => `${k.replace(/_/g, " ")}: ${v}`);
  return parts.length ? parts.join(", ") : undefined;
}

export function describeAction(action: string): string {
  return ACTION_TEXT[action] ?? action.replace(/^http\./, "API request ").replace(/[._]/g, " ");
}

export function adaptAuditEvent(e: BackendAuditEvent): AuditEvent {
  return {
    id: e.id,
    ts: e.timestamp,
    actor: e.actor ?? "system",
    action: describeAction(e.action),
    caseId: e.resource_type === "case" ? (e.resource_id ?? undefined) : undefined,
    detail: e.resource_type === "endpoint" ? `${e.resource_id} (${detailText(e.details) ?? ""})` : detailText(e.details),
  };
}

export function adaptFunnel(b: BackendFunnel) {
  return { stages: b.stages, reduction: b.reduction_pct };
}

function change(current: number, previous: number, money = false): Pick<Metric, "delta" | "direction"> {
  const diff = current - previous;
  const direction = diff >= 0 ? "up" : "down";
  if (previous === 0) return { delta: current === 0 ? "No change" : "New", direction };
  const pct = Math.round((diff / previous) * 100);
  return { delta: money ? `${diff >= 0 ? "+" : "-"}${inrCompact(Math.abs(diff))}` : `${pct >= 0 ? "+" : ""}${pct}%`, direction };
}

/** GET /dashboard -> the overview screen. Every number is a count the backend computed. */
export function adaptDashboard(b: BackendDashboard): FunnelData {
  const cur = b.periods.current ?? { claims: 0, alerts: 0, routed_claims: 0, routed_dollars: 0 };
  const prev = b.periods.previous ?? { claims: 0, alerts: 0, routed_claims: 0, routed_dollars: 0 };
  const sev = b.funnel.alerts_by_severity;
  return {
    ...adaptFunnel(b.funnel),
    metrics: [
      { key: "claims", label: "Claims, last 30 days", display: cur.claims.toLocaleString("en-IN"), ...change(cur.claims, prev.claims) },
      { key: "alerts", label: "Alerts, last 30 days", display: cur.alerts.toLocaleString("en-IN"), ...change(cur.alerts, prev.alerts) },
      { key: "cases", label: "Claims routed to cases, last 30 days", display: cur.routed_claims.toLocaleString("en-IN"), ...change(cur.routed_claims, prev.routed_claims) },
      { key: "risk", label: "Amount routed (INR), last 30 days", display: inrCompact(cur.routed_dollars), ...change(cur.routed_dollars, prev.routed_dollars, true) },
    ],
    riskDistribution: (["critical", "high", "medium", "low"] as const).map((level) => ({ level, count: sev[level] ?? 0 })),
    topProviders: b.top_providers.map((p) => ({ id: p.provider_id, amount: p.expected_recovery, level: adaptLevel(p.severity), caseId: p.case_id })),
    activity: b.activity.map((a) => ({ id: a.id, text: `${a.actor ?? "system"}: ${describeAction(a.action).toLowerCase()}${a.resource_id ? ` (${a.resource_id})` : ""}`, ts: a.timestamp })),
  };
}
