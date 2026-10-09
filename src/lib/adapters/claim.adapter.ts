import type { ClaimRow, RiskLevel } from "@/lib/types";
import type { BackendClaim } from "./backend-types";

const LEVELS: RiskLevel[] = ["critical", "high", "medium", "low"];

export function adaptLevel(severity: string | null | undefined, score?: number | null): RiskLevel {
  if (severity && (LEVELS as string[]).includes(severity)) return severity as RiskLevel;
  const s = score ?? 0;
  return s >= 0.8 ? "critical" : s >= 0.6 ? "high" : s >= 0.4 ? "medium" : "low";
}

export function adaptClaim(b: BackendClaim): ClaimRow {
  return {
    id: b.claim_id,
    memberId: b.member_id ?? "",
    providerId: b.provider_id ?? "",
    serviceDate: b.service_date ?? "",
    billed: b.total_billed ?? 0,
    status: b.status === "processed" || b.status === "failed" ? b.status : "processing",
    coverageStatus: b.coverage_status,
    // A claim held for coverage review has no fraud score at all; keep that distinct from a low score.
    risk: b.risk_score,
    level: b.risk_score === null ? null : adaptLevel(b.severity, b.risk_score),
  };
}

/** A minimal, valid claim in the backend's ingest format. */
export function buildTestClaim(claimId: string, overrides: Record<string, unknown> = {}): Record<string, unknown> {
  const today = new Date().toISOString().slice(0, 10);
  return {
    claim_id: claimId,
    member_id: "MBR-1000",
    provider_id: "PRV-2000",
    service_date: today,
    claim_type: "professional",
    total_billed: 120,
    diagnosis_codes: ["M54.5"],
    plan_type: "family_floater",
    policy_start_date: "2021-01-01",
    service_location: "IN",
    lines: [{ line_id: `${claimId}-L1`, cpt_code: "99213", units: 1, billed_amount: 120, paid_amount: 110, diagnosis_pointer: [1] }],
    ...overrides,
  };
}
