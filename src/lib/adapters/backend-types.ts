// Shapes returned by the FastAPI backend (snake_case), limited to the fields the UI reads.

export interface BackendLine {
  line_id: string;
  cpt_code: string | null;
  units: number | null;
  billed_amount: number | null;
  paid_amount?: number | null;
}

export interface BackendClaim {
  claim_id: string;
  member_id: string | null;
  provider_id: string | null;
  facility_id?: string | null;
  service_date: string | null;
  claim_type?: string | null;
  total_billed: number | null;
  coverage_status: string | null;
  risk_score: number | null;
  severity: string | null;
  two_axis_quadrant?: string | null;
  status: string;
  processed_at?: string | null;
  model_version?: string | null;
  model_warning?: string | null;
  lines?: BackendLine[];
}

export interface BackendCaseSummary {
  case_id: string;
  provider_id: string | null;
  provider_name: string | null;
  specialty: string | null;
  risk_score: number | null;
  suspicion_score: number | null;
  severity: string | null;
  member_harm_score: number | null;
  evidence_strength: number | null;
  expected_recovery: number | null;
  estimated_hours: number | null;
  claim_count: number;
  members_affected: number;
  status: string;
  assigned_to: string | null;
  primary_flag: string | null;
  opened_reason?: string | null;
  created_at: string;
  rank?: number;
  in_capacity?: boolean;
}

export interface BackendFlag {
  signal_id: string;
  detector: string;
  name: string;
  label: string;
  score: number;
  claim_id: string;
  occurrences: number;
}

export interface BackendSimilarCase {
  claim_id: string;
  case_id: string | null;
  similarity: number;
  case_status: string | null;
  primary_flag: string | null;
  provider_id: string | null;
}

export interface BackendCaseDetail extends BackendCaseSummary {
  provider: { provider_id: string | null; name: string | null; specialty: string | null; on_provider_file: boolean };
  signal_breakdown: Record<string, number>;
  flags: BackendFlag[];
  member_harm_factors: string[];
  model_version: string | null;
  model_warning?: string | null;
  similar_cases?: BackendSimilarCase[];
  primary_claim: { claim_id: string; service_date: string | null; total_billed: number | null; lines: BackendLine[] } | null;
}

export interface BackendEvidenceItem {
  signal_id: string;
  detector: string;
  name: string;
  title: string;
  summary: string;
  score_label: string;
  score: number;
  severity: string | null;
  evidence: Record<string, unknown>;
  source: { claim_id: string; fields: string[] };
  occurrences: number;
}

export interface BackendEvidence {
  case_id: string;
  items: BackendEvidenceItem[];
  limitations: string[];
  model_warning?: string | null;
}

export interface BackendQueue {
  capacity: { capacity: number; total_hours: number; total_selected: number; total_expected_recovery: number; total_harm_reduction: number };
  cases: BackendCaseSummary[];
  total: number;
}

export interface BackendOptimize {
  selected_cases: { case_id: string }[];
  total_selected: number;
  total_hours: number;
  capacity: number;
  total_expected_recovery: number;
  total_harm_reduction: number;
  optimization_method: string;
}

export interface BackendFunnel {
  stages: { key: string; label: string; value: number }[];
  reduction_pct: number;
  alerts_by_severity: Record<string, number>;
  dollars_at_risk: number;
}

export interface BackendPeriod {
  claims: number;
  alerts: number;
  routed_claims: number;
  routed_dollars: number;
}

export interface BackendAuditEvent {
  id: string;
  timestamp: string;
  actor: string | null;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  details: Record<string, unknown> | null;
}

export interface BackendDashboard {
  funnel: BackendFunnel;
  periods: { current?: BackendPeriod; previous?: BackendPeriod };
  top_providers: { provider_id: string; expected_recovery: number; severity: string; case_id: string }[];
  activity: { id: string; action: string; actor: string | null; resource_id: string | null; details: Record<string, unknown> | null; timestamp: string }[];
}

export interface BackendInject {
  claim_id: string;
  scheme: string;
  caught: boolean;
  latency_ms: number;
  caught_by: string[];
  flags: { detector: string; rule_name?: string; model?: string; pattern?: string; confidence?: number; score?: number }[];
  case_id: string | null;
}
