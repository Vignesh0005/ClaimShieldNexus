export type RiskLevel = "critical" | "high" | "medium" | "low";
export type HarmLevel = "High" | "Med" | "Low";
export type Role = "admin" | "investigator" | "analyst" | "viewer";
export type SignalKind = "rule" | "ml" | "graph" | "temporal";
export type CaseStatus =
  | "pending_review"
  | "in_review"
  | "needs_info"
  | "confirmed"
  | "false_positive"
  | "escalated";
export type Decision = "CONFIRM_FWA" | "NEEDS_INFO" | "FALSE_POSITIVE" | "REASSIGN";
export type LineDecision = "confirm" | "dismiss" | "review";

export interface Tenant {
  id: string;
  name: string;
  plan: string;
  region: string;
  claimsPerMonth: number | null;
  users: number | null;
  status: "active" | "onboarding" | "suspended";
  createdAt: string;
}

export interface Flag {
  id: string;
  kind: SignalKind;
  name: string;
  score: number;
}

export interface ClaimLine {
  id: string;
  code: string;
  description: string;
  amount: number;
}

export interface CaseSummary {
  id: string;
  providerId: string;
  providerName: string;
  specialty: string;
  risk: number;
  level: RiskLevel;
  amount: number;
  members: number;
  harm: number;
  harmLevel: HarmLevel;
  evidence: number;
  status: CaseStatus;
  assignee: string;
  rule: string;
  hours: number;
  openedAt: string;
}

export interface CaseDetail extends CaseSummary {
  signals: Record<SignalKind, number>;
  flags: Flag[];
  harmFactors: string[];
  lines: ClaimLine[];
  peers: { id: string; suspicion: number; evidence: number }[];
  similarCases?: SimilarCase[];
  modelWarning?: string | null;
  openedReason?: string | null;
}

export interface SimilarCase {
  claimId: string;
  caseId: string | null;
  similarity: number;
  status: string | null;
  flag: string;
  providerId: string | null;
}

export interface ClaimRow {
  id: string;
  memberId: string;
  providerId: string;
  serviceDate: string;
  billed: number;
  status: "processing" | "processed" | "failed";
  coverageStatus: string | null;
  risk: number | null;
  level: RiskLevel | null;
}

export interface CitedLine {
  text: string;
  sources: string[];
}

export interface BriefEnhancement {
  model: string;
  fallbackReason?: string | null;
  narrative: CitedLine[];
  counterfactuals: CitedLine[];
  plainLanguage: CitedLine[];
  limitations: string[];
}

export interface EvidenceRow {
  label: string;
  value: string;
  delta?: string;
  match?: boolean;
}

export interface EvidenceItem {
  id: string;
  kind: SignalKind;
  title: string;
  scoreLabel: "Confidence" | "Score";
  score: number;
  summary: string;
  rowsTitle: string;
  rows: EvidenceRow[];
  facts?: EvidenceRow[];
  source?: string;
  link?: { label: string; href: string };
}

export interface EvidenceResponse {
  items: EvidenceItem[];
  limitations: string[];
}

export type NodeType = "provider" | "member" | "facility";

export interface GraphNode {
  id: string;
  label: string;
  type: NodeType;
  inLoop?: boolean;
  name?: string;
  specialty?: string;
  claims: number;
  amount: number;
  risk?: number;
  sharedAddresses?: number;
  priorInvestigations?: number;
  firstSeen: string;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  type: "referral" | "claim";
  date: string;
}

export interface NetworkData {
  centerId?: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  range: { from: string; to: string };
}

export interface TimelineEvent {
  id: string;
  date: string;
  title: string;
  detail: string;
  kind: SignalKind | "case";
}

export interface Brief {
  caseId: string;
  type: "technical" | "plain";
  provider: string;
  riskLine: string;
  amount: number;
  members: number;
  harmLine: string;
  evidence: string[];
  timeline: string[];
  network: { providers: number; members: number; text: string };
  confidence: number;
  limitations: string[];
  recommendedAction: string;
  disclaimer: string;
  generatedAt: string;
  enhancement?: BriefEnhancement | null;
}

export interface Counterfactual {
  baseline: number;
  threshold: number;
  scenarios: {
    id: string;
    label: string;
    description: string;
    newRisk: number;
    wouldRoute: boolean;
  }[];
}

export interface AuditEvent {
  id: string;
  ts: string;
  actor: string;
  action: string;
  caseId?: string;
  detail?: string;
}

export interface Metric {
  key: string;
  label: string;
  display: string;
  delta: string;
  direction: "up" | "down";
}

export interface FunnelData {
  stages: { key: string; label: string; value: number }[];
  reduction: number;
  metrics: Metric[];
  riskDistribution: { level: RiskLevel; count: number }[];
  topProviders: { id: string; amount: number; level: RiskLevel; caseId: string }[];
  activity: { id: string; text: string; ts: string }[];
}

export interface QueueData {
  capacityHours: number;
  usedHours: number;
  selected: string[];
  total: number;
  expectedRecovery: number;
  harmReduction: number;
  cases: CaseSummary[];
}

export interface InjectResult {
  scheme: string;
  claimId: string;
  caseId: string | null;
  latencyMs: number;
  caughtBy: SignalKind[];
  flags: Flag[];
}

export interface GeoEvent {
  id: string;
  subject: string;
  subjectType: "provider" | "member";
  date: string;
  caseId: string;
  a: { city: string; lat: number; lng: number; time?: string };
  b: { city: string; lat: number; lng: number; time?: string };
  distanceKm: number;
  minutesApart: number | null;
  level: RiskLevel;
}

export interface AnalyticsData {
  monthly: { month: string; alerts: number; cases: number; identified: number; recovered: number | null }[];
  bySignal: { scheme: string; cases: number; amount: number }[];
  precision: { month: string; precision: number; falsePositive: number }[];
  heatmap: { schemes: string[]; specialties: string[]; z: number[][] };
  workload: { investigator: string; open: number; closed: number; avgHours: number | null }[];
  totals: { identified: number; recovered: number | null; avgDaysToDecision: number | null; precision: number | null; decisions?: number };
}

export interface ModelCard {
  name: string;
  version: string;
  type: string;
  trainedAt: string;
  intendedUse: string;
  outOfScope: string[];
  trainingData: string;
  features: { name: string; importance: number }[];
  limitations: string[];
  history: { version: string; date: string; note: string }[];
  // Mock API only.
  metrics?: { label: string; value: number; note: string }[];
  bias?: { group: string; category: string; flagRate: number; falsePositiveRate: number; ratio: number; status: "pass" | "review" }[];
  drift?: { month: string; psi: number }[];
  // Real backend.
  trainingSamples?: number | null;
  syntheticWarning?: string | null;
  evaluation?: { label: string; random: number | null; providerSplit: number | null }[];
  evaluationNote?: string | null;
  providerSplitFolds?: number | null;
  biasAnalysis?: string[];
  fairness?: string;
}

export interface HealthData {
  status: "operational" | "degraded";
  checkedAt: string;
  services: { name: string; status: "operational" | "degraded" | "down"; latencyMs: number; uptime: number | null; note?: string }[];
  latency: { t: string; p50: number; p95: number }[];
  ingest?: { perMinute: number; backlog: number; lastEventAt: string };
  performance?: { samples: number; p50: number | null; p95: number | null; p99: number | null; perMinute: number | null; perMinuteAvg5: number | null; backlog: number | null; mode: string; note: string } | null;
}

export interface LogEntry {
  id: string;
  ts: string;
  level: "info" | "warn" | "error";
  service: string;
  tenantId: string;
  message: string;
}

export interface FeedbackEntry {
  id: string;
  caseId: string;
  actor: string;
  ts: string;
  useful: boolean;
  reasons: string[];
  comment: string;
}

export interface OverlayInfo {
  id: string;
  risk: number;
  level: RiskLevel;
  reasons: { label: string; score: number }[];
  caseId: string | null;
}

export interface CoverageRuleRow {
  id: string;
  category: string;
  name: string;
  description: string;
  sourceSection: string;
  sourceDocument: string;
  authoritative: boolean;
  needsReview: boolean;
  disclaimer: string | null;
  enabled: boolean;
}

export interface CoverageRules {
  rules: CoverageRuleRow[];
  illustrative: number;
  notice: string | null;
}

export interface ComplianceReport {
  total: number;
  authoritative: number;
  illustrative: number;
  needsReview: number;
  sourceDocument: string;
  expectedRules: number;
  loadedRules: number;
  sourceStatus: string;
  sourceNote: string | null;
  referenceData: { name: string; entries: number; usedBy: string; authoritative: boolean; disclaimer: string; productionSource: string }[];
  notice: string | null;
}
