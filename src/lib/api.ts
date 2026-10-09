"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuthStore, useTenantStore } from "@/stores";
import { USE_MOCK } from "./api/client";
import { realApi } from "./api/routes";
import type {
  AnalyticsData,
  AuditEvent,
  Brief,
  CaseDetail,
  CaseSummary,
  ComplianceReport,
  Counterfactual,
  CoverageRules,
  Decision,
  EvidenceResponse,
  FeedbackEntry,
  FunnelData,
  GeoEvent,
  HealthData,
  InjectResult,
  LineDecision,
  LogEntry,
  ModelCard,
  NetworkData,
  QueueData,
  Tenant,
  TimelineEvent,
} from "./types";

/**
 * Single entry point for data. By default every call goes to the FastAPI backend through the
 * adapter layer (src/lib/api/routes.ts). Set NEXT_PUBLIC_USE_MOCK=true to use the bundled mock.
 */
export async function api<T>(path: string, init?: { method?: "GET" | "POST"; body?: unknown; tenantId?: string }): Promise<T> {
  if (!USE_MOCK) return realApi<T>(path, init);
  const tenantId = init?.tenantId ?? useTenantStore.getState().tenantId;
  const res = await fetch(`/api/v1${path}`, {
    method: init?.method ?? "GET",
    headers: { "content-type": "application/json", "x-tenant-id": tenantId },
    body: init?.body === undefined ? undefined : JSON.stringify(init.body),
  });
  if (!res.ok) {
    let message = `Request failed (${res.status}).`;
    try {
      message = (await res.json()).error ?? message;
    } catch {}
    throw new Error(message);
  }
  return res.json() as Promise<T>;
}

const actor = () => useAuthStore.getState().user?.id ?? "unknown";
const useTenantId = () => useTenantStore((s) => s.tenantId);

export function useTenants() {
  const tenantId = useTenantId();
  const role = useAuthStore((s) => s.role);
  const userId = useAuthStore((s) => s.user?.id);
  return useQuery({ queryKey: ["tenants", tenantId, userId, role], queryFn: () => api<Tenant[]>("/tenants") });
}

export function useFunnel() {
  const tenantId = useTenantId();
  return useQuery({ queryKey: ["funnel", tenantId], queryFn: () => api<FunnelData>("/funnel") });
}

export function useQueue(capacity: { investigators: number; hours: number }) {
  const tenantId = useTenantId();
  return useQuery({
    queryKey: ["queue", tenantId, capacity],
    queryFn: () => api<QueueData>(`/queue?investigators=${capacity.investigators}&hours=${capacity.hours}`),
    placeholderData: (prev) => prev,
  });
}

export function useCases() {
  const tenantId = useTenantId();
  return useQuery({ queryKey: ["claims", tenantId, "cases"], queryFn: () => api<CaseSummary[]>("/cases") });
}

export function useCase(caseId: string) {
  const tenantId = useTenantId();
  return useQuery({ queryKey: ["case", caseId, tenantId], queryFn: () => api<CaseDetail>(`/cases/${caseId}`), retry: false });
}

export function useEvidence(caseId: string) {
  return useQuery({ queryKey: ["case", caseId, "evidence"], queryFn: () => api<EvidenceResponse>(`/cases/${caseId}/evidence`) });
}

export function useNetwork(caseId: string | null) {
  const tenantId = useTenantId();
  return useQuery({
    queryKey: ["network", caseId ?? `global-${tenantId}`, "2024-01/2025-01"],
    queryFn: () => api<NetworkData>(caseId ? `/cases/${caseId}/network` : "/network"),
  });
}

export function useTimeline(caseId: string) {
  return useQuery({ queryKey: ["case", caseId, "timeline"], queryFn: () => api<TimelineEvent[]>(`/cases/${caseId}/timeline`) });
}

export function useBrief(caseId: string, type: "technical" | "plain", enhance = false) {
  return useQuery({
    queryKey: ["brief", caseId, type, enhance],
    queryFn: () => api<Brief>(`/cases/${caseId}/brief`, { method: "POST", body: { type, enhance } }),
  });
}

export function useCoverageRules() {
  const tenantId = useTenantId();
  return useQuery({ queryKey: ["coverage-rules", tenantId], queryFn: () => api<CoverageRules>("/coverage/rules") });
}

export function useComplianceReport() {
  const tenantId = useTenantId();
  return useQuery({ queryKey: ["compliance-report", tenantId], queryFn: () => api<ComplianceReport>("/coverage/compliance-report") });
}

export function useCounterfactual(caseId: string) {
  return useQuery({ queryKey: ["case", caseId, "counterfactual"], queryFn: () => api<Counterfactual>(`/cases/${caseId}/counterfactual`) });
}

export function useAudit(caseId?: string) {
  const tenantId = useTenantId();
  return useQuery({
    queryKey: ["audit", caseId ?? `all-${tenantId}`],
    queryFn: () => api<AuditEvent[]>(caseId ? `/audit/${caseId}` : "/audit"),
  });
}

export function useFeedback() {
  const tenantId = useTenantId();
  return useQuery({ queryKey: ["feedback", tenantId], queryFn: () => api<FeedbackEntry[]>("/feedback") });
}

export function useModels() {
  const tenantId = useTenantId();
  return useQuery({ queryKey: ["models", tenantId], queryFn: () => api<ModelCard>("/models") });
}

export function useHealth() {
  return useQuery({ queryKey: ["health"], queryFn: () => api<HealthData>("/health"), refetchInterval: 30_000 });
}

export function useGeo() {
  const tenantId = useTenantId();
  return useQuery({ queryKey: ["geo", tenantId], queryFn: () => api<GeoEvent[]>("/geo") });
}

export function useAnalytics() {
  const tenantId = useTenantId();
  return useQuery({ queryKey: ["analytics", tenantId], queryFn: () => api<AnalyticsData>("/analytics") });
}

export function useLogs() {
  return useQuery({ queryKey: ["logs"], queryFn: () => api<LogEntry[]>("/admin/logs") });
}

// ---------- mutations ----------

export function logAudit(action: string, caseId?: string, detail?: string) {
  return api("/audit", { method: "POST", body: { action, caseId, detail, actor: actor() } }).catch(() => undefined);
}

function useInvalidateCase() {
  const qc = useQueryClient();
  return (caseId?: string) => {
    if (caseId) {
      qc.invalidateQueries({ queryKey: ["case", caseId] });
      qc.invalidateQueries({ queryKey: ["audit"] });
    }
    for (const key of ["queue", "claims", "funnel", "analytics", "feedback", "audit", "network", "geo"]) {
      qc.invalidateQueries({ queryKey: [key] });
    }
  };
}

export interface DecisionInput {
  decision: Decision;
  lines: Record<string, LineDecision>;
  notes: string;
  nextAction: string;
  assignee?: string;
}

export function useSubmitDecision(caseId: string) {
  const invalidate = useInvalidateCase();
  return useMutation({
    mutationFn: (input: DecisionInput) => api(`/cases/${caseId}/decision`, { method: "POST", body: { ...input, actor: actor() } }),
    onSuccess: () => invalidate(caseId),
  });
}

export function useAssignCase(caseId: string) {
  const invalidate = useInvalidateCase();
  return useMutation({
    mutationFn: (input: { assignee?: string; status?: string }) =>
      api<CaseDetail>(`/cases/${caseId}/assign`, { method: "POST", body: { ...input, actor: actor() } }),
    onSuccess: () => invalidate(caseId),
  });
}

export function useInject() {
  const invalidate = useInvalidateCase();
  return useMutation({
    mutationFn: (scheme: string) => api<InjectResult>("/inject", { method: "POST", body: { scheme, actor: actor() } }),
    onSuccess: () => invalidate(),
  });
}

export function useSubmitFeedback() {
  const invalidate = useInvalidateCase();
  return useMutation({
    mutationFn: (input: { caseId: string; useful: boolean; reasons: string[]; comment: string }) =>
      api<FeedbackEntry>("/feedback", { method: "POST", body: { ...input, actor: actor() } }),
    onSuccess: () => invalidate(),
  });
}

export function useResetDemo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api("/demo/reset", { method: "POST", body: {} }),
    onSuccess: () => qc.invalidateQueries(),
  });
}
