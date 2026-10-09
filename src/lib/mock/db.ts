// In-memory mock backend that implements the /api/v1 contract with synthetic data.
// Everything here is generated; no real providers, members or claims are represented.
import type {
  AnalyticsData,
  AuditEvent,
  Brief,
  CaseDetail,
  CaseStatus,
  CaseSummary,
  Counterfactual,
  Decision,
  EvidenceResponse,
  FeedbackEntry,
  Flag,
  FunnelData,
  GeoEvent,
  GraphEdge,
  GraphNode,
  HealthData,
  InjectResult,
  LineDecision,
  LogEntry,
  ModelCard,
  NetworkData,
  OverlayInfo,
  QueueData,
  RiskLevel,
  SignalKind,
  Tenant,
  TimelineEvent,
} from "../types";
import { DISCLAIMER, harmLevel, riskLevel, inr , inrCompact } from "../utils";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

interface TenantDb {
  scale: number;
  cases: CaseDetail[];
  audit: AuditEvent[];
  feedback: FeedbackEntry[];
  activity: { id: string; text: string; ts: string }[];
  injected: number;
  seq: number;
}

interface Store {
  tenants: Tenant[];
  dbs: Map<string, TenantDb>;
}

const g = globalThis as unknown as { __nexus?: Store };

const SEED_TENANTS: Tenant[] = [
  { id: "meridian", name: "Meridian Health Plan", plan: "Enterprise", region: "US East", claimsPerMonth: 1_240_000, users: 42, status: "active", createdAt: "2024-03-11" },
  { id: "northlake", name: "Northlake Mutual", plan: "Growth", region: "US Central", claimsPerMonth: 610_000, users: 18, status: "active", createdAt: "2024-08-02" },
  { id: "cascade", name: "Cascade Benefit Trust", plan: "Pilot", region: "US West", claimsPerMonth: 95_000, users: 6, status: "onboarding", createdAt: "2025-01-06" },
];

function store(): Store {
  if (!g.__nexus) g.__nexus = { tenants: SEED_TENANTS.map((t) => ({ ...t })), dbs: new Map() };
  return g.__nexus;
}

function hash(s: string) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return h >>> 0;
}

function rng(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const round2 = (n: number) => Math.round(n * 100) / 100;
const clamp = (n: number, lo = 0.05, hi = 0.99) => Math.min(hi, Math.max(lo, n));
const pick = <T,>(r: () => number, arr: T[]) => arr[Math.floor(r() * arr.length)];
const pad = (n: number, w = 4) => String(n).padStart(w, "0");
const ago = (minutes: number) => new Date(Date.now() - minutes * 60_000).toISOString();

const SCHEMES = ["Duplicate billing", "Upcoding", "Unbundling", "Phantom billing", "Impossible timing", "Referral loop", "DME billing pattern", "Identity misuse"];
const SPECIALTIES = ["Cardiology", "Orthopedics", "Dermatology", "Pain management", "Physical therapy", "DME supplier", "Laboratory", "Home health"];
const ASSIGNEES = ["A. Sharma", "J. Okafor", "L. Chen", "Unassigned"];
const LETTERS = "XYZWVUTSRQPNMLKJHGFEDCBA".split("");
const TOP_HOURS = [4, 5, 5, 5, 4, 6, 5, 5, 4, 6, 5, 5];
const LINES = [
  { id: "L1", code: "99215", description: "Office visit, established patient, level 5" },
  { id: "L2", code: "93000", description: "Electrocardiogram, complete" },
  { id: "L3", code: "80053", description: "Comprehensive metabolic panel" },
  { id: "L4", code: "85025", description: "Complete blood count with differential" },
  { id: "L5", code: "36415", description: "Routine venipuncture" },
];

const FIXED = [
  { id: "CS-2025-0042", providerId: "PRV-1042", risk: 0.91, amount: 487_300, harm: 0.82, members: 38, specialty: "Cardiology", name: "Dr. X", rule: "Duplicate billing", evidence: 0.87, assignee: "A. Sharma" },
  { id: "CS-2025-0039", providerId: "PRV-1042", risk: 0.87, amount: 234_100, harm: 0.78, members: 24, specialty: "Cardiology", name: "Dr. X", rule: "Upcoding", evidence: 0.81, assignee: "A. Sharma" },
  { id: "CS-2025-0051", providerId: "PRV-0871", risk: 0.84, amount: 189_400, harm: 0.65, members: 19, specialty: "Laboratory", name: "Dr. Y", rule: "Referral loop", evidence: 0.79, assignee: "J. Okafor" },
  { id: "CS-2025-0033", providerId: "PRV-0912", risk: 0.79, amount: 156_200, harm: 0.71, members: 27, specialty: "Pain management", name: "Dr. Z", rule: "Unbundling", evidence: 0.74, assignee: "L. Chen" },
  { id: "CS-2025-0198", providerId: "PRV-0455", risk: 0.74, amount: 89_100, harm: 0.45, members: 11, specialty: "Orthopedics", name: "Dr. W", rule: "Impossible timing", evidence: 0.7, assignee: "Unassigned" },
  { id: "CS-2025-0212", providerId: "PRV-0233", risk: 0.68, amount: 67_800, harm: 0.52, members: 14, specialty: "DME supplier", name: "Dr. V", rule: "DME billing pattern", evidence: 0.66, assignee: "Unassigned" },
];

function buildCase(
  r: () => number,
  index: number,
  base: { id: string; providerId: string; risk: number; amount: number; harm: number; members: number; specialty: string; name: string; rule: string; evidence: number; assignee: string },
  exact = false,
): CaseDetail {
  const signals: Record<SignalKind, number> = exact
    ? { rule: 0.92, ml: 0.88, graph: 0.84, temporal: 0.72 }
    : {
        rule: round2(clamp(base.risk + 0.04 - r() * 0.1)),
        ml: round2(clamp(base.risk + 0.02 - r() * 0.12)),
        graph: round2(clamp(base.risk - 0.02 - r() * 0.16)),
        temporal: round2(clamp(base.risk - 0.08 - r() * 0.2)),
      };
  const others = SCHEMES.filter((s) => s !== base.rule);
  const flags: Flag[] = exact
    ? [
        { id: "FLG-001", kind: "rule", name: "Duplicate billing", score: 0.96 },
        { id: "FLG-002", kind: "ml", name: "Upcoding", score: 0.78 },
        { id: "FLG-003", kind: "graph", name: "Referral loop", score: 0.84 },
        { id: "FLG-004", kind: "temporal", name: "Impossible timing", score: 0.92 },
      ]
    : [
        { id: "FLG-001", kind: "rule", name: base.rule, score: round2(clamp(signals.rule + 0.03)) },
        { id: "FLG-002", kind: "ml", name: others[Math.floor(r() * others.length)], score: signals.ml },
        { id: "FLG-003", kind: "graph", name: "Referral loop", score: signals.graph },
        { id: "FLG-004", kind: "temporal", name: "Billing spike", score: signals.temporal },
      ];
  const perMember = 2 + Math.floor(base.risk * 4);
  const harmFactors = exact
    ? ["38 elderly members affected", "Low-income ZIP codes", "Repeat exposure (5 claims per member in 30 days)"]
    : [
        `${base.members} members affected, ${Math.round(base.members * (0.3 + base.harm * 0.5))} aged 65 or older`,
        base.harm >= 0.6 ? "Concentrated in low-income ZIP codes" : "No concentration in low-income ZIP codes",
        `Repeat exposure (${perMember} claims per member in 30 days)`,
      ];
  const nLines = 3 + Math.floor(r() * 2);
  const lines = (exact ? [LINES[0], LINES[2], LINES[3]] : LINES.slice(0, nLines)).map((l, i) => ({
    ...l,
    amount: Math.round((base.amount / base.members / (i + 2)) * (0.6 + r() * 0.5)),
  }));
  const peers = Array.from({ length: 34 }, (_, i) => ({
    id: `peer-${i}`,
    suspicion: round2(clamp(r() * r() * 0.95 + 0.04)),
    evidence: round2(clamp(r() * 0.9 + 0.05)),
  }));
  return {
    id: base.id,
    providerId: base.providerId,
    providerName: base.name,
    specialty: base.specialty,
    risk: base.risk,
    level: riskLevel(base.risk),
    amount: base.amount,
    members: base.members,
    harm: base.harm,
    harmLevel: harmLevel(base.harm),
    evidence: base.evidence,
    status: index < 2 ? "pending_review" : index % 5 === 0 ? "in_review" : "pending_review",
    assignee: base.assignee,
    rule: base.rule,
    hours: index < TOP_HOURS.length ? TOP_HOURS[index] : 3 + Math.floor(r() * 5),
    openedAt: `2025-01-${pad(3 + (index % 12), 2)}T0${index % 9}:1${index % 6}:00Z`,
    signals,
    flags,
    harmFactors,
    lines,
    peers,
  };
}

function generate(tenantId: string): TenantDb {
  const r = rng(hash(tenantId));
  const scale = tenantId === "meridian" ? 1 : tenantId === "northlake" ? 0.52 : tenantId === "cascade" ? 0.18 : 0.3 + r() * 0.5;
  const cases: CaseDetail[] = [];
  const fixed = tenantId === "meridian" ? FIXED : [];
  fixed.forEach((f, i) => cases.push(buildCase(r, i, f, i === 0)));
  const total = 48;
  const start = fixed.length ? 0.66 : 0.93;
  const idBase = fixed.length ? 300 : 100 + (hash(tenantId) % 400);
  for (let i = fixed.length; i < total; i++) {
    const t = (i - fixed.length) / (total - fixed.length);
    const risk = round2(start - t * (start - 0.31) - r() * 0.012);
    const members = 4 + Math.floor(r() * 30);
    cases.push(
      buildCase(r, i, {
        id: `CS-2025-${pad(idBase + i * 7 + Math.floor(r() * 5))}`,
        providerId: `PRV-${pad(100 + Math.floor(r() * 1800))}`,
        risk,
        amount: Math.round((24_000 + (1 - t) * 105_000 * (0.55 + r() * 0.6)) / 100) * 100,
        harm: round2(clamp(0.2 + r() * 0.6)),
        members,
        specialty: pick(r, SPECIALTIES),
        name: `Dr. ${LETTERS[i % LETTERS.length]}`,
        rule: pick(r, SCHEMES),
        evidence: round2(clamp(risk - 0.08 + r() * 0.12)),
        assignee: pick(r, ASSIGNEES),
      }),
    );
  }
  const top = cases[0];
  const audit: AuditEvent[] = [
    { id: "a1", ts: "2025-01-10T14:28:00Z", actor: "AUD-007", action: "Opened case", caseId: top.id },
    { id: "a2", ts: "2025-01-10T14:29:00Z", actor: "AUD-007", action: "Viewed evidence for FLG-001", caseId: top.id },
    { id: "a3", ts: "2025-01-10T14:30:00Z", actor: "AUD-007", action: "Viewed network graph", caseId: top.id },
    { id: "a4", ts: "2025-01-10T11:02:00Z", actor: "system", action: "Model retrained", detail: "xgboost_fwa_v1.2.3 promoted after validation" },
    { id: "a5", ts: "2025-01-10T09:40:00Z", actor: "ADM-002", action: "Changed routing threshold", detail: "0.65 to 0.60" },
    { id: "a6", ts: "2025-01-09T16:12:00Z", actor: "AUD-011", action: "Assigned case", caseId: cases[2].id, detail: `Assigned to ${cases[2].assignee}` },
    { id: "a7", ts: "2025-01-09T15:47:00Z", actor: "AUD-011", action: "Exported queue as CSV", detail: "12 cases" },
    { id: "a8", ts: "2025-01-09T10:05:00Z", actor: "AUD-004", action: "Opened case", caseId: cases[3].id },
    { id: "a9", ts: "2025-01-08T13:31:00Z", actor: "AUD-004", action: "Generated brief (plain language)", caseId: cases[3].id },
    { id: "a10", ts: "2025-01-08T08:15:00Z", actor: "ADM-002", action: "Updated field mapping", detail: "cpt_cd mapped to procedure_code" },
  ];
  const activity = [
    { id: "act1", text: `AUD-007 opened ${top.id} for review`, ts: ago(2) },
    { id: "act2", text: "New referral loop detected across 5 providers", ts: ago(15) },
    { id: "act3", text: "Model retrained to v1.2.3", ts: ago(60) },
    { id: "act4", text: `${Math.round(142 * scale) || 12} new claims ingested`, ts: ago(120) },
  ];
  const feedback: FeedbackEntry[] = [
    { id: "f1", caseId: cases[4].id, actor: "AUD-004", ts: "2025-01-09T12:00:00Z", useful: true, reasons: ["Evidence was clear"], comment: "Timing evidence matched the EHR export." },
    { id: "f2", caseId: cases[7].id, actor: "AUD-011", ts: "2025-01-08T17:20:00Z", useful: false, reasons: ["Legitimate billing pattern"], comment: "Provider runs a high-volume infusion clinic; peer group is too broad." },
  ];
  return { scale, cases, audit, feedback, activity, injected: 0, seq: 100 };
}

function db(tenantId: string): TenantDb {
  const s = store();
  let d = s.dbs.get(tenantId);
  if (!d) {
    d = generate(tenantId);
    s.dbs.set(tenantId, d);
  }
  return d;
}

function findCase(d: TenantDb, id: string): CaseDetail {
  const c = d.cases.find((x) => x.id === id);
  if (!c) throw new ApiError(404, `Case ${id} was not found for this tenant.`);
  return c;
}

function summary(c: CaseDetail): CaseSummary {
  const { signals: _s, flags: _f, harmFactors: _h, lines: _l, peers: _p, ...rest } = c;
  return rest;
}

function ranked(d: TenantDb) {
  return [...d.cases].sort((a, b) => b.risk - a.risk);
}

function addAudit(d: TenantDb, e: Omit<AuditEvent, "id" | "ts">) {
  d.audit.unshift({ ...e, id: `a${++d.seq}`, ts: new Date().toISOString() });
}

function addActivity(d: TenantDb, text: string) {
  d.activity.unshift({ id: `act${++d.seq}`, text, ts: new Date().toISOString() });
  d.activity = d.activity.slice(0, 12);
}

// ---------- derived views ----------

function queue(d: TenantDb, investigators: number, hours: number): QueueData {
  const cases = ranked(d);
  const capacityHours = investigators * hours;
  let used = 0;
  const selected: CaseDetail[] = [];
  for (const c of cases) {
    if (c.status === "false_positive") continue;
    if (used + c.hours <= capacityHours) {
      used += c.hours;
      selected.push(c);
    }
  }
  const harmAll = cases.reduce((s, c) => s + c.harm * c.members, 0);
  const harmSel = selected.reduce((s, c) => s + c.harm * c.members, 0);
  return {
    capacityHours,
    usedHours: used,
    selected: selected.map((c) => c.id),
    total: cases.length,
    expectedRecovery: Math.round(selected.reduce((s, c) => s + c.amount * c.evidence, 0)),
    harmReduction: harmAll ? round2(harmSel / harmAll) : 0,
    cases: cases.map(summary),
  };
}

function funnel(d: TenantDb): FunnelData {
  const claims = Math.round(5000 * d.scale) + d.injected;
  const alerts = Math.round(640 * d.scale) + d.injected;
  const clusters = d.cases.length;
  const siu = queue(d, 3, 20).selected.length;
  const atRisk = d.cases.reduce((s, c) => s + c.amount, 0);
  const byProvider = new Map<string, { amount: number; risk: number; caseId: string }>();
  for (const c of ranked(d)) {
    const p = byProvider.get(c.providerId);
    if (p) p.amount += c.amount;
    else byProvider.set(c.providerId, { amount: c.amount, risk: c.risk, caseId: c.id });
  }
  const low = Math.round(452 * d.scale);
  const medium = Math.round(156 * d.scale);
  const high = Math.round(24 * d.scale);
  return {
    stages: [
      { key: "claims", label: "Claims", value: claims },
      { key: "alerts", label: "Alerts", value: alerts },
      { key: "clusters", label: "Clusters", value: clusters },
      { key: "cases", label: "SIU cases", value: siu },
    ],
    reduction: Math.round((1 - siu / claims) * 1000) / 10,
    metrics: [
      { key: "claims", label: "Claims", display: claims.toLocaleString("en-IN"), delta: "+12%", direction: "up" },
      { key: "alerts", label: "Alerts", display: alerts.toLocaleString("en-IN"), delta: "-8%", direction: "down" },
      { key: "cases", label: "SIU cases", display: String(siu), delta: "+2", direction: "up" },
      { key: "risk", label: "Amount at risk (INR)", display: inrCompact(atRisk), delta: "+₹3.4 lakh", direction: "up" },
    ],
    riskDistribution: [
      { level: "critical", count: Math.max(1, alerts - low - medium - high) },
      { level: "high", count: high },
      { level: "medium", count: medium },
      { level: "low", count: low },
    ],
    topProviders: [...byProvider.entries()]
      .sort((a, b) => b[1].amount - a[1].amount)
      .slice(0, 5)
      .map(([id, p]) => ({ id, amount: p.amount, level: riskLevel(p.risk), caseId: p.caseId })),
    activity: d.activity.slice(0, 6),
  };
}

const RULE_TEXT: Record<string, string> = {
  "Duplicate billing": "This claim is 98% identical to CLM-2025-00389.",
  Upcoding: "Level 5 evaluation codes are billed far more often than documented visit length supports.",
  Unbundling: "Component codes were billed separately where a bundled code applies.",
  "Phantom billing": "Services were billed on dates with no matching encounter record.",
  "Impossible timing": "Billed service time exceeds 24 hours for a single calendar day.",
  "Referral loop": "Referrals repeatedly circulate among the same small group of providers.",
  "DME billing pattern": "Equipment was billed without a qualifying prior visit on file.",
  "Identity misuse": "The same member ID was used at distant locations within a short window.",
};

function ringFor(c: CaseDetail): string[] {
  if (c.providerId === "PRV-1042") return ["PRV-1042", "PRV-0871", "PRV-0912", "PRV-0455", "PRV-0233"];
  const r = rng(hash(c.id + "ring"));
  const ids = new Set<string>([c.providerId]);
  while (ids.size < 5) ids.add(`PRV-${pad(100 + Math.floor(r() * 1800))}`);
  return [...ids];
}

function evidence(c: CaseDetail): EvidenceResponse {
  const r = rng(hash(c.id + "ev"));
  const member = `MBR-${pad(1000 + Math.floor(r() * 8000))}`;
  const ring = ringFor(c);
  const loopClaims = Math.round(c.members * 3.74);
  const k = c.risk;
  return {
    items: [
      {
        id: "FLG-001",
        kind: "rule",
        title: c.flags[0].name,
        scoreLabel: "Confidence",
        score: c.flags[0].score,
        summary: RULE_TEXT[c.flags[0].name] ?? "Rule conditions were met for this claim.",
        rowsTitle: "Matching fields",
        rows: [
          { label: "member_id", value: c.id === "CS-2025-0042" ? "MBR-8821" : member, match: true },
          { label: "provider_id", value: c.providerId, match: true },
          { label: "service_date", value: "2025-01-08", match: true },
          { label: "cpt_code", value: c.lines[0].code, match: true },
          { label: "billed_amt", value: c.id === "CS-2025-0042" ? "₹12,400" : inr(c.lines[0].amount), match: true },
        ],
        source: `claims.csv, row ${c.id === "CS-2025-0042" ? 421 : 100 + Math.floor(r() * 4800)}`,
        link: { label: "View original claim", href: `/cases/${c.id}?tab=timeline` },
      },
      {
        id: "FLG-002",
        kind: "ml",
        title: "Isolation forest",
        scoreLabel: "Score",
        score: c.signals.ml,
        summary: "Provider billing pattern is anomalous compared with specialty peers.",
        rowsTitle: "Features driving the anomaly (SHAP)",
        rows: [
          { label: "avg_claim_amount", value: `${inr(Math.round(1400 + k * 8600))} (peer: ₹1,400)`, delta: `+${(k * 0.37).toFixed(2)}` },
          { label: "visits_per_member", value: `${Math.round(2 + k * 11)} (peer: 2)`, delta: `+${(k * 0.31).toFixed(2)}` },
          { label: "level5_em_rate", value: `${Math.round(12 + k * 72)}% (peer: 12%)`, delta: `+${(k * 0.24).toFixed(2)}` },
          { label: "geographic_spread", value: `${Math.max(1, Math.round(k * 5.5))} cities per week`, delta: `+${(k * 0.2).toFixed(2)}` },
        ],
        source: "Model: xgboost_fwa_v1.2.3",
        link: { label: "View model card", href: "/models" },
      },
      {
        id: "FLG-003",
        kind: "graph",
        title: "Referral loop",
        scoreLabel: "Score",
        score: c.signals.graph,
        summary: `Provider is part of a ${ring.length}-provider referral loop.`,
        rowsTitle: "Loop summary",
        rows: [
          { label: "Loop", value: [...ring, ring[0]].join(" > ") },
          { label: "Total claims in loop", value: String(c.id === "CS-2025-0042" ? 142 : loopClaims) },
          { label: "Total amount (INR)", value: inr(c.amount) },
          { label: "Members affected", value: String(c.members) },
        ],
        link: { label: "View network graph", href: `/cases/${c.id}?tab=network` },
      },
      {
        id: "FLG-004",
        kind: "temporal",
        title: c.flags[3].name,
        scoreLabel: "Score",
        score: c.signals.temporal,
        summary: `Billed amount rose ${Math.round(k * 374)}% over the trailing 30 days against a flat peer baseline.`,
        rowsTitle: "Change over 30 days",
        rows: [
          { label: "Claims per week", value: `${Math.round(8 + k * 40)} (prior: ${Math.round(8 + k * 6)})` },
          { label: "Billed per week", value: `${inr(Math.round((c.amount / 4) * 0.9))} (prior: ${inr(Math.round(c.amount / 18))})` },
        ],
        link: { label: "View timeline", href: `/cases/${c.id}?tab=timeline` },
      },
    ],
    limitations: [
      `No prior investigation outcome for ${c.providerId}`,
      "EHR note duration may be incomplete",
      "Referral loop legitimacy unverified",
    ],
  };
}

const MONTHS = ["2024-01", "2024-02", "2024-03", "2024-04", "2024-05", "2024-06", "2024-07", "2024-08", "2024-09", "2024-10", "2024-11", "2024-12", "2025-01"];

function network(c: CaseDetail, memberCap = 60): NetworkData {
  const r = rng(hash(c.id + "net"));
  const ring = ringFor(c);
  const nodes: GraphNode[] = [];
  const edges: GraphEdge[] = [];
  ring.forEach((id, i) => {
    nodes.push({
      id,
      label: id,
      type: "provider",
      inLoop: true,
      name: i === 0 ? c.providerName : `Dr. ${LETTERS[(i + 1) % LETTERS.length]}`,
      specialty: i === 0 ? c.specialty : SPECIALTIES[(hash(id) + i) % SPECIALTIES.length],
      claims: i === 0 ? 342 : 60 + Math.floor(r() * 220),
      amount: i === 0 ? 1_200_000 : Math.round(120_000 + r() * 700_000),
      risk: i === 0 ? c.risk : round2(clamp(c.risk - 0.04 - r() * 0.2)),
      sharedAddresses: i === 0 ? 2 : Math.floor(r() * 3),
      priorInvestigations: i === 0 ? 1 : Math.floor(r() * 2),
      firstSeen: MONTHS[Math.min(i, 3)],
    });
  });
  ring.forEach((id, i) => {
    const next = ring[(i + 1) % ring.length];
    for (let k = 0; k < 2; k++) {
      edges.push({ id: `ref-${i}-${k}`, source: id, target: next, type: "referral", date: MONTHS[Math.min(12, 2 + i * 2 + k * 2)] });
    }
  });
  ["FAC-0101", "FAC-0240"].forEach((id, i) => {
    nodes.push({ id, label: id, type: "facility", name: i === 0 ? "Outpatient clinic A" : "Imaging center B", claims: 80 + Math.floor(r() * 120), amount: Math.round(90_000 + r() * 200_000), firstSeen: MONTHS[i * 3] });
    edges.push({ id: `fac-${i}-0`, source: ring[i], target: id, type: "claim", date: MONTHS[1 + i * 3] });
    edges.push({ id: `fac-${i}-1`, source: ring[i + 2], target: id, type: "claim", date: MONTHS[5 + i * 3] });
  });
  const members = Math.min(c.members, memberCap);
  for (let m = 0; m < members; m++) {
    const id = `MBR-${pad(1000 + Math.floor(r() * 8999))}-${m}`;
    const month = Math.floor(r() * 12) + 1;
    nodes.push({ id, label: id.slice(0, 8), type: "member", claims: 1 + Math.floor(r() * 6), amount: Math.round(800 + r() * 14_000), firstSeen: MONTHS[month] });
    const links = 1 + Math.floor(r() * 2.4);
    const startAt = Math.floor(r() * ring.length);
    for (let k = 0; k < links; k++) {
      edges.push({ id: `clm-${m}-${k}`, source: id, target: ring[(startAt + k) % ring.length], type: "claim", date: MONTHS[Math.min(12, month + k)] });
    }
  }
  return { centerId: c.providerId, nodes, edges, range: { from: MONTHS[0], to: MONTHS[12] } };
}

function globalNetwork(d: TenantDb): NetworkData {
  const seen = new Set<string>();
  const nodes: GraphNode[] = [];
  const edges: GraphEdge[] = [];
  const providers = new Set<string>();
  let n = 0;
  for (const c of ranked(d)) {
    if (providers.has(c.providerId)) continue;
    if (n >= 4) break;
    const ring = ringFor(c);
    if (ring.some((p) => providers.has(p))) continue;
    ring.forEach((p) => providers.add(p));
    const net = network(c, 14);
    for (const node of net.nodes) {
      if (seen.has(node.id)) continue;
      seen.add(node.id);
      nodes.push(node);
    }
    for (const e of net.edges) edges.push({ ...e, id: `g${n}-${e.id}` });
    n++;
  }
  const r = rng(hash("global" + d.cases[0].id));
  for (let i = 0; i < 16; i++) {
    const id = `PRV-${pad(2000 + i * 13)}`;
    nodes.push({ id, label: id, type: "provider", inLoop: false, name: `Dr. ${LETTERS[i % LETTERS.length]}${i}`, specialty: pick(r, SPECIALTIES), claims: 20 + Math.floor(r() * 150), amount: Math.round(20_000 + r() * 160_000), risk: round2(0.08 + r() * 0.3), sharedAddresses: 0, priorInvestigations: 0, firstSeen: MONTHS[Math.floor(r() * 6)] });
    const m = 2 + Math.floor(r() * 3);
    for (let k = 0; k < m; k++) {
      const mid = `MBR-${pad(9000 + i)}-${k}`;
      const month = Math.floor(r() * 12);
      nodes.push({ id: mid, label: mid.slice(0, 8), type: "member", claims: 1 + Math.floor(r() * 3), amount: Math.round(300 + r() * 3000), firstSeen: MONTHS[month] });
      edges.push({ id: `gx-${i}-${k}`, source: mid, target: id, type: "claim", date: MONTHS[month] });
    }
  }
  return { nodes, edges, range: { from: MONTHS[0], to: MONTHS[12] } };
}

function timeline(c: CaseDetail): TimelineEvent[] {
  const ring = ringFor(c);
  const dup = c.id === "CS-2025-0042" ? 47 : Math.round(c.members * 1.2);
  return [
    { id: "t1", date: "2024-09-14", title: "First referral between loop providers", detail: `${ring[0]} referred 3 members to ${ring[1]}.`, kind: "graph" },
    { id: "t2", date: "2024-11-02", title: "Referral loop closes", detail: `Referrals from ${ring[ring.length - 1]} return to ${ring[0]}, completing a ${ring.length}-provider loop.`, kind: "graph" },
    { id: "t3", date: "2024-12-12", title: "Billing volume departs from peer baseline", detail: `Weekly billed amount exceeds the ${c.specialty.toLowerCase()} peer median by more than 3 standard deviations.`, kind: "temporal" },
    { id: "t4", date: "2025-01-03", title: `${dup} claims matching ${c.rule.toLowerCase()} rule`, detail: "Claims submitted between Jan 3 and Jan 9 met the rule conditions.", kind: "rule" },
    { id: "t5", date: "2025-01-09", title: "Anomaly score crosses routing threshold", detail: `Isolation forest score reached ${c.signals.ml.toFixed(2)}.`, kind: "ml" },
    { id: "t6", date: "2025-01-10", title: `Referral spike to ${ring[1]}`, detail: "Referral count for the week is 4 times the trailing average.", kind: "graph" },
    { id: "t7", date: c.openedAt.slice(0, 10) > "2025-01-10" ? c.openedAt.slice(0, 10) : "2025-01-10", title: "Case opened for human review", detail: `Routed to the SIU queue. Assigned to ${c.assignee}.`, kind: "case" },
  ];
}

function brief(c: CaseDetail, type: "technical" | "plain"): Brief {
  const ring = ringFor(c);
  const dup = c.id === "CS-2025-0042" ? 47 : Math.round(c.members * 1.2);
  const spike = Math.round(c.risk * 374);
  const lvl = c.level[0].toUpperCase() + c.level.slice(1);
  const technical = type === "technical";
  return {
    caseId: c.id,
    type,
    provider: `${c.providerName} (${c.providerId})`,
    riskLine: `${c.risk.toFixed(2)} (${lvl})`,
    amount: c.amount,
    members: c.members,
    harmLine: `${c.harm.toFixed(2)} (${c.harmLevel === "Med" ? "Medium" : c.harmLevel})`,
    evidence: technical
      ? [
          `Rule: ${dup} claims matched ${c.rule.toLowerCase()} (Jan 3-9), confidence ${c.flags[0].score.toFixed(2)}`,
          `ML: isolation forest anomaly score ${c.signals.ml.toFixed(2)}`,
          `Graph: part of a ${ring.length}-provider referral loop, score ${c.signals.graph.toFixed(2)}`,
          `Temporal: billing spike +${spike}% in 30 days`,
        ]
      : [
          `${dup} claims in one week look the same as claims already submitted.`,
          "This provider bills very differently from similar providers.",
          `The provider and ${ring.length - 1} others keep referring the same patients to each other.`,
          `Billing rose sharply in the last month (about ${Math.round(spike / 100) + 1} times the earlier level).`,
        ],
    timeline: [
      `Jan 3-9: ${dup} claims matched the ${c.rule.toLowerCase()} rule`,
      `Jan 10: referral spike to ${ring[1]}`,
      `${c.openedAt.slice(5, 10) > "01-10" ? "Jan " + Number(c.openedAt.slice(8, 10)) : "Jan 10"}: case opened for review`,
    ],
    network: {
      providers: ring.length,
      members: c.members,
      text: technical
        ? `${ring.length} providers and ${c.members} members connected through referral and claim edges.`
        : `${ring.length} providers share ${c.members} patients between them.`,
    },
    confidence: c.risk,
    limitations: evidence(c).limitations,
    recommendedAction: technical
      ? `Escalate to SIU Tier 2. Request medical records for Jan 3-9. Estimated review time: ${c.hours} hours.`
      : `A senior investigator should look at this case and request the medical records for Jan 3-9. This should take about ${c.hours} hours.`,
    disclaimer: DISCLAIMER,
    generatedAt: new Date().toISOString(),
  };
}

function counterfactual(c: CaseDetail): Counterfactual {
  const threshold = 0.6;
  const mk = (id: string, label: string, description: string, drop: number) => {
    const newRisk = round2(clamp(c.risk - drop, 0.02));
    return { id, label, description, newRisk, wouldRoute: newRisk >= threshold };
  };
  return {
    baseline: c.risk,
    threshold,
    scenarios: [
      mk("cf1", `Without the ${c.rule.toLowerCase()} match`, "Remove the rule signal and keep everything else unchanged.", c.signals.rule * 0.22),
      mk("cf2", "If billing matched the peer median", "Set average claim amount and visit frequency to the specialty median.", c.signals.ml * 0.31),
      mk("cf3", "If the referral loop were not present", "Remove referral edges among the loop providers.", c.signals.graph * 0.19),
      mk("cf4", "If level 5 visits were billed as level 3", "Re-score with evaluation codes one tier lower on affected lines.", c.signals.ml * 0.12),
      mk("cf5", "If all signals above were absent", "Combined effect of the four scenarios.", c.risk * 0.78),
    ],
  };
}

const CITIES = [
  { city: "New York, NY", lat: 40.7128, lng: -74.006 },
  { city: "Miami, FL", lat: 25.7617, lng: -80.1918 },
  { city: "Chicago, IL", lat: 41.8781, lng: -87.6298 },
  { city: "Houston, TX", lat: 29.7604, lng: -95.3698 },
  { city: "Phoenix, AZ", lat: 33.4484, lng: -112.074 },
  { city: "Los Angeles, CA", lat: 34.0522, lng: -118.2437 },
  { city: "Seattle, WA", lat: 47.6062, lng: -122.3321 },
  { city: "Denver, CO", lat: 39.7392, lng: -104.9903 },
  { city: "Atlanta, GA", lat: 33.749, lng: -84.388 },
  { city: "Boston, MA", lat: 42.3601, lng: -71.0589 },
];

function km(a: { lat: number; lng: number }, b: { lat: number; lng: number }) {
  const rad = (x: number) => (x * Math.PI) / 180;
  const dLat = rad(b.lat - a.lat);
  const dLng = rad(b.lng - a.lng);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLng / 2) ** 2;
  return Math.round(6371 * 2 * Math.asin(Math.sqrt(h)));
}

function geo(d: TenantDb): GeoEvent[] {
  const r = rng(hash("geo" + d.cases[0].id));
  return ranked(d)
    .slice(0, 14)
    .map((c, i) => {
      const ai = Math.floor(r() * CITIES.length);
      const bi = (ai + 1 + Math.floor(r() * (CITIES.length - 1))) % CITIES.length;
      const a = CITIES[ai];
      const b = CITIES[bi];
      const minutesApart = 25 + Math.floor(r() * 150);
      const h = 8 + Math.floor(r() * 6);
      const m = Math.floor(r() * 50);
      const end = h * 60 + m + minutesApart;
      const isMember = i % 3 === 2;
      return {
        id: `GEO-${pad(i + 1, 3)}`,
        subject: isMember ? `MBR-${pad(1000 + Math.floor(r() * 8000))}` : c.providerId,
        subjectType: isMember ? ("member" as const) : ("provider" as const),
        date: `2025-01-${pad(3 + (i % 9), 2)}`,
        caseId: c.id,
        a: { ...a, time: `${pad(h, 2)}:${pad(m, 2)}` },
        b: { ...b, time: `${pad(Math.floor(end / 60), 2)}:${pad(end % 60, 2)}` },
        distanceKm: km(a, b),
        minutesApart,
        level: c.level,
      };
    });
}

function analytics(d: TenantDb): AnalyticsData {
  const r = rng(hash("an" + d.cases[0].id));
  const s = d.scale;
  const monthly = MONTHS.slice(1).map((month, i) => {
    const identified = Math.round((1.9 + i * 0.21 + r() * 0.5) * 1_000_000 * s);
    return {
      month,
      alerts: Math.round((880 - i * 20 + r() * 60) * s),
      cases: Math.round((7 + i * 0.45 + r() * 2) * Math.max(0.4, s)),
      identified,
      recovered: Math.round(identified * (0.34 + i * 0.012 + r() * 0.05)),
    };
  });
  const precision = MONTHS.slice(1).map((month, i) => {
    const p = round2(0.58 + i * 0.019 + r() * 0.03);
    return { month, precision: p, falsePositive: round2(1 - p) };
  });
  const bySignal = SCHEMES.map((scheme) => {
    const cs = d.cases.filter((c) => c.rule === scheme);
    return { scheme, cases: cs.length, amount: cs.reduce((a, c) => a + c.amount, 0) };
  }).sort((a, b) => b.amount - a.amount);
  const specialties = SPECIALTIES;
  const z = SCHEMES.map((scheme) => specialties.map((sp) => d.cases.filter((c) => c.rule === scheme && c.specialty === sp).length));
  const workload = ASSIGNEES.slice(0, 3).map((investigator) => {
    const mine = d.cases.filter((c) => c.assignee === investigator);
    return {
      investigator,
      open: mine.filter((c) => c.status === "pending_review" || c.status === "in_review" || c.status === "needs_info").length,
      closed: 6 + Math.floor(r() * 12) + mine.filter((c) => c.status === "confirmed" || c.status === "false_positive" || c.status === "escalated").length,
      avgHours: Math.round((3.4 + r() * 2.2) * 10) / 10,
    };
  });
  return {
    monthly,
    bySignal,
    precision,
    heatmap: { schemes: SCHEMES, specialties, z },
    workload,
    totals: {
      identified: monthly.reduce((a, m) => a + m.identified, 0),
      recovered: monthly.reduce((a, m) => a + m.recovered, 0),
      avgDaysToDecision: 6.4,
      precision: precision[precision.length - 1].precision,
    },
  };
}

function models(): ModelCard {
  return {
    name: "xgboost_fwa",
    version: "v1.2.3",
    type: "Gradient-boosted trees with isolation forest and graph features",
    trainedAt: "2025-01-10",
    intendedUse:
      "Ranks healthcare claims and provider clusters for human review by a Special Investigations Unit. Scores indicate how unusual a billing pattern is. They are not a finding of fraud, waste or abuse.",
    outOfScope: [
      "Automatically denying, pending or recouping claims",
      "Decisions about individual members' eligibility or care",
      "Use without review by a qualified investigator",
    ],
    trainingData:
      "5,000 synthetic claims across 412 synthetic providers and 1,960 synthetic members, with 8 injected scheme types. No real claims or protected health information were used.",
    metrics: [
      { label: "Precision at top 50", value: 0.81, note: "Share of top-ranked clusters that reviewers confirmed" },
      { label: "Recall", value: 0.74, note: "Share of injected schemes that were flagged" },
      { label: "ROC AUC", value: 0.93, note: "Held-out synthetic claims" },
      { label: "PR AUC", value: 0.68, note: "Class prevalence 2.1%" },
    ],
    features: [
      { name: "avg_claim_amount vs. peers", importance: 0.21 },
      { name: "visits_per_member", importance: 0.17 },
      { name: "level5_em_rate", importance: 0.14 },
      { name: "referral_loop_membership", importance: 0.13 },
      { name: "duplicate_similarity", importance: 0.12 },
      { name: "geographic_spread", importance: 0.09 },
      { name: "billing_velocity_30d", importance: 0.08 },
      { name: "shared_address_count", importance: 0.06 },
    ],
    limitations: [
      "Trained on synthetic data; performance on production claims is unverified.",
      "Peer groups are defined by specialty only and do not account for case mix or practice size.",
      "Referral loops can be legitimate (for example, integrated care groups); the graph signal cannot tell these apart.",
      "Labels come from injected schemes and investigator feedback, which may carry reviewer bias.",
    ],
    bias: [
      { group: "Urban providers", category: "Geography", flagRate: 0.128, falsePositiveRate: 0.041, ratio: 1.0, status: "pass" },
      { group: "Rural providers", category: "Geography", flagRate: 0.137, falsePositiveRate: 0.047, ratio: 1.15, status: "pass" },
      { group: "Solo practices", category: "Practice size", flagRate: 0.162, falsePositiveRate: 0.058, ratio: 1.41, status: "review" },
      { group: "Group practices", category: "Practice size", flagRate: 0.119, falsePositiveRate: 0.041, ratio: 1.0, status: "pass" },
      { group: "Low-income ZIP codes", category: "Member area", flagRate: 0.141, falsePositiveRate: 0.046, ratio: 1.1, status: "pass" },
      { group: "Other ZIP codes", category: "Member area", flagRate: 0.126, falsePositiveRate: 0.042, ratio: 1.0, status: "pass" },
      { group: "Members 65 and older", category: "Member age", flagRate: 0.133, falsePositiveRate: 0.044, ratio: 1.05, status: "pass" },
      { group: "Members under 65", category: "Member age", flagRate: 0.129, falsePositiveRate: 0.042, ratio: 1.0, status: "pass" },
    ],
    drift: MONTHS.slice(4).map((month, i) => ({ month, psi: round2(0.03 + i * 0.011 + (i % 3) * 0.008) })),
    history: [
      { version: "v1.2.3", date: "2025-01-10", note: "Retrained with 214 investigator decisions. Added shared-address feature." },
      { version: "v1.2.2", date: "2024-12-02", note: "Recalibrated scores after threshold review." },
      { version: "v1.1.0", date: "2024-10-18", note: "Added referral-loop graph features." },
      { version: "v1.0.0", date: "2024-08-05", note: "Initial release." },
    ],
  };
}

function health(): HealthData {
  const r = rng(Math.floor(Date.now() / 30_000));
  const services = ["Ingest API", "Rules engine", "ML scoring", "Graph service", "Brief generator", "Audit store"].map((name, i) => ({
    name,
    status: (name === "Brief generator" && r() > 0.7 ? "degraded" : "operational") as "operational" | "degraded",
    latencyMs: Math.round([38, 22, 140, 210, 860, 18][i] * (0.85 + r() * 0.35)),
    uptime: [99.99, 99.98, 99.95, 99.91, 99.72, 99.99][i],
  }));
  const now = Date.now();
  return {
    status: services.some((s) => s.status !== "operational") ? "degraded" : "operational",
    checkedAt: new Date().toISOString(),
    services,
    latency: Array.from({ length: 24 }, (_, i) => {
      const t = new Date(now - (23 - i) * 5 * 60_000);
      const p50 = Math.round(110 + r() * 50);
      return { t: `${pad(t.getHours(), 2)}:${pad(t.getMinutes(), 2)}`, p50, p95: p50 + Math.round(140 + r() * 160) };
    }),
    ingest: { perMinute: Math.round(60 + r() * 30), backlog: Math.round(r() * 40), lastEventAt: ago(0.2) },
  };
}

function logs(): LogEntry[] {
  const r = rng(77);
  const samples: [LogEntry["level"], string, string][] = [
    ["info", "ingest", "Batch accepted: 142 claims"],
    ["info", "rules", "Evaluated 142 claims against 23 rules in 61 ms"],
    ["info", "ml", "Scored 142 claims with xgboost_fwa_v1.2.3"],
    ["warn", "graph", "Loop detection exceeded 2 s budget (2,140 ms)"],
    ["info", "audit", "Audit event persisted"],
    ["error", "brief", "Brief generation timed out after 10 s; retried successfully"],
    ["info", "auth", "Role change applied: analyst to investigator"],
    ["warn", "ingest", "Field paid_amt missing on 3 claims; defaulted to null"],
    ["info", "ml", "Drift check passed (PSI 0.07)"],
    ["info", "webhook", "Delivered case.routed to tenant endpoint (200)"],
  ];
  const tenants = store().tenants;
  return Array.from({ length: 60 }, (_, i) => {
    const [level, service, message] = samples[Math.floor(r() * samples.length)];
    return { id: `log-${i}`, ts: ago(i * 3 + r() * 2), level, service, tenantId: tenants[Math.floor(r() * tenants.length)].id, message };
  });
}

const SCHEME_SIGNALS: Record<string, { name: string; kinds: SignalKind[]; rule: string }> = {
  phantom: { name: "Phantom billing", kinds: ["rule", "ml"], rule: "phantom_billing" },
  duplicate: { name: "Duplicate billing", kinds: ["rule", "ml", "graph"], rule: "duplicate_billing" },
  upcoding: { name: "Upcoding", kinds: ["ml", "rule"], rule: "upcoding_em_level" },
  unbundling: { name: "Unbundling", kinds: ["rule"], rule: "unbundled_components" },
  impossible_day: { name: "Impossible timing", kinds: ["rule", "temporal"], rule: "impossible_day" },
  referral_ring: { name: "Referral loop", kinds: ["graph", "ml", "rule"], rule: "referral_loop" },
  dme: { name: "DME billing pattern", kinds: ["rule", "ml"], rule: "dme_no_prior_visit" },
  identity: { name: "Identity misuse", kinds: ["rule", "temporal", "graph"], rule: "identity_distance" },
};

const KIND_DETECTOR: Record<SignalKind, string> = { rule: "", ml: "isolation_forest", graph: "referral_loop", temporal: "billing_velocity" };

function inject(d: TenantDb, scheme: string, actor: string): InjectResult {
  const def = SCHEME_SIGNALS[scheme];
  if (!def) throw new ApiError(400, `Unknown scheme "${scheme}".`);
  const r = rng(hash(scheme + d.seq + Date.now()));
  d.injected += 1;
  const n = 9999 - (d.injected - 1);
  const risk = round2(0.86 + r() * 0.09);
  const c = buildCase(r, 99, {
    id: `CS-2025-${n}`,
    providerId: `PRV-${pad(3000 + Math.floor(r() * 900))}`,
    risk,
    amount: Math.round((40_000 + r() * 160_000) / 100) * 100,
    harm: round2(0.45 + r() * 0.4),
    members: 6 + Math.floor(r() * 24),
    specialty: pick(r, SPECIALTIES),
    name: "Dr. Q",
    rule: def.name,
    evidence: round2(risk - 0.05),
    assignee: "Unassigned",
  });
  c.hours = 4;
  c.openedAt = new Date().toISOString();
  d.cases.push(c);
  const flags: Flag[] = def.kinds.map((kind, i) => ({
    id: `FLG-${pad(i + 1, 3)}`,
    kind,
    name: kind === "rule" ? def.rule : KIND_DETECTOR[kind],
    score: round2(clamp(0.98 - i * 0.045 - r() * 0.02)),
  }));
  const claimId = `CLM-2025-${n}`;
  addAudit(d, { actor, action: "Injected test scheme", caseId: c.id, detail: `${def.name} (${claimId})` });
  addActivity(d, `Test scheme injected: ${def.name} flagged as ${c.id}`);
  return { scheme, claimId, caseId: c.id, latencyMs: 180 + Math.floor(r() * 240), caughtBy: def.kinds, flags };
}

const DECISION_STATUS: Record<Decision, CaseStatus> = {
  CONFIRM_FWA: "confirmed",
  NEEDS_INFO: "needs_info",
  FALSE_POSITIVE: "false_positive",
  REASSIGN: "in_review",
};

const DECISION_TEXT: Record<Decision, string> = {
  CONFIRM_FWA: "confirmed for SIU referral",
  NEEDS_INFO: "marked as needing more information",
  FALSE_POSITIVE: "closed as a false positive",
  REASSIGN: "reassigned",
};

interface DecisionBody {
  decision: Decision;
  lines?: Record<string, LineDecision>;
  notes?: string;
  nextAction?: string;
  assignee?: string;
  actor?: string;
}

function decide(d: TenantDb, id: string, body: DecisionBody) {
  const c = findCase(d, id);
  if (!body?.decision || !(body.decision in DECISION_STATUS)) throw new ApiError(400, "A decision is required.");
  const actor = body.actor ?? "unknown";
  c.status = body.decision === "CONFIRM_FWA" && body.nextAction?.includes("Tier 2") ? "escalated" : DECISION_STATUS[body.decision];
  if (body.decision === "REASSIGN" && body.assignee) c.assignee = body.assignee;
  for (const [line, v] of Object.entries(body.lines ?? {})) {
    addAudit(d, { actor, action: `Line ${line}: ${v.toUpperCase()}`, caseId: id });
  }
  addAudit(d, {
    actor,
    action: `Decision: ${body.decision}`,
    caseId: id,
    detail: [body.nextAction, body.notes].filter(Boolean).join(" | ") || undefined,
  });
  addActivity(d, `${actor} ${DECISION_TEXT[body.decision]} ${id}`);
  return { ok: true, case: c };
}

function overlay(d: TenantDb, entityId: string): OverlayInfo {
  const c = ranked(d).find((x) => x.providerId === entityId || x.id === entityId);
  if (!c) {
    const r = rng(hash(entityId));
    const risk = round2(0.05 + r() * 0.3);
    return { id: entityId, risk, level: riskLevel(risk), reasons: [], caseId: null };
  }
  return {
    id: entityId,
    risk: c.risk,
    level: c.level,
    reasons: [...c.flags].sort((a, b) => b.score - a.score).slice(0, 3).map((f) => ({ label: f.name, score: f.score })),
    caseId: c.id,
  };
}

// ---------- router ----------

export function handle(method: string, path: string[], tenantId: string, query: URLSearchParams, body: any): unknown {
  const s = store();
  const d = db(tenantId);
  const [a, b, c] = path;
  const route = `${method} ${path.join("/")}`;

  if (route === "GET tenants") return s.tenants;
  if (route === "GET funnel") return funnel(d);
  if (route === "GET queue") {
    const inv = Math.min(20, Math.max(1, Number(query.get("investigators") ?? 3)));
    const hrs = Math.min(40, Math.max(1, Number(query.get("hours") ?? 20)));
    return queue(d, inv, hrs);
  }
  if (route === "GET cases") return ranked(d).map(summary);
  if (route === "GET network") return globalNetwork(d);
  if (route === "GET geo") return geo(d);
  if (route === "GET analytics") return analytics(d);
  if (route === "GET models") return models();
  if (route === "GET health") return health();
  if (route === "GET audit") return d.audit;
  if (route === "POST audit") {
    addAudit(d, { actor: body?.actor ?? "unknown", action: String(body?.action ?? "Viewed"), caseId: body?.caseId, detail: body?.detail });
    return { ok: true };
  }
  if (route === "GET feedback") return d.feedback;
  if (route === "POST feedback") {
    if (!body?.caseId) throw new ApiError(400, "caseId is required.");
    const entry: FeedbackEntry = {
      id: `f${++d.seq}`,
      caseId: body.caseId,
      actor: body.actor ?? "unknown",
      ts: new Date().toISOString(),
      useful: !!body.useful,
      reasons: Array.isArray(body.reasons) ? body.reasons : [],
      comment: String(body.comment ?? ""),
    };
    d.feedback.unshift(entry);
    addAudit(d, { actor: entry.actor, action: "Submitted feedback", caseId: entry.caseId, detail: entry.useful ? "Useful" : "Not useful" });
    return entry;
  }
  if (route === "POST inject") return inject(d, String(body?.scheme ?? ""), body?.actor ?? "unknown");
  if (route === "POST claims/ingest") {
    d.injected += 0;
    return { accepted: 1, claimId: body?.claim_id ?? "CLM-TEST-0001", risk: 0.12, level: "low" as RiskLevel, latencyMs: 41 };
  }
  if (route === "POST claims/batch") return { accepted: Array.isArray(body?.claims) ? body.claims.length : 0, rejected: 0 };
  if (route === "POST demo/reset") {
    s.dbs.delete(tenantId);
    return { ok: true };
  }
  if (route === "GET admin/tenants") return s.tenants;
  if (route === "POST admin/tenants") {
    const name = String(body?.name ?? "").trim();
    if (!name) throw new ApiError(400, "Company name is required.");
    const id = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || `tenant-${s.tenants.length + 1}`;
    const existing = s.tenants.find((t) => t.id === id);
    if (existing) return existing;
    const t: Tenant = { id, name, plan: "Pilot", region: body?.region ?? "US East", claimsPerMonth: Number(body?.claimsPerMonth) || 50_000, users: 1, status: "onboarding", createdAt: new Date().toISOString().slice(0, 10) };
    s.tenants.push(t);
    return t;
  }
  if (route === "GET admin/logs") return logs();
  if (a === "overlay" && b && method === "GET") return overlay(d, decodeURIComponent(b));
  if (a === "audit" && b && method === "GET") return d.audit.filter((e) => e.caseId === b);
  if (a === "cases" && b) {
    const item = findCase(d, b);
    if (!c && method === "GET") return item;
    if (c === "evidence" && method === "GET") return evidence(item);
    if (c === "network" && method === "GET") return network(item);
    if (c === "timeline" && method === "GET") return timeline(item);
    if (c === "counterfactual" && method === "GET") return counterfactual(item);
    if (c === "brief" && method === "POST") return brief(item, body?.type === "plain" ? "plain" : "technical");
    if (c === "decision" && method === "POST") return decide(d, b, body);
    if (c === "assign" && method === "POST") {
      const actor = body?.actor ?? "unknown";
      if (body?.assignee && body.assignee !== item.assignee) {
        item.assignee = body.assignee;
        addAudit(d, { actor, action: "Assigned case", caseId: b, detail: `Assigned to ${body.assignee}` });
      }
      if (body?.status && body.status !== item.status) {
        item.status = body.status;
        addAudit(d, { actor, action: "Changed status", caseId: b, detail: body.status });
      }
      return item;
    }
  }
  throw new ApiError(404, `No route for ${route}.`);
}
