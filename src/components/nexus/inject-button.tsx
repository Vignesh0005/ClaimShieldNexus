"use client";

import { ArrowUpNarrowWide, BarChart3, Copy, Fingerprint, Gauge, Ghost, Globe2, Accessibility, Repeat2, Rocket, Scissors, Split, Stethoscope, Tags, TrendingUp, UserX, Users, Loader2, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export interface Scheme {
  key: string;
  label: string;
  description: string;
  icon: LucideIcon;
}

export const SCHEMES: Scheme[] = [
  { key: "phantom", label: "Phantom billing", description: "Services billed with no matching encounter", icon: Ghost },
  { key: "duplicate", label: "Duplicate billing", description: "The same service submitted twice", icon: Copy },
  { key: "upcoding", label: "Upcoding", description: "Higher-level codes than the visit supports", icon: ArrowUpNarrowWide },
  { key: "unbundling", label: "Unbundling", description: "Bundled procedure split into parts", icon: Scissors },
  { key: "impossible_day", label: "Impossible day", description: "More than 24 hours billed in one day", icon: Globe2 },
  { key: "referral_ring", label: "Referral ring", description: "Providers referring in a closed loop", icon: Repeat2 },
  { key: "dme", label: "DME pattern", description: "Equipment billed with no prior visit", icon: Accessibility },
  { key: "identity", label: "Identity misuse", description: "One member ID used in distant places", icon: Fingerprint },
  { key: "units_cap", label: "Units above daily limit", description: "Far more units than one day allows", icon: Gauge },
  { key: "amount_outlier", label: "Unusually high amount", description: "A routine service billed at many times its usual amount", icon: TrendingUp },
  { key: "diagnosis_procedure_mismatch", label: "Diagnosis mismatch", description: "A procedure billed with a diagnosis it does not fit", icon: Stethoscope },
  { key: "demographic_mismatch", label: "Demographic mismatch", description: "A service that does not fit the member's gender", icon: UserX },
  { key: "peer_outlier", label: "Peer outlier", description: "Each member seen far more often than at peer providers", icon: BarChart3 },
  { key: "split_billing", label: "Split billing", description: "One service billed in parts on consecutive days", icon: Split },
  { key: "modifier_overuse", label: "Modifier overuse", description: "A distinct-service modifier on almost every line", icon: Tags },
  { key: "new_provider_burst", label: "New provider burst", description: "A new provider submitting a large volume of claims", icon: Rocket },
  { key: "provider_shopping", label: "Provider shopping", description: "One member, the same service, many providers", icon: Users },
];

export function InjectButton({ scheme, busy, disabled, onInject }: { scheme: Scheme; busy: boolean; disabled: boolean; onInject: (key: string) => void }) {
  const Icon = busy ? Loader2 : scheme.icon;
  return (
    <button
      type="button"
      disabled={disabled}
      aria-busy={busy}
      onClick={() => onInject(scheme.key)}
      className={cn(
        "flex h-full flex-col items-start gap-2 rounded-lg border bg-card p-4 text-left transition-colors hover:border-primary hover:bg-primary/5 disabled:cursor-not-allowed disabled:opacity-60",
        busy && "border-primary",
      )}
    >
      <Icon className={cn("size-5 text-link", busy && "animate-spin")} aria-hidden />
      <span className="text-sm font-semibold">{scheme.label}</span>
      <span className="text-xs text-muted-foreground">{scheme.description}</span>
    </button>
  );
}
