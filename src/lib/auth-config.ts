import type { Role } from "@/lib/types";

// Clerk is used when a publishable key is configured. Without one the app falls back to a
// local demo sign-in so it can run with no external accounts.
export const CLERK_ENABLED = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;

export const DEMO_LOGIN_ROLES: readonly Role[] = ["admin", "investigator"];
