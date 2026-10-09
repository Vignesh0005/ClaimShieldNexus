"use client";

import { useEffect, useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { MotionConfig } from "framer-motion";
import { useUser } from "@clerk/nextjs";
import { CLERK_ENABLED } from "@/lib/auth-config";
import { useAuthStore } from "@/stores";
import type { Role } from "@/lib/types";

const ROLES: Role[] = ["admin", "investigator", "analyst", "viewer"];

// Mirrors the Clerk session into the auth store. Role comes from the user's public metadata
// and defaults to the least-privileged role.
function ClerkBridge() {
  const { isLoaded, isSignedIn, user } = useUser();
  useEffect(() => {
    if (!isLoaded) return;
    if (!isSignedIn || !user) {
      useAuthStore.getState().signOut();
      return;
    }
    const claimed = user.publicMetadata?.role as Role | undefined;
    useAuthStore.getState().signIn(claimed && ROLES.includes(claimed) ? claimed : "viewer", {
      id: user.id.slice(-7).toUpperCase(),
      name: user.fullName ?? user.primaryEmailAddress?.emailAddress ?? "User",
      email: user.primaryEmailAddress?.emailAddress ?? "",
    });
  }, [isLoaded, isSignedIn, user]);
  return null;
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () => new QueryClient({ defaultOptions: { queries: { staleTime: 30_000, refetchOnWindowFocus: false, retry: 1 } } }),
  );
  return (
    <ThemeProvider attribute="class" defaultTheme="light" forcedTheme="light" enableSystem={false} disableTransitionOnChange>
      <QueryClientProvider client={client}>
        <MotionConfig reducedMotion="user">
          {CLERK_ENABLED ? <ClerkBridge /> : null}
          {children}
        </MotionConfig>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
