"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { SignIn } from "@clerk/nextjs";
import { CLERK_ENABLED, DEMO_LOGIN_ROLES } from "@/lib/auth-config";
import { ROLE_LABEL, ROLE_SUMMARY } from "@/lib/permissions";
import type { Role } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores";
import { Button } from "@/components/ui/button";
import { PublicHeader } from "@/components/shell/public-header";


function DemoSignIn() {
  const router = useRouter();
  const signIn = useAuthStore((s) => s.signIn);
  const [role, setRole] = useState<Role>("investigator");
  return (
    <form
      className="w-full max-w-md rounded-lg border bg-card p-6"
      onSubmit={(e) => {
        e.preventDefault();
        signIn(role);
        router.push("/dashboard");
      }}
    >
      <h1 className="text-xl font-semibold">Sign in to the demo workspace</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        No account is needed. Choose a role to see what each one can do. You can switch roles later from the account menu.
      </p>
      <div role="radiogroup" aria-label="Role" className="mt-5 space-y-2">
        {DEMO_LOGIN_ROLES.map((r) => (
          <button
            key={r}
            type="button"
            role="radio"
            aria-checked={role === r}
            onClick={() => setRole(r)}
            className={cn("block w-full rounded-md border p-3 text-left hover:bg-accent", role === r && "border-primary bg-primary/10 ring-1 ring-primary")}
          >
            <span className="block text-sm font-medium">{ROLE_LABEL[r]}</span>
            <span className="block text-xs text-muted-foreground">{ROLE_SUMMARY[r]}</span>
          </button>
        ))}
      </div>
      <Button type="submit" className="mt-5 w-full">
        Sign in as {ROLE_LABEL[role]}
      </Button>
      <p className="mt-3 text-xs text-muted-foreground">
        This sign-in is for demonstration only and does not protect data. Production sign-in uses Clerk once its keys are configured.
      </p>
    </form>
  );
}

export default function LoginPage() {
  return (
    <div className="min-h-dvh">
      <PublicHeader minimal />
      <main id="main" className="flex justify-center px-4 py-12">
        {CLERK_ENABLED ? <SignIn routing="path" path="/login" fallbackRedirectUrl="/dashboard" /> : <DemoSignIn />}
      </main>
    </div>
  );
}
