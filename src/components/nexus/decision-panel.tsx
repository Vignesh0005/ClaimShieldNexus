"use client";

import { useState } from "react";
import { CircleCheck, CircleHelp, CircleX, UserRoundCog, type LucideIcon } from "lucide-react";
import { useSubmitDecision } from "@/lib/api";
import type { CaseDetail, Decision, LineDecision } from "@/lib/types";
import { cn, inr } from "@/lib/utils";
import { useAuthStore } from "@/stores";
import { Button } from "@/components/ui/button";
import { Field, Textarea } from "@/components/ui/form";
import { Select } from "@/components/ui/select";

const DECISIONS: { value: Decision; label: string; hint: string; icon: LucideIcon }[] = [
  { value: "CONFIRM_FWA", label: "Confirm for SIU referral", hint: "Evidence supports further investigation.", icon: CircleCheck },
  { value: "NEEDS_INFO", label: "Needs more information", hint: "Request records before deciding.", icon: CircleHelp },
  { value: "FALSE_POSITIVE", label: "Close as false positive", hint: "Billing pattern is explained.", icon: CircleX },
  { value: "REASSIGN", label: "Reassign", hint: "Hand the case to another reviewer.", icon: UserRoundCog },
];

const LINE_OPTIONS: { value: LineDecision; label: string }[] = [
  { value: "confirm", label: "Confirm" },
  { value: "dismiss", label: "Dismiss" },
  { value: "review", label: "Review" },
];

const NEXT_ACTIONS: Record<Decision, string[]> = {
  CONFIRM_FWA: ["Record referral for further investigation"],
  NEEDS_INFO: ["Request medical records", "Request EHR visit notes", "Contact provider relations"],
  FALSE_POSITIVE: ["Close case", "Close case and add provider to peer-group review"],
  REASSIGN: ["Return to queue"],
};

const ASSIGNEES = ["A. Sharma", "J. Okafor", "L. Chen"];

export function DecisionPanel({ item }: { item: CaseDetail }) {
  const canDecide = useAuthStore((s) => s.can("case.decide"));
  const submit = useSubmitDecision(item.id);
  const [decision, setDecision] = useState<Decision | null>(null);
  const [lines, setLines] = useState<Record<string, LineDecision>>({});
  const [notes, setNotes] = useState("");
  const [nextAction, setNextAction] = useState("");
  const [assignee, setAssignee] = useState(ASSIGNEES.find((a) => a !== item.assignee) ?? ASSIGNEES[0]);
  const [done, setDone] = useState<string | null>(null);

  const choose = (d: Decision) => {
    setDecision(d);
    setNextAction(NEXT_ACTIONS[d][0]);
    setDone(null);
  };

  const notesMissing = decision !== null && notes.trim().length < 10;

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!decision || notesMissing) return;
    const label = DECISIONS.find((d) => d.value === decision)!.label;
    submit.mutate(
      { decision, lines, notes: notes.trim(), nextAction, assignee: decision === "REASSIGN" ? assignee : undefined },
      {
        onSuccess: () => {
          setDone(`Decision recorded: ${label}. It has been added to the audit trail.`);
          setDecision(null);
          setLines({});
          setNotes("");
        },
      },
    );
  };

  return (
    <form onSubmit={onSubmit} className="space-y-5" aria-describedby="decision-note">
      <p id="decision-note" className="max-w-[75ch] text-sm text-muted-foreground">
        The system does not act on a case by itself. A decision recorded here is a reviewer's judgement about next steps, not a finding of fraud, and every decision is written to the audit trail.
      </p>

      {!canDecide ? (
        <p role="status" className="rounded-md border border-dashed p-3 text-sm">
          Your role can view this case but cannot record decisions. Ask an SIU Investigator or Admin to review it.
        </p>
      ) : null}

      <fieldset disabled={!canDecide || submit.isPending} className="space-y-5 disabled:opacity-60">
        <div>
          <h3 className="text-sm font-semibold">Case-level decision</h3>
          <div role="radiogroup" aria-label="Case-level decision" className="mt-2 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
            {DECISIONS.map((d) => {
              const selected = decision === d.value;
              return (
                <button
                  key={d.value}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  onClick={() => choose(d.value)}
                  className={cn(
                    "flex items-start gap-2.5 rounded-md border bg-card p-3 text-left transition-colors hover:bg-accent",
                    selected && "border-primary bg-primary/10 ring-1 ring-primary",
                  )}
                >
                  <d.icon className="mt-0.5 size-4 shrink-0" aria-hidden />
                  <span>
                    <span className="block text-sm font-medium">{d.label}</span>
                    <span className="block text-xs text-muted-foreground">{d.hint}</span>
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        <div>
          <h3 className="text-sm font-semibold">Line-level decisions (optional)</h3>
          <ul className="mt-2 divide-y rounded-md border">
            {item.lines.map((l) => (
              <li key={l.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-sm">
                <span className="min-w-0">
                  <span className="id font-medium">
                    Line {l.id} ({l.code})
                  </span>{" "}
                  <span className="text-muted-foreground">
                    {l.description}, <span className="num">{inr(l.amount)}</span>
                  </span>
                </span>
                <span role="radiogroup" aria-label={`Decision for line ${l.id}`} className="inline-flex overflow-hidden rounded-md border">
                  {LINE_OPTIONS.map((o) => {
                    const selected = lines[l.id] === o.value;
                    return (
                      <button
                        key={o.value}
                        type="button"
                        role="radio"
                        aria-checked={selected}
                        onClick={() =>
                          setLines((prev) => {
                            const next = { ...prev };
                            if (selected) delete next[l.id];
                            else next[l.id] = o.value;
                            return next;
                          })
                        }
                        className={cn("border-r px-2.5 py-1 text-xs font-medium last:border-r-0 hover:bg-accent", selected && "bg-primary text-primary-foreground hover:bg-primary")}
                      >
                        {o.label}
                      </button>
                    );
                  })}
                </span>
              </li>
            ))}
          </ul>
        </div>

        <Field label="Notes" htmlFor="decision-notes" hint="Required. Record the reasoning another reviewer would need to understand this decision.">
          <Textarea
            id="decision-notes"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Example: Matching claims reviewed. Evidence supports further investigation; record the findings and supporting references."
            aria-invalid={notesMissing}
          />
        </Field>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Next action" htmlFor="next-action">
            <Select
              id="next-action"
              label="Next action"
              value={nextAction}
              onValueChange={setNextAction}
              disabled={!decision}
              placeholder="Choose a decision first"
              options={(decision ? NEXT_ACTIONS[decision] : []).map((a) => ({ value: a, label: a }))}
            />
          </Field>
          {decision === "REASSIGN" ? (
            <Field label="Reassign to" htmlFor="reassign-to">
              <Select id="reassign-to" label="Reassign to" value={assignee} onValueChange={setAssignee} options={ASSIGNEES.map((a) => ({ value: a, label: a }))} />
            </Field>
          ) : null}
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" disabled={!decision || notesMissing}>
            {submit.isPending ? "Recording decision" : "Record decision"}
          </Button>
          {!decision ? <span className="text-xs text-muted-foreground">Choose a case-level decision to continue.</span> : null}
          {notesMissing ? <span className="text-xs text-muted-foreground">Add at least 10 characters of notes.</span> : null}
        </div>
      </fieldset>

      <div aria-live="polite">
        {done ? <p className="rounded-md border border-emerald-500/40 bg-emerald-500/10 p-3 text-sm">{done}</p> : null}
        {submit.isError ? (
          <p role="alert" className="rounded-md border border-red-600/40 bg-red-600/5 p-3 text-sm">
            The decision was not recorded: {(submit.error as Error).message} Your notes are still here; try again.
          </p>
        ) : null}
      </div>
    </form>
  );
}
