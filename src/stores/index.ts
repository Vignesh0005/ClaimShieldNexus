"use client";

import { useEffect, useState } from "react";
import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { InjectResult, RiskLevel, Role } from "@/lib/types";
import { can, type Permission } from "@/lib/permissions";

// ---------- auth ----------

interface AuthState {
  signedIn: boolean;
  user: { id: string; name: string; email: string } | null;
  role: Role;
  signIn: (role: Role, user?: { id: string; name: string; email: string }) => void;
  signOut: () => void;
  setRole: (role: Role) => void;
  can: (p: Permission) => boolean;
}

const DEMO_USERS: Record<Role, { id: string; name: string; email: string }> = {
  admin: { id: "ADM-002", name: "R. Alvarez", email: "admin@demo.claimshield.example" },
  investigator: { id: "AUD-007", name: "A. Sharma", email: "investigator@demo.claimshield.example" },
  analyst: { id: "ANL-014", name: "M. Petrov", email: "analyst@demo.claimshield.example" },
  viewer: { id: "VWR-021", name: "S. Doyle", email: "viewer@demo.claimshield.example" },
};

const idsOfDemo = Object.fromEntries(Object.values(DEMO_USERS).map((u) => [u.id, true]));

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      signedIn: false,
      user: null,
      role: "investigator",
      signIn: (role, user) => set({ signedIn: true, role, user: user ?? DEMO_USERS[role] }),
      signOut: () => set({ signedIn: false, user: null }),
      setRole: (role) => set((s) => ({ role, user: s.user && s.user.id in idsOfDemo ? DEMO_USERS[role] : s.user })),
      can: (p) => can(get().role, p),
    }),
    { name: "nexus-auth", partialize: (s) => ({ signedIn: s.signedIn, user: s.user, role: s.role }) },
  ),
);

// ---------- tenant ----------

export interface FieldMap {
  source: string;
  target: string;
  detection: "auto" | "manual";
}

export interface Thresholds {
  critical: number;
  high: number;
  medium: number;
  routing: number;
}

export interface OutputConfig {
  webhookUrl: string;
  scoreFormat: "0-1" | "0-100";
  delivery: "webhook" | "queue-only" | "sftp";
  includeBrief: boolean;
}

export interface TenantConfig {
  companyName: string;
  contactEmail: string;
  region: string;
  claimsPerMonth: string;
  apiKeyPreview: string | null;
  output: OutputConfig;
  onboardingStep: number;
}

export const DEFAULT_MAPPING: FieldMap[] = [
  { source: "clm_id", target: "claim_id", detection: "auto" },
  { source: "mbr_no", target: "member_id", detection: "auto" },
  { source: "prv_id", target: "provider_id", detection: "auto" },
  { source: "svc_dt", target: "service_date", detection: "auto" },
  { source: "cpt_cd", target: "procedure_code", detection: "manual" },
  { source: "icd_cd", target: "diagnosis_code", detection: "manual" },
  { source: "billed_amt", target: "billed_amount", detection: "auto" },
  { source: "paid_amt", target: "paid_amount", detection: "auto" },
];

interface TenantState {
  tenantId: string;
  config: TenantConfig;
  fieldMapping: FieldMap[];
  thresholds: Thresholds;
  setTenant: (id: string) => void;
  setConfig: (c: Partial<TenantConfig>) => void;
  setFieldMapping: (m: FieldMap[]) => void;
  setThresholds: (t: Partial<Thresholds>) => void;
}

const DEFAULT_CONFIG: TenantConfig = {
  companyName: "",
  contactEmail: "",
  region: "US East",
  claimsPerMonth: "",
  apiKeyPreview: null,
  output: { webhookUrl: "", scoreFormat: "0-1", delivery: "webhook", includeBrief: true },
  onboardingStep: 0,
};

export const useTenantStore = create<TenantState>()(
  persist(
    (set) => ({
      tenantId: "meridian",
      config: DEFAULT_CONFIG,
      fieldMapping: DEFAULT_MAPPING,
      thresholds: { critical: 0.8, high: 0.6, medium: 0.4, routing: 0.6 },
      setTenant: (tenantId) => set({ tenantId }),
      setConfig: (c) => set((s) => ({ config: { ...s.config, ...c } })),
      setFieldMapping: (fieldMapping) => set({ fieldMapping }),
      setThresholds: (t) => set((s) => ({ thresholds: { ...s.thresholds, ...t } })),
    }),
    { name: "nexus-tenant" },
  ),
);

// ---------- cases ----------

export type CaseSort = "priority" | "amount" | "harm" | "opened";

interface CaseState {
  selectedCaseId: string | null;
  severity: RiskLevel | "all";
  rule: string;
  status: string;
  search: string;
  sort: CaseSort;
  set: (p: Partial<Omit<CaseState, "set">>) => void;
}

export const useCaseStore = create<CaseState>()((set) => ({
  selectedCaseId: null,
  severity: "all",
  rule: "all",
  status: "all",
  search: "",
  sort: "priority",
  set: (p) => set(p),
}));

// ---------- queue ----------

interface QueueState {
  investigators: number;
  hours: number;
  checked: string[];
  setCapacity: (p: { investigators?: number; hours?: number }) => void;
  toggle: (id: string) => void;
  setChecked: (ids: string[]) => void;
}

export const useQueueStore = create<QueueState>()((set) => ({
  investigators: 3,
  hours: 20,
  checked: [],
  setCapacity: (p) => set(p),
  toggle: (id) => set((s) => ({ checked: s.checked.includes(id) ? s.checked.filter((x) => x !== id) : [...s.checked, id] })),
  setChecked: (checked) => set({ checked }),
}));

// ---------- global filters ----------

interface FilterState {
  severity: RiskLevel | "all";
  rule: string;
  set: (p: Partial<Omit<FilterState, "set">>) => void;
}

export const useFilterStore = create<FilterState>()((set) => ({
  severity: "all",
  rule: "all",
  set: (p) => set(p),
}));

// ---------- ui ----------

interface UIState {
  sidebarCollapsed: boolean;
  mobileNavOpen: boolean;
  tourStep: number | null;
  toggleSidebar: () => void;
  setMobileNav: (open: boolean) => void;
  setTourStep: (step: number | null) => void;
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      mobileNavOpen: false,
      tourStep: null,
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      setMobileNav: (mobileNavOpen) => set({ mobileNavOpen }),
      setTourStep: (tourStep) => set({ tourStep }),
    }),
    { name: "nexus-ui", partialize: (s) => ({ sidebarCollapsed: s.sidebarCollapsed }) },
  ),
);

// ---------- demo ----------

interface DemoState {
  demoMode: boolean;
  injecting: string | null;
  lastResult: InjectResult | null;
  history: InjectResult[];
  setInjecting: (scheme: string | null) => void;
  addResult: (r: InjectResult) => void;
  reset: () => void;
}

export const useDemoStore = create<DemoState>()((set) => ({
  demoMode: true,
  injecting: null,
  lastResult: null,
  history: [],
  setInjecting: (injecting) => set({ injecting }),
  addResult: (r) => set((s) => ({ lastResult: r, history: [r, ...s.history].slice(0, 8), injecting: null })),
  reset: () => set({ injecting: null, lastResult: null, history: [] }),
}));

export function useHydrated() {
  // Persisted stores rehydrate from localStorage after mount; gate role- and tenant-dependent UI on this.
  const [hydrated, setHydrated] = useState(false);
  useEffect(() => setHydrated(true), []);
  return hydrated;
}
