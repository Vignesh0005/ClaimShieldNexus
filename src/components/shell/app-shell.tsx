"use client";

import { useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import * as Dialog from "@radix-ui/react-dialog";
import { UserButton } from "@clerk/nextjs";
import {
  Activity,
  BarChart3,
  FileText,
  Bell,
  Building2,
  FlaskConical,
  FolderSearch,
  LayoutDashboard,
  ListOrdered,
  LogOut,
  MapPinned,
  Menu,
  MessageSquareText,
  PanelLeft,
  RotateCcw,
  Route,
  Scale,
  ScrollText,
  Settings,
  Share2,
  Terminal,
  UserRound,
  type LucideIcon,
} from "lucide-react";
import { CLERK_ENABLED, DEMO_LOGIN_ROLES } from "@/lib/auth-config";
import { useFunnel, useResetDemo, useTenants } from "@/lib/api";
import { ROLE_LABEL } from "@/lib/permissions";
import type { Role } from "@/lib/types";
import { cn, timeAgo } from "@/lib/utils";
import { useAuthStore, useDemoStore, useHydrated, useQueueStore, useTenantStore, useUIStore } from "@/stores";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/state";
import { GuidedTour } from "./guided-tour";
import { Logo } from "./logo";

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
}

const NAV: { group: string; adminOnly?: boolean; items: NavItem[] }[] = [
  {
    group: "Investigate",
    items: [
      { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
      { href: "/queue", label: "SIU queue", icon: ListOrdered },
      { href: "/cases", label: "Cases", icon: FolderSearch },
      { href: "/claims", label: "Claims", icon: FileText },
      { href: "/network", label: "Network", icon: Share2 },
      { href: "/map", label: "Geography", icon: MapPinned },
    ],
  },
  {
    group: "Oversight",
    items: [
      { href: "/analytics", label: "Analytics", icon: BarChart3 },
      { href: "/audit", label: "Audit trail", icon: ScrollText },
      { href: "/feedback", label: "Feedback", icon: MessageSquareText },
      { href: "/models", label: "Models", icon: Scale },
    ],
  },
  { group: "Configure", items: [{ href: "/settings", label: "Settings", icon: Settings }] },
  {
    group: "Admin",
    adminOnly: true,
    items: [
      { href: "/admin/tenants", label: "Tenants", icon: Building2 },
      { href: "/admin/health", label: "System health", icon: Activity },
      { href: "/admin/logs", label: "System logs", icon: Terminal },
    ],
  },
  {
    group: "Demo",
    items: [
      { href: "/demo/inject", label: "Inject a test scheme", icon: FlaskConical },
    ],
  },
];

function NavList({ role, expanded, onNavigate }: { role: Role; expanded: "always" | "lg" | "never"; onNavigate?: () => void }) {
  const pathname = usePathname();
  const labelClass = expanded === "always" ? "" : expanded === "lg" ? "hidden lg:inline" : "hidden";
  const groupClass = expanded === "always" ? "" : expanded === "lg" ? "hidden lg:block" : "hidden";
  return (
    <nav aria-label="Main" className="flex-1 overflow-y-auto px-2 py-3">
      {NAV.filter((g) => !g.adminOnly || role === "admin").map((g, i) => (
        <div key={g.group} className={cn(i > 0 && "mt-3 border-t border-white/15 pt-3")}>
          <p className={cn("px-2 pb-1 text-xs text-sidebar-muted", groupClass)}>{g.group}</p>
          <ul className="space-y-0.5">
            {g.items.map((item) => {
              const active = pathname === item.href || pathname.startsWith(item.href + "/");
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    onClick={onNavigate}
                    title={item.label}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "flex h-9 items-center gap-3 rounded-md px-2.5 text-sm text-sidebar-foreground/90 ring-offset-sidebar transition-colors hover:bg-white/10",
                      active && "bg-white/20 font-semibold text-white shadow-sm ring-1 ring-inset ring-white/20 hover:bg-white/25",
                    )}
                  >
                    <item.icon className="size-4 shrink-0" aria-hidden />
                    <span className={cn("truncate", labelClass)}>{item.label}</span>
                    {labelClass ? <span className={cn("sr-only", expanded === "lg" && "lg:hidden")}>{item.label}</span> : null}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

function TenantSwitcher() {
  const { data } = useTenants();
  const tenantId = useTenantStore((s) => s.tenantId);
  const setTenant = useTenantStore((s) => s.setTenant);
  const options = (data ?? [{ id: tenantId, name: tenantId }]).map((t) => ({ value: t.id, label: t.name }));
  if (!options.some((o) => o.value === tenantId)) options.push({ value: tenantId, label: tenantId });
  return <Select label="Tenant" value={tenantId} onValueChange={setTenant} options={options} className="w-40 sm:w-52" />;
}

function AlertsMenu() {
  const { data } = useFunnel();
  const items = data?.activity ?? [];
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label={`Recent activity, ${items.length} items`}>
          <Bell />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-80">
        <DropdownMenuLabel>Recent activity</DropdownMenuLabel>
        {items.length === 0 ? <p className="px-2 py-3 text-sm text-muted-foreground">Nothing new for this tenant.</p> : null}
        {items.map((a) => (
          <DropdownMenuItem key={a.id} className="flex-col items-start gap-0.5">
            <span>{a.text}</span>
            <span className="text-xs text-muted-foreground">{timeAgo(a.ts)}</span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function UserMenu() {
  const router = useRouter();
  const { user, role, setRole, signOut } = useAuthStore();
  const setTourStep = useUIStore((s) => s.setTourStep);
  const reset = useResetDemo();
  const resetDemo = () =>
    reset.mutate(undefined, {
      onSuccess: () => {
        useDemoStore.getState().reset();
        useQueueStore.getState().setCapacity({ investigators: 3, hours: 20 });
        useQueueStore.getState().setChecked([]);
      },
    });
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" className="gap-2 px-2.5" aria-label={`Account menu for ${user?.name ?? "user"}, ${ROLE_LABEL[role]}`}>
          <UserRound />
          <span className="hidden text-left leading-tight md:block">
            <span className="block text-xs font-medium">{user?.name}</span>
            <span className="block text-2xs text-muted-foreground">{ROLE_LABEL[role]}</span>
          </span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent>
        <DropdownMenuLabel>
          Signed in as <span className="id">{user?.id}</span>
        </DropdownMenuLabel>
        {!CLERK_ENABLED ? (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuLabel>View as role (demo sign-in)</DropdownMenuLabel>
            {DEMO_LOGIN_ROLES.map((r) => (
              <DropdownMenuItem key={r} onSelect={() => setRole(r)} aria-current={r === role}>
                <span className={cn("size-1.5 rounded-full", r === role ? "bg-primary" : "bg-transparent")} aria-hidden />
                {ROLE_LABEL[r]}
              </DropdownMenuItem>
            ))}
          </>
        ) : null}
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => setTourStep(0)}>
          <Route /> Start guided tour
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={resetDemo}>
          <RotateCcw /> Reset demo data
        </DropdownMenuItem>
        {!CLERK_ENABLED ? (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onSelect={() => {
                signOut();
                router.push("/login");
              }}
            >
              <LogOut /> Sign out
            </DropdownMenuItem>
          </>
        ) : null}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const hydrated = useHydrated();
  const { signedIn, role } = useAuthStore();
  const { sidebarCollapsed, toggleSidebar, mobileNavOpen, setMobileNav } = useUIStore();

  useEffect(() => {
    if (hydrated && !CLERK_ENABLED && (!signedIn || !DEMO_LOGIN_ROLES.includes(role))) {
      if (signedIn) useAuthStore.getState().signOut();
      router.replace("/login");
    }
  }, [hydrated, signedIn, role, router]);

  if (!hydrated || !signedIn || (!CLERK_ENABLED && !DEMO_LOGIN_ROLES.includes(role))) {
    return (
      <div className="p-6" role="status">
        <span className="sr-only">Loading workspace</span>
        <Skeleton className="mb-4 h-10 w-64" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  return (
    <div className="flex h-dvh">
      <aside className={cn("sidebar-surface hidden shrink-0 flex-col bg-sidebar text-sidebar-foreground sm:flex sm:w-14", sidebarCollapsed ? "lg:w-14" : "lg:w-56")}>
        <Link href="/dashboard" className="flex h-16 items-center px-3.5 text-sidebar-foreground ring-offset-sidebar">
          <Logo compact className={cn("lg:hidden", sidebarCollapsed && "lg:flex")} />
          <Logo compact markClassName="h-14 w-48" className={cn("hidden", !sidebarCollapsed && "lg:flex")} />
        </Link>
        <NavList role={role} expanded={sidebarCollapsed ? "never" : "lg"} />
      </aside>

      <Dialog.Root open={mobileNavOpen} onOpenChange={setMobileNav}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60" />
          <Dialog.Content className="fixed inset-y-0 left-0 z-50 flex w-64 flex-col sidebar-surface bg-sidebar text-sidebar-foreground">
            <Dialog.Title className="flex h-16 items-center px-3.5 text-sm text-sidebar-foreground">
              <Logo compact markClassName="h-14 w-48" />
            </Dialog.Title>
            <Dialog.Description className="sr-only">Main navigation</Dialog.Description>
            <NavList role={role} expanded="always" onNavigate={() => setMobileNav(false)} />
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="glass-header relative z-30 flex h-16 shrink-0 items-center gap-2 border-b px-3 sm:px-6">
          <Button variant="ghost" size="icon" className="sm:hidden" aria-label="Open navigation" onClick={() => setMobileNav(true)}>
            <Menu />
          </Button>
          <Button variant="ghost" size="icon" className="hidden lg:inline-flex" aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"} aria-pressed={!sidebarCollapsed} onClick={toggleSidebar}>
            <PanelLeft />
          </Button>
          <div className="flex-1" />
          <TenantSwitcher />
          <AlertsMenu />
          <UserMenu />
          {CLERK_ENABLED ? <UserButton /> : null}
        </header>
        <main id="main" tabIndex={-1} className="workspace-canvas min-h-0 flex-1 overflow-y-auto p-4 outline-none sm:p-7">
          <div className="mx-auto max-w-[1680px]">{children}</div>
        </main>
      </div>
      <GuidedTour />
    </div>
  );
}

export function RoleGate({ allow, children }: { allow: Role[]; children: React.ReactNode }) {
  const role = useAuthStore((s) => s.role);
  if (allow.includes(role)) return <>{children}</>;
  return (
    <div className="rounded-lg border border-dashed p-8 text-sm">
      <p className="font-medium">This page is limited to {allow.map((r) => ROLE_LABEL[r]).join(" and ")} roles</p>
      <p className="mt-1 text-muted-foreground">
        You are signed in as {ROLE_LABEL[role]}. Ask a tenant admin to change your role if you need access.
      </p>
    </div>
  );
}
