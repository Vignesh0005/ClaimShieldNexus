import type { Role } from "./types";

export type Permission =
  | "case.decide"
  | "case.assign"
  | "feedback.submit"
  | "export"
  | "settings.edit"
  | "users.manage"
  | "admin.view"
  | "demo.inject";

export const ROLE_LABEL: Record<Role, string> = {
  admin: "Admin",
  investigator: "SIU Investigator",
  analyst: "Analyst",
  viewer: "Viewer",
};

export const ROLE_SUMMARY: Record<Role, string> = {
  admin: "Full access, including tenants, users and system health.",
  investigator: "Reviews cases, records decisions and gives feedback.",
  analyst: "Explores cases and analytics, exports data. Cannot record decisions.",
  viewer: "Read-only access to cases and analytics.",
};

const GRANTS: Record<Role, Permission[]> = {
  admin: ["case.decide", "case.assign", "feedback.submit", "export", "settings.edit", "users.manage", "admin.view", "demo.inject"],
  investigator: ["case.decide", "case.assign", "feedback.submit", "export", "demo.inject"],
  analyst: ["feedback.submit", "export", "demo.inject"],
  viewer: [],
};

export function can(role: Role, permission: Permission) {
  return GRANTS[role].includes(permission);
}
