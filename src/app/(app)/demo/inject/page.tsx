"use client";

import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import { useInject, useResetDemo } from "@/lib/api";
import { useAuthStore, useDemoStore } from "@/stores";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/state";
import { InjectButton, SCHEMES } from "@/components/nexus/inject-button";
import { SignalTag } from "@/components/nexus/risk-badge";
import { score } from "@/lib/utils";

export default function InjectPage() {
  const inject = useInject();
  const reset = useResetDemo();
  const canInject = useAuthStore((s) => s.can("demo.inject"));
  const { injecting, lastResult, history, setInjecting, addResult, reset: resetStore } = useDemoStore();

  const run = (key: string) => {
    setInjecting(key);
    inject.mutate(key, { onSuccess: addResult, onError: () => setInjecting(null) });
  };

  const label = (key: string) => SCHEMES.find((s) => s.key === key)?.label ?? key;

  return (
    <>
      <PageHeader
        title="Inject a test scheme"
        description="Choose a billing pattern. A synthetic claim set is sent through the live pipeline, and the result shows which detectors flagged it and how long that took."
        actions={
          <Button
            variant="outline"
            size="sm"
            disabled={reset.isPending}
            onClick={() => reset.mutate(undefined, { onSuccess: resetStore })}
          >
            {reset.isPending ? "Resetting demo data" : "Reset demo data"}
          </Button>
        }
      />
      {!canInject ? <p className="mb-4 rounded-md border border-dashed p-3 text-sm">Your role cannot inject test schemes. Switch to an Analyst, SIU Investigator or Admin role from the account menu.</p> : null}

      <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {SCHEMES.map((s) => (
          <li key={s.key}>
            <InjectButton scheme={s} busy={injecting === s.key} disabled={!canInject || injecting !== null} onInject={run} />
          </li>
        ))}
      </ul>

      <div aria-live="polite" className="mt-5">
        {inject.isError ? (
          <p role="alert" className="rounded-md border border-red-600/40 bg-red-600/5 p-3 text-sm">
            The test scheme was not injected: {(inject.error as Error).message} Try again.
          </p>
        ) : null}
        <AnimatePresence mode="wait">
          {lastResult ? (
            <motion.div key={lastResult.claimId} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>
              <Card className="border-emerald-500/50 p-5">
                <h2 className="text-lg font-semibold">
                  Flagged in <span className="num">{lastResult.latencyMs} ms</span>
                </h2>
                <dl className="mt-3 grid gap-x-8 gap-y-1 text-sm sm:grid-cols-[8rem_1fr]">
                  <dt className="text-muted-foreground">Scheme</dt>
                  <dd>{label(lastResult.scheme)}</dd>
                  <dt className="text-muted-foreground">Claim</dt>
                  <dd className="id">{lastResult.claimId}</dd>
                  <dt className="text-muted-foreground">Flagged by</dt>
                  <dd className="flex flex-wrap gap-1.5">
                    {lastResult.caughtBy.map((k) => (
                      <SignalTag key={k} kind={k} />
                    ))}
                  </dd>
                  <dt className="text-muted-foreground">Flags</dt>
                  <dd className="num">{lastResult.flags.length}</dd>
                </dl>
                <ul className="mt-4 divide-y rounded-md border text-sm">
                  {lastResult.flags.map((f) => (
                    <li key={f.id} className="flex items-center justify-between gap-3 px-3 py-2">
                      <span className="flex items-center gap-2">
                        <SignalTag kind={f.kind} />
                        <span className="font-mono text-xs">{f.name}</span>
                      </span>
                      <span>
                        <span className="text-muted-foreground">{f.kind === "rule" ? "confidence" : "score"} </span>
                        <span className="num font-semibold">{score(f.score)}</span>
                      </span>
                    </li>
                  ))}
                </ul>
                <div className="mt-4 flex flex-wrap items-center gap-3">
                  {lastResult.caseId ? (
                    <>
                      <Button asChild>
                        <Link href={`/cases/${lastResult.caseId}`}>View case {lastResult.caseId}</Link>
                      </Button>
                      <p className="text-xs text-muted-foreground">The case now waits in the queue for a reviewer. Nothing else happens until a person records a decision.</p>
                    </>
                  ) : (
                    <p className="text-sm text-muted-foreground">The claim was flagged but stayed below this tenant's case-opening rules, so no case was opened.</p>
                  )}
                </div>
              </Card>
            </motion.div>
          ) : (
            <Card className="border-dashed p-6 text-sm text-muted-foreground">Results appear here after you choose a scheme.</Card>
          )}
        </AnimatePresence>
      </div>

      {history.length > 1 ? (
        <section className="mt-6">
          <h2 className="text-sm font-semibold">Earlier in this session</h2>
          <ul className="mt-2 divide-y rounded-md border text-sm">
            {history.slice(1).map((h) => (
              <li key={h.claimId} className="flex flex-wrap items-center justify-between gap-3 px-3 py-2">
                <span>{label(h.scheme)}</span>
                <span className="num text-muted-foreground">{h.latencyMs} ms</span>
                {h.caseId ? (
                  <Link href={`/cases/${h.caseId}`} className="id text-link underline-offset-4 hover:underline">
                    {h.caseId}
                  </Link>
                ) : (
                  <span className="text-muted-foreground">No case opened</span>
                )}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </>
  );
}
