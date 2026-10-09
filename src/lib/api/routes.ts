// Maps each data request the UI makes onto backend calls and runs the result through an adapter.
// The UI keeps its own vocabulary (paths and shapes in src/lib/types.ts); the backend keeps its
// schemas; this file and src/lib/adapters are the only place the two meet.
import type { BackendCaseDetail, BackendCaseSummary, BackendClaim, BackendDashboard, BackendEvidence, BackendInject, BackendOptimize, BackendQueue } from "@/lib/adapters/backend-types";
import { adaptCaseDetail, adaptCaseSummary, adaptDecisionRequest, assigneeId } from "@/lib/adapters/case.adapter";
import { adaptClaim, adaptLevel, buildTestClaim } from "@/lib/adapters/claim.adapter";
import { adaptEvidence } from "@/lib/adapters/evidence.adapter";
import { adaptAuditEvent, adaptDashboard } from "@/lib/adapters/funnel.adapter";
import {
  adaptAnalytics,
  adaptBrief,
  adaptComplianceReport,
  adaptCounterfactual,
  adaptCoverageRules,
  adaptFeedback,
  adaptFeedbackRequest,
  adaptGeo,
  adaptHealth,
  adaptInject,
  adaptLogs,
  adaptModelCard,
  adaptNetwork,
  adaptOverlay,
  adaptTenant,
  adaptTimeline,
} from "@/lib/adapters/misc.adapter";
import { adaptQueue } from "@/lib/adapters/queue.adapter";
import { useAuthStore } from "@/stores";
import { ApiError, backend } from "./client";

type Init = { method?: "GET" | "POST"; body?: any; tenantId?: string };
type Handler = (m: RegExpMatchArray, q: URLSearchParams, init: Init) => Promise<unknown>;

const WORKFLOW = ["pending_review", "in_review", "needs_info"];
const CLIENT_EVENTS: [RegExp, string][] = [
  [/^Exported queue as CSV/, "export.queue_csv"],
  [/^Exported brief as PDF/, "export.brief_pdf"],
  [/^Sent to SIU queue from overlay/, "overlay.sent_to_siu"],
];

async function timed(name: string, path: string): Promise<{ name: string; ok: boolean; ms: number; note?: string }> {
  const start = performance.now();
  try {
    const body = await backend<any>(path, { auth: false });
    return { name, ok: body.status === "ok", ms: Math.round(performance.now() - start), note: body.note ?? body.mode ?? undefined };
  } catch {
    return { name, ok: false, ms: Math.round(performance.now() - start) };
  }
}

async function tenants() {
  const list = await backend<{ tenants: any[] }>("/tenants");
  let counts: Record<string, { claims: number; cases: number }> = {};
  if (useAuthStore.getState().role === "admin") {
    try {
      const overview = await backend<{ tenants: any[] }>("/admin/overview");
      counts = Object.fromEntries(overview.tenants.map((t) => [t.slug, { claims: t.claims, cases: t.cases }]));
    } catch {}
  }
  return list.tenants.map((t) => adaptTenant(t, counts[t.slug]));
}

async function waitForClaim(claimId: string, tenant?: string) {
  for (let i = 0; i < 60; i++) {
    const s = await backend<any>(`/claims/${encodeURIComponent(claimId)}/status`, { tenant });
    if (s.status !== "processing") return s;
    await new Promise((r) => setTimeout(r, 250));
  }
  throw new ApiError("The claim was accepted but detection has not finished after 15 seconds. Check that the backend worker is running.", 504);
}

const ROUTES: [method: "GET" | "POST", pattern: RegExp, handler: Handler][] = [
  ["GET", /^\/tenants$/, tenants],
  ["GET", /^\/admin\/tenants$/, tenants],
  ["POST", /^\/admin\/tenants$/, async (_m, _q, init) => {
    try {
      return adaptTenant(await backend<any>("/tenants", { method: "POST", body: { name: init.body.name } }));
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        const existing = (await tenants()).find((t) => t.name.toLowerCase() === String(init.body.name).toLowerCase());
        if (existing) return existing;
      }
      throw e;
    }
  }],

  ["GET", /^\/funnel$/, async () => adaptDashboard(await backend<BackendDashboard>("/dashboard"))],

  ["GET", /^\/queue$/, async (_m, q) => {
    const params = { num_investigators: Number(q.get("investigators") ?? 3), hours_per_investigator: Number(q.get("hours") ?? 20) };
    const [queue, plan] = await Promise.all([backend<BackendQueue>("/queue", { query: params }), backend<BackendOptimize>("/queue/optimize", { method: "POST", body: params })]);
    return adaptQueue(queue, plan);
  }],

  ["GET", /^\/cases$/, async () => (await backend<{ items: BackendCaseSummary[] }>("/cases", { query: { limit: 500 } })).items.map(adaptCaseSummary)],
  ["GET", /^\/cases\/([^/]+)$/, async (m) => {
    const [detail, all] = await Promise.all([backend<BackendCaseDetail>(`/cases/${m[1]}`), backend<{ items: BackendCaseSummary[] }>("/cases", { query: { limit: 200 } })]);
    return adaptCaseDetail(detail, all.items);
  }],
  ["GET", /^\/cases\/([^/]+)\/evidence$/, async (m) => adaptEvidence(await backend<BackendEvidence>(`/cases/${m[1]}/evidence`))],
  ["GET", /^\/cases\/([^/]+)\/network$/, async (m) => adaptNetwork(await backend(`/cases/${m[1]}/network`))],
  ["GET", /^\/cases\/([^/]+)\/timeline$/, async (m) => adaptTimeline(await backend(`/cases/${m[1]}/timeline`))],
  ["GET", /^\/cases\/([^/]+)\/counterfactual$/, async (m) => adaptCounterfactual(await backend(`/cases/${m[1]}/counterfactual`))],
  ["POST", /^\/cases\/([^/]+)\/brief$/, async (m, _q, init) => {
    const type: "technical" | "plain" = init.body?.type === "plain" ? "plain" : "technical";
    if (init.body?.enhance) return adaptBrief(await backend(`/briefs/${m[1]}/enhance`, { method: "POST", body: { brief_type: type } }), type);
    try {
      return adaptBrief(await backend(`/briefs/${m[1]}/${type === "plain" ? "plain" : "generate"}`, { method: "POST" }), type);
    } catch (e) {
      // Roles that cannot generate a brief can still read the latest stored one.
      if (e instanceof ApiError && e.status === 403) return adaptBrief(await backend(`/briefs/${m[1]}`, { query: { type } }), type);
      throw e;
    }
  }],
  ["POST", /^\/cases\/([^/]+)\/decision$/, async (m, _q, init) => backend(`/cases/${m[1]}/decision`, { method: "POST", body: adaptDecisionRequest(init.body) })],
  ["POST", /^\/cases\/([^/]+)\/assign$/, async (m, _q, init) => {
    const { assignee, status } = init.body ?? {};
    if (assignee) {
      if (assignee === "Unassigned") throw new ApiError("A case cannot be unassigned. Reassign it to another reviewer instead.", 422);
      await backend("/queue/assign", { method: "POST", body: { case_id: decodeURIComponent(m[1]), assignee: assigneeId(assignee) } });
    }
    if (status) {
      if (!WORKFLOW.includes(status)) throw new ApiError("An outcome can only be set by recording a decision. Use the Decision tab.", 422);
      await backend(`/cases/${m[1]}/status`, { method: "POST", query: { status } });
    }
    return adaptCaseDetail(await backend<BackendCaseDetail>(`/cases/${m[1]}`));
  }],

  ["GET", /^\/network$/, async () => adaptNetwork(await backend("/network"))],
  ["GET", /^\/geo$/, async () => adaptGeo(await backend("/network/geo-conflicts"))],

  ["GET", /^\/audit$/, async () => (await backend<{ events: any[] }>("/audit", { query: { limit: 500 } })).events.map(adaptAuditEvent)],
  ["GET", /^\/audit\/([^/]+)$/, async (m) => (await backend<{ events: any[] }>(`/audit/${m[1]}`)).events.map(adaptAuditEvent)],
  ["POST", /^\/audit$/, async (_m, _q, init) => {
    // Views are recorded by the backend when the data is read. Only actions that happen purely
    // in the browser are reported from here.
    const event = CLIENT_EVENTS.find(([re]) => re.test(String(init.body?.action ?? "")));
    if (!event) return { recorded: false };
    return backend("/audit/events", { method: "POST", body: { action: event[1], case_id: init.body.caseId, detail: init.body.detail ?? init.body.action } });
  }],

  ["GET", /^\/feedback$/, async () => (await backend<{ items: any[] }>("/feedback")).items.map(adaptFeedback)],
  ["POST", /^\/feedback$/, async (_m, _q, init) => backend("/feedback", { method: "POST", body: adaptFeedbackRequest(init.body) })],

  ["POST", /^\/inject$/, async (_m, _q, init) => adaptInject(await backend<BackendInject>("/inject", { method: "POST", body: { scheme: init.body.scheme } }), init.body.scheme)],

  ["GET", /^\/models$/, async () => {
    const list = await backend<{ versions: any[]; serving: string | null }>("/models");
    const version = list.serving ?? list.versions.find((v) => v.is_deployed)?.version ?? list.versions[0]?.version;
    if (!version) throw new ApiError("No model has been trained yet. Run scripts.train_xgboost in the backend folder.", 404);
    let card: any;
    try {
      card = await backend(`/models/${version}/card`);
    } catch {
      card = await backend(`/models/${version}`);
    }
    return adaptModelCard(card, list.versions);
  }],

  ["GET", /^\/health$/, async () => {
    const checks = await Promise.all([timed("API and database", "/health/ready"), timed("Database", "/health/db"), timed("Cache", "/health/redis"), timed("ML scoring", "/health/ml-server"), timed("Copilot model", "/health/ollama")]);
    let perf = null;
    try {
      perf = await backend("/health/performance");
    } catch {}
    return adaptHealth(checks, perf);
  }],
  ["GET", /^\/analytics$/, async () => adaptAnalytics(await backend("/admin/analytics"))],
  ["GET", /^\/admin\/logs$/, async () => adaptLogs(await backend("/admin/logs"))],

  ["GET", /^\/claims$/, async (_m, q) => (await backend<{ items: BackendClaim[] }>("/claims", { query: { limit: Number(q.get("limit") ?? 100) } })).items.map(adaptClaim)],
  ["GET", /^\/claims\/([^/]+)$/, async (m) => adaptClaim(await backend<BackendClaim>(`/claims/${m[1]}`))],
  ["POST", /^\/claims$/, async (_m, _q, init) => {
    const accepted = await backend<any>("/claims", { method: "POST", body: init.body, tenant: init.tenantId });
    await waitForClaim(accepted.claim_id, init.tenantId);
    return adaptClaim(await backend<BackendClaim>(`/claims/${encodeURIComponent(accepted.claim_id)}`, { tenant: init.tenantId }));
  }],
  // Onboarding "test connection": one synthetic claim through the real pipeline for that tenant.
  ["POST", /^\/claims\/ingest$/, async (_m, _q, init) => {
    const id = `CLM-CONNTEST-${Date.now().toString(36).toUpperCase()}`;
    const start = performance.now();
    await backend("/claims", { method: "POST", body: buildTestClaim(id), tenant: init.tenantId });
    const status = await waitForClaim(id, init.tenantId);
    return { accepted: 1, claimId: id, risk: status.risk_score ?? 0, level: adaptLevel(null, status.risk_score), latencyMs: status.processing_time_ms ?? Math.round(performance.now() - start) };
  }],
  ["POST", /^\/claims\/batch$/, async (_m, _q, init) => backend("/claims/batch", { method: "POST", body: init.body, tenant: init.tenantId })],

  ["GET", /^\/coverage\/rules$/, async (_m, q) => adaptCoverageRules(await backend("/coverage/rules", { query: { authoritative: q.get("authoritative") } }))],
  ["GET", /^\/coverage\/compliance-report$/, async () => adaptComplianceReport(await backend("/coverage/compliance-report"))],

  ["GET", /^\/overlay\/([^/]+)$/, async (m) => {
    const id = decodeURIComponent(m[1]);
    const byProvider = await backend<{ items: BackendCaseSummary[] }>("/cases", { query: { provider_id: id, limit: 1 } });
    const caseId = byProvider.items[0]?.case_id ?? (id.startsWith("CS-") ? id : null);
    if (!caseId) return adaptOverlay(id, null);
    try {
      return adaptOverlay(id, await backend<BackendCaseDetail>(`/cases/${encodeURIComponent(caseId)}`));
    } catch {
      return adaptOverlay(id, null);
    }
  }],

  ["POST", /^\/demo\/reset$/, async () => {
    throw new ApiError("Demo data lives in the backend database and is not reset from here. To restore it, delete backend/claimshield.db and run: python -m scripts.seed_demo", 422);
  }],
];

export async function realApi<T>(path: string, init: Init = {}): Promise<T> {
  const [pathname, search = ""] = path.split("?");
  const method = init.method ?? "GET";
  for (const [m, pattern, handler] of ROUTES) {
    const match = m === method ? pathname.match(pattern) : null;
    if (match) return handler(match, new URLSearchParams(search), init) as Promise<T>;
  }
  throw new ApiError(`No backend mapping for ${method} ${pathname}.`, 404);
}
