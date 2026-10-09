import type { CaseDetail, CaseStatus, CaseSummary, Decision, Flag, LineDecision, SignalKind } from "@/lib/types";
import { harmLevel } from "@/lib/utils";
import type { BackendCaseDetail, BackendCaseSummary } from "./backend-types";
import { adaptLevel } from "./claim.adapter";

// The UI refers to reviewers by display name; the backend by staff ID. These are the demo
// tenant's seeded users. An unknown ID is shown as-is rather than hidden.
const DIRECTORY: Record<string, string> = {
  "AUD-007": "A. Sharma",
  "AUD-011": "J. Okafor",
  "AUD-004": "L. Chen",
  "ADM-002": "R. Alvarez",
  "ANL-014": "M. Petrov",
  "VWR-021": "S. Doyle",
};

export const assigneeName = (id: string | null | undefined) => (id ? (DIRECTORY[id] ?? id) : "Unassigned");
export const assigneeId = (name: string) => Object.entries(DIRECTORY).find(([, n]) => n === name)?.[0] ?? name;

const STATUSES: CaseStatus[] = ["pending_review", "in_review", "needs_info", "confirmed", "false_positive", "escalated"];
const KINDS: SignalKind[] = ["rule", "ml", "graph", "temporal"];

export const flagLabel = (name: string | null | undefined) => (name ? name.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase()) : "Unclassified");

export function adaptCaseSummary(b: BackendCaseSummary): CaseSummary {
  const risk = b.risk_score ?? 0;
  const harm = b.member_harm_score ?? 0;
  return {
    id: b.case_id,
    providerId: b.provider_id ?? "Unknown",
    providerName: b.provider_name ?? "Provider",
    specialty: b.specialty ?? "Not on provider file",
    risk,
    level: adaptLevel(b.severity, risk),
    amount: b.expected_recovery ?? 0,
    members: b.members_affected,
    harm,
    harmLevel: harmLevel(harm),
    evidence: b.evidence_strength ?? 0,
    status: (STATUSES as string[]).includes(b.status) ? (b.status as CaseStatus) : "pending_review",
    assignee: assigneeName(b.assigned_to),
    rule: flagLabel(b.primary_flag),
    hours: b.estimated_hours ?? 0,
    openedAt: b.created_at,
  };
}

export function adaptCaseDetail(b: BackendCaseDetail, others: BackendCaseSummary[] = []): CaseDetail {
  const flags: Flag[] = b.flags
    .filter((f) => (KINDS as string[]).includes(f.detector))
    .map((f) => ({ id: `${f.signal_id}-${f.name}`, kind: f.detector as SignalKind, name: f.label, score: f.score }));
  return {
    ...adaptCaseSummary(b),
    signals: {
      rule: b.signal_breakdown.rule ?? 0,
      ml: b.signal_breakdown.ml ?? 0,
      graph: b.signal_breakdown.graph ?? 0,
      temporal: b.signal_breakdown.temporal ?? 0,
    },
    flags,
    harmFactors: b.member_harm_factors,
    lines: (b.primary_claim?.lines ?? []).map((l) => ({
      id: l.line_id,
      code: l.cpt_code ?? "",
      description: `${l.units ?? 1} unit${(l.units ?? 1) === 1 ? "" : "s"} on claim ${b.primary_claim!.claim_id}`,
      amount: l.billed_amount ?? 0,
    })),
    // Other cases in this tenant, for the suspicion-against-evidence comparison.
    peers: others.filter((o) => o.case_id !== b.case_id).map((o) => ({ id: o.case_id, suspicion: o.suspicion_score ?? o.risk_score ?? 0, evidence: o.evidence_strength ?? 0 })),
    similarCases: (b.similar_cases ?? []).map((s) => ({ claimId: s.claim_id, caseId: s.case_id, similarity: s.similarity, status: s.case_status, flag: flagLabel(s.primary_flag), providerId: s.provider_id })),
    modelWarning: b.model_warning ?? null,
    openedReason: b.opened_reason ?? null,
  };
}

const DECISION: Record<Decision, string> = { CONFIRM_FWA: "confirm_fraud", NEEDS_INFO: "needs_info", FALSE_POSITIVE: "false_positive", REASSIGN: "reassign" };

/** UI decision form -> backend POST /cases/{id}/decision body. */
export function adaptDecisionRequest(input: { decision: Decision; lines: Record<string, LineDecision>; notes: string; nextAction: string; assignee?: string }) {
  const action = input.nextAction.toLowerCase();
  return {
    decision: DECISION[input.decision],
    notes: input.notes,
    line_decisions: Object.entries(input.lines).map(([line_id, decision]) => ({ line_id, decision })),
    next_action: action.includes("tier 2") ? "escalate_tier2" : action.replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "").slice(0, 100),
    assignee: input.assignee ? assigneeId(input.assignee) : undefined,
  };
}
