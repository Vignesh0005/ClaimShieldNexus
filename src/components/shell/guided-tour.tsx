"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { X } from "lucide-react";
import { useCases } from "@/lib/api";
import { useUIStore } from "@/stores";
import { Button } from "@/components/ui/button";

const STEPS = [
  { path: "/dashboard", title: "Start with the funnel", body: "Thousands of claims reduce to a short list of cases. Each stage shows how many items remain." },
  { path: "/queue", title: "Match the queue to your capacity", body: "Move the sliders to set investigator hours. The queue selects the highest-priority cases that fit." },
  { path: "CASE?tab=evidence", title: "Read the evidence", body: "Every flag shows what triggered it, where the data came from, and what the system does not know." },
  { path: "CASE?tab=decision", title: "A person decides", body: "Nothing is actioned automatically. The reviewer records a decision and it is written to the audit trail." },
  { path: "/demo/inject", title: "Inject a test scheme", body: "Send a synthetic claim pattern through the pipeline and see which detectors flag it." },
];

export function GuidedTour() {
  const router = useRouter();
  const pathname = usePathname();
  const step = useUIStore((s) => s.tourStep);
  const setStep = useUIStore((s) => s.setTourStep);
  const { data: cases } = useCases();
  const topCase = cases?.[0]?.id;

  const target = step === null ? null : STEPS[step].path.replace("CASE", topCase ? `/cases/${topCase}` : "/cases");

  useEffect(() => {
    if (target) router.push(target);
    // Only navigate when the step changes, not on every pathname update.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target]);

  if (step === null) return null;
  const s = STEPS[step];
  const last = step === STEPS.length - 1;
  return (
    <section
      aria-label="Guided tour"
      aria-live="polite"
      className="fixed bottom-4 right-4 z-40 w-[min(22rem,calc(100vw-2rem))] rounded-lg border border-primary/50 bg-popover p-4 text-popover-foreground shadow-xl"
    >
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs text-muted-foreground">
          Step {step + 1} of {STEPS.length}
          {pathname ? <span className="sr-only">, current page {pathname}</span> : null}
        </p>
        <button className="rounded-sm text-muted-foreground hover:text-foreground" aria-label="End tour" onClick={() => setStep(null)}>
          <X className="size-4" />
        </button>
      </div>
      <h2 className="mt-1 text-sm font-semibold">{s.title}</h2>
      <p className="mt-1 text-sm text-muted-foreground">{s.body}</p>
      <div className="mt-3 flex justify-between">
        <Button size="sm" variant="ghost" disabled={step === 0} onClick={() => setStep(step - 1)}>
          Back
        </Button>
        <Button size="sm" onClick={() => setStep(last ? null : step + 1)}>
          {last ? "End tour" : "Next step"}
        </Button>
      </div>
    </section>
  );
}
