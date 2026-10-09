"use client";

import { AlertTriangle } from "lucide-react";
import { useComplianceReport } from "@/lib/api";

/** Shown wherever coverage outcomes or coverage rules are displayed while any rule is illustrative. */
export function ComplianceBanner() {
  const { data } = useComplianceReport();
  if (!data || data.illustrative === 0) return null;
  return (
    <p role="note" className="mb-4 flex items-start gap-2 rounded-md border border-amber-500/60 bg-amber-500/10 p-3 text-sm">
      <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-800 dark:text-amber-200" aria-hidden />
      <span>
        <span className="font-medium">Coverage rules marked "illustrative" require compliance review before production use.</span>{" "}
        <span className="num">
          {data.illustrative} of {data.total}
        </span>{" "}
        coverage rules in use are illustrative; <span className="num">{data.loadedRules} of {data.expectedRules}</span> rules from {data.sourceDocument} are loaded.
      </span>
    </p>
  );
}
