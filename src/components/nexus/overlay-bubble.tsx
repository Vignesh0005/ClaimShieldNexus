"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import { api, logAudit } from "@/lib/api";
import type { OverlayInfo } from "@/lib/types";
import { useAuthStore } from "@/stores";
import { Button } from "@/components/ui/button";
import { LogoMark } from "@/components/shell/logo";
import { RiskBadge } from "./risk-badge";
import { score } from "@/lib/utils";

// In-page version of the browser-extension overlay (see /extension). Opens for whichever ID the
// reviewer picked in the host claims screen.
export function OverlayBubble({ entityId, onClose }: { entityId: string | null; onClose: () => void }) {
  const canAssign = useAuthStore((s) => s.can("case.assign"));
  const [sent, setSent] = useState<string | null>(null);
  const { data, isLoading, error } = useQuery({
    queryKey: ["overlay", entityId],
    queryFn: () => api<OverlayInfo>(`/overlay/${encodeURIComponent(entityId!)}`),
    enabled: !!entityId,
  });

  return (
    <AnimatePresence>
      {entityId ? (
        <motion.aside
          key={entityId}
          role="dialog"
          aria-label={`ClaimShield summary for ${entityId}`}
          initial={{ opacity: 0, y: 8, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 8 }}
          transition={{ duration: 0.16 }}
          className="absolute bottom-4 right-4 z-10 w-[min(20rem,calc(100%-2rem))] rounded-lg border border-electric/60 bg-navy p-4 text-slate-100 shadow-2xl"
        >
          <header className="flex items-center justify-between border-b border-white/15 pb-2">
            <span className="flex items-center gap-2 text-sm font-semibold">
              <LogoMark className="size-5" /> ClaimShield
            </span>
            <button onClick={onClose} aria-label="Close summary" className="rounded-sm text-slate-300 ring-offset-navy hover:text-white">
              <X className="size-4" />
            </button>
          </header>
          <p className="id mt-3 text-base font-semibold">{entityId}</p>
          {isLoading ? <p className="mt-2 text-sm text-slate-300">Looking up this ID</p> : null}
          {error ? <p className="mt-2 text-sm text-slate-300">Could not load a summary for this ID. Check your connection and select it again.</p> : null}
          {data ? (
            <div className="dark">
              <p className="mt-2 flex items-center gap-2 text-sm">
                Risk <RiskBadge score={data.risk} level={data.level} />
              </p>
              {data.reasons.length ? (
                <>
                  <p className="mt-3 text-xs text-slate-300">Top reasons</p>
                  <ol className="mt-1 list-decimal space-y-0.5 pl-5 text-sm">
                    {data.reasons.map((r) => (
                      <li key={r.label}>
                        {r.label} <span className="num text-slate-300">({score(r.score)})</span>
                      </li>
                    ))}
                  </ol>
                </>
              ) : (
                <p className="mt-3 text-sm text-slate-300">No open case references this ID.</p>
              )}
              {data.caseId ? (
                <div className="mt-4 flex flex-wrap gap-2">
                  <Button asChild size="sm">
                    <Link href={`/cases/${data.caseId}`}>View full case</Link>
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="border-white/30 bg-transparent text-white hover:bg-white/10"
                    disabled={!canAssign || sent === data.caseId}
                    onClick={() => {
                      logAudit("Sent to SIU queue from overlay", data.caseId!, entityId);
                      setSent(data.caseId);
                    }}
                  >
                    {sent === data.caseId ? "Sent to SIU" : "Send to SIU"}
                  </Button>
                </div>
              ) : null}
              <p className="mt-3 text-2xs text-slate-400">A score is a prompt for review, not a finding.</p>
            </div>
          ) : null}
        </motion.aside>
      ) : null}
    </AnimatePresence>
  );
}
