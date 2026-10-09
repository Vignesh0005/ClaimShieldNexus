"use client";

import { useState } from "react";
import Link from "next/link";
import { useCases, useFeedback, useSubmitFeedback } from "@/lib/api";
import { cn, dateTime } from "@/lib/utils";
import { useAuthStore } from "@/stores";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Field, Textarea } from "@/components/ui/form";
import { Select } from "@/components/ui/select";
import { Empty, ErrorState, Loading, PageHeader } from "@/components/ui/state";
import { StatusPill } from "@/components/nexus/risk-badge";

const REASONS_USEFUL = ["Evidence was clear", "Priority was right", "Brief saved time", "Network context helped"];
const REASONS_NOT = ["Legitimate billing pattern", "Evidence was weak", "Duplicate of an existing case", "Peer group was wrong", "Score seemed too high"];

export default function FeedbackPage() {
  const cases = useCases();
  const feedback = useFeedback();
  const submit = useSubmitFeedback();
  const canSubmit = useAuthStore((s) => s.can("feedback.submit"));
  const [caseId, setCaseId] = useState("");
  const [useful, setUseful] = useState<boolean | null>(null);
  const [reasons, setReasons] = useState<string[]>([]);
  const [comment, setComment] = useState("");
  const [done, setDone] = useState("");

  const options = useful === false ? REASONS_NOT : REASONS_USEFUL;
  const entries = feedback.data ?? [];
  const usefulCount = entries.filter((e) => e.useful).length;

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!caseId || useful === null) return;
    submit.mutate(
      { caseId, useful, reasons, comment: comment.trim() },
      {
        onSuccess: () => {
          setDone(`Feedback on ${caseId} submitted. It will be included in the next model review.`);
          setCaseId("");
          setUseful(null);
          setReasons([]);
          setComment("");
        },
      },
    );
  };

  return (
    <>
      <PageHeader
        title="Investigator feedback"
        description="Tell the system whether a flagged case was worth reviewing. Feedback is reviewed by a person before it is used to retrain or recalibrate the model."
      />
      <div className="grid gap-4 lg:grid-cols-[minmax(0,26rem)_1fr]">
        <Card className="h-fit p-4 sm:p-5">
          <h2 className="text-base font-semibold">Give feedback on a case</h2>
          {!canSubmit ? <p className="mt-2 rounded-md border border-dashed p-3 text-sm">Your role can read feedback but cannot submit it.</p> : null}
          <form onSubmit={onSubmit} className="mt-4 space-y-4">
            <fieldset disabled={!canSubmit || submit.isPending} className="space-y-4 disabled:opacity-60">
              <Field label="Case" htmlFor="fb-case">
                <Select
                  id="fb-case"
                  label="Case"
                  value={caseId}
                  onValueChange={setCaseId}
                  placeholder={cases.isLoading ? "Loading cases" : "Choose a case"}
                  options={(cases.data ?? []).map((c) => ({ value: c.id, label: `${c.id} (${c.providerId}, ${c.rule})` }))}
                />
              </Field>
              <div>
                <p className="text-sm font-medium" id="fb-useful">
                  Was this case worth reviewing?
                </p>
                <div role="radiogroup" aria-labelledby="fb-useful" className="mt-1.5 inline-flex overflow-hidden rounded-md border">
                  {[
                    [true, "Yes, useful"],
                    [false, "No, not useful"],
                  ].map(([v, label]) => (
                    <button
                      key={String(v)}
                      type="button"
                      role="radio"
                      aria-checked={useful === v}
                      onClick={() => {
                        setUseful(v as boolean);
                        setReasons([]);
                      }}
                      className={cn("border-r px-3 py-1.5 text-sm font-medium last:border-r-0 hover:bg-accent", useful === v && "bg-primary text-primary-foreground hover:bg-primary")}
                    >
                      {label as string}
                    </button>
                  ))}
                </div>
              </div>
              {useful !== null ? (
                <fieldset>
                  <legend className="text-sm font-medium">Why? (optional)</legend>
                  <div className="mt-1.5 space-y-1.5">
                    {options.map((r) => (
                      <label key={r} className="flex items-center gap-2 text-sm">
                        <input type="checkbox" checked={reasons.includes(r)} onChange={() => setReasons(reasons.includes(r) ? reasons.filter((x) => x !== r) : [...reasons, r])} />
                        {r}
                      </label>
                    ))}
                  </div>
                </fieldset>
              ) : null}
              <Field label="Comment (optional)" htmlFor="fb-comment">
                <Textarea id="fb-comment" value={comment} onChange={(e) => setComment(e.target.value)} placeholder="What would have made this case easier to review?" />
              </Field>
              <Button type="submit" disabled={!caseId || useful === null}>
                {submit.isPending ? "Submitting feedback" : "Submit feedback"}
              </Button>
            </fieldset>
            <div aria-live="polite" className="text-sm">
              {done ? <p className="rounded-md border border-emerald-500/40 bg-emerald-500/10 p-3">{done}</p> : null}
              {submit.isError ? <p role="alert" className="rounded-md border border-red-600/40 bg-red-600/5 p-3">Feedback was not submitted: {(submit.error as Error).message}</p> : null}
            </div>
          </form>
        </Card>

        <div>
          <h2 className="mb-3 text-base font-semibold">
            Submitted feedback{" "}
            {entries.length ? (
              <span className="num text-sm font-normal text-muted-foreground">
                ({usefulCount} of {entries.length} marked useful)
              </span>
            ) : null}
          </h2>
          {feedback.isLoading ? <Loading /> : null}
          {feedback.error ? <ErrorState error={feedback.error} onRetry={() => feedback.refetch()} /> : null}
          {feedback.data && !entries.length ? <Empty title="No feedback yet">Submit the first entry using the form.</Empty> : null}
          <ul className="space-y-3">
            {entries.map((e) => (
              <li key={e.id}>
                <Card className="p-4 text-sm">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <Link href={`/cases/${e.caseId}`} className="id font-medium text-link underline-offset-4 hover:underline">
                      {e.caseId}
                    </Link>
                    <StatusPill tone={e.useful ? "good" : "warn"}>{e.useful ? "Useful" : "Not useful"}</StatusPill>
                  </div>
                  {e.reasons.length ? <p className="mt-2">{e.reasons.join("; ")}</p> : null}
                  {e.comment ? <p className="mt-1 max-w-[75ch] text-muted-foreground">{e.comment}</p> : null}
                  <p className="mt-2 text-xs text-muted-foreground">
                    <span className="id">{e.actor}</span>, <time dateTime={e.ts} className="id">{dateTime(e.ts)}</time> UTC
                  </p>
                </Card>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </>
  );
}
