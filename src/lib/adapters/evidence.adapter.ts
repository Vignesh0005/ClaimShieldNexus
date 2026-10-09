import type { EvidenceItem, EvidenceResponse, EvidenceRow, SignalKind } from "@/lib/types";
import { inr } from "@/lib/utils";
import type { BackendEvidence, BackendEvidenceItem } from "./backend-types";

const KINDS = ["rule", "ml", "graph", "temporal"];
const humanize = (key: string) => key.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());

function text(value: unknown): string {
  if (value === null || value === undefined) return "Not available";
  if (Array.isArray(value)) return value.map((v) => (typeof v === "object" ? JSON.stringify(v) : String(v))).join(", ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function rows(item: BackendEvidenceItem): { title: string; rows: EvidenceRow[] } {
  const e = item.evidence ?? {};
  if (item.name === "duplicate_billing" && Array.isArray(e.matching_fields)) {
    return { title: `Fields matching ${text(e.matched_claim_id)}`, rows: (e.matching_fields as string[]).map((f) => ({ label: f, value: `Same as ${text(e.matched_claim_id)}`, match: true })) };
  }
  if (Array.isArray(e.top_features)) {
    const features = e.top_features as { feature: string; shap: number; value: number | null }[];
    return { title: "Features driving the score (SHAP)", rows: features.map((f) => ({ label: f.feature, value: text(f.value), delta: `${f.shap >= 0 ? "+" : ""}${f.shap.toFixed(2)}` })) };
  }
  if (Array.isArray(e.loop_members)) {
    const loop = e.loop_members as string[];
    return {
      title: "Loop summary",
      rows: [
        { label: "Loop", value: [...loop, loop[0]].join(" > ") },
        { label: "Referrals in loop", value: text(e.referrals_in_loop) },
        { label: "Total claims in loop", value: text(e.total_claims_in_loop) },
        { label: "Total amount (INR)", value: typeof e.total_dollars === "number" ? inr(e.total_dollars) : "Not available" },
        { label: "Members affected", value: text(e.members_affected) },
        ...(e.common_owner ? [{ label: "Common owner", value: text(e.common_owner) }] : []),
      ],
    };
  }
  return { title: "Recorded evidence", rows: Object.entries(e).filter(([k]) => k !== "model").map(([k, v]) => ({ label: humanize(k), value: text(v) })) };
}

export function adaptEvidenceItem(item: BackendEvidenceItem, caseId: string, modelWarning?: string | null): EvidenceItem {
  const { title, rows: r } = rows(item);
  const isModel = item.detector === "ml";
  const source = [`Claim ${item.source.claim_id}`, item.source.fields.length ? `fields ${item.source.fields.join(", ")}` : "", item.occurrences > 1 ? `seen on ${item.occurrences} claims in this case` : ""].filter(Boolean).join("; ");
  return {
    id: `${item.signal_id}-${item.name}`,
    kind: item.detector as SignalKind,
    title: item.title,
    scoreLabel: item.score_label === "confidence" ? "Confidence" : "Score",
    score: item.score,
    summary: item.summary,
    rowsTitle: title,
    rows: r,
    source: isModel && modelWarning ? `${source}. ${modelWarning}` : source,
    link: isModel ? { label: "View model card", href: "/models" } : item.detector === "graph" ? { label: "View network graph", href: `/cases/${caseId}?tab=network` } : undefined,
  };
}

export function adaptEvidence(b: BackendEvidence): EvidenceResponse {
  return {
    items: b.items.filter((i) => KINDS.includes(i.detector)).map((i) => adaptEvidenceItem(i, b.case_id, b.model_warning)),
    limitations: b.limitations,
  };
}
