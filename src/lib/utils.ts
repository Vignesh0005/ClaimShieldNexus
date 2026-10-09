import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import type { CaseStatus, HarmLevel, RiskLevel } from "./types";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export const DISCLAIMER = "Synthetic demo. Not a fraud determination.";

export function riskLevel(score: number): RiskLevel {
  if (score >= 0.8) return "critical";
  if (score >= 0.6) return "high";
  if (score >= 0.4) return "medium";
  return "low";
}

export function harmLevel(score: number): HarmLevel {
  if (score >= 0.7) return "High";
  if (score >= 0.5) return "Med";
  return "Low";
}

export const RISK_LABEL: Record<RiskLevel, string> = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  low: "Low",
};

export const RISK_HEX: Record<RiskLevel, string> = {
  critical: "#DC2626",
  high: "#EA580C",
  medium: "#F59E0B",
  low: "#10B981",
};

export const STATUS_LABEL: Record<CaseStatus, string> = {
  pending_review: "Pending review",
  in_review: "In review",
  needs_info: "Needs more information",
  confirmed: "Confirmed for referral",
  false_positive: "Closed as false positive",
  escalated: "Escalated",
};

export function inr(n: number) {
  return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(n);
}

export function inrCompact(n: number) {
  const abs = Math.abs(n);
  const short = (value: number) => new Intl.NumberFormat("en-IN", { maximumFractionDigits: 1 }).format(value);
  if (abs >= 1_00_00_000) return `₹${short(n / 1_00_00_000)} crore`;
  if (abs >= 1_00_000) return `₹${short(n / 1_00_000)} lakh`;
  if (abs >= 1_000) return `₹${short(n / 1_000)} thousand`;
  return inr(n);
}

export function num(n: number) {
  return new Intl.NumberFormat("en-IN").format(n);
}

/** A 0 to 1 score as a whole percentage, the way every score is shown in the UI. */
export function score(n: number) {
  return `${Math.round(n * 100)}%`;
}

export function timeAgo(iso: string) {
  const s = Math.max(1, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  if (s < 60) return "just now";
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} hour${h === 1 ? "" : "s"} ago`;
  const d = Math.round(h / 24);
  return `${d} day${d === 1 ? "" : "s"} ago`;
}

export function dateTime(iso: string) {
  const d = new Date(iso);
  const p = (x: number) => String(x).padStart(2, "0");
  return `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())}`;
}

export function downloadText(filename: string, text: string, type = "text/csv") {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function toCsv(rows: Record<string, string | number>[]) {
  if (!rows.length) return "";
  const keys = Object.keys(rows[0]);
  const esc = (v: string | number) => `"${String(v).replace(/"/g, '""')}"`;
  return [keys.join(","), ...rows.map((r) => keys.map((k) => esc(r[k])).join(","))].join("\n");
}
