import Image from "next/image";
import { cn } from "@/lib/utils";

export function LogoMark({ className }: { className?: string }) {
  return (
    <span className={cn("relative inline-flex size-12 shrink-0 overflow-hidden", className)} aria-hidden>
      <Image
        src="/claimshield-logo-white.png"
        alt=""
        fill
        sizes="(min-width: 1024px) 192px, 180px"
        className="object-contain"
      />
    </span>
  );
}

export function Logo({ className, compact, markClassName }: { className?: string; compact?: boolean; markClassName?: string }) {
  return (
    <span className={cn("flex items-center gap-2 font-semibold", className)}>
      <LogoMark className={markClassName} />
      {compact ? <span className="sr-only">ClaimShield</span> : <span className="whitespace-nowrap">ClaimShield</span>}
    </span>
  );
}
