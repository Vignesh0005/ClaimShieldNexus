"use client";

import { useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Field, Input, Textarea } from "@/components/ui/form";
import { Select } from "@/components/ui/select";
import { PublicHeader } from "@/components/shell/public-header";

const VOLUMES = ["Under 100,000 claims a month", "100,000 to 500,000", "500,000 to 2 million", "Over 2 million"];

export default function DemoRequestPage() {
  const [form, setForm] = useState({ name: "", email: "", company: "", volume: VOLUMES[1], message: "" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [sent, setSent] = useState(false);
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setForm({ ...form, [k]: e.target.value });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const next: Record<string, string> = {};
    if (!form.name.trim()) next.name = "Enter your name.";
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(form.email)) next.email = "Enter a work email address, like name@plan.com.";
    if (!form.company.trim()) next.company = "Enter your organization.";
    setErrors(next);
    if (Object.keys(next).length === 0) setSent(true);
  };

  return (
    <div className="min-h-dvh">
      <PublicHeader />
      <main id="main" className="mx-auto grid max-w-5xl gap-10 px-4 py-12 sm:px-6 md:grid-cols-2">
        <div>
          <h1 className="text-3xl font-semibold">Request a demo</h1>
          <p className="mt-3 max-w-[48ch] text-muted-foreground">
            A 30-minute walkthrough with synthetic claims: from ingest to a reviewed case, including the evidence trail and audit log.
          </p>
          <h2 className="mt-8 text-sm font-semibold">What we cover</h2>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted-foreground">
            <li>Mapping your claim fields and connecting a test feed</li>
            <li>How rules, models and the provider graph produce a score</li>
            <li>How investigators review, decide and give feedback</li>
            <li>The model card, bias checks and known limitations</li>
          </ul>
          <p className="mt-8 text-sm text-muted-foreground">
            Prefer to look around first?{" "}
            <Link href="/login" className="font-medium text-link underline-offset-4 hover:underline">
              Open the demo workspace
            </Link>
          </p>
        </div>

        {sent ? (
          <div role="status" className="h-fit rounded-lg border bg-card p-6">
            <h2 className="text-lg font-semibold">Request recorded</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Thanks, {form.name.split(" ")[0]}. This is a demonstration build, so the request was not sent to anyone and no email will follow.
            </p>
            <Button asChild className="mt-4">
              <Link href="/login">Open the demo workspace</Link>
            </Button>
          </div>
        ) : (
          <form onSubmit={submit} noValidate className="space-y-4 rounded-lg border bg-card p-6">
            <Field label="Name" htmlFor="name" hint={errors.name}>
              <Input id="name" autoComplete="name" value={form.name} onChange={set("name")} aria-invalid={!!errors.name} />
            </Field>
            <Field label="Work email" htmlFor="email" hint={errors.email}>
              <Input id="email" type="email" autoComplete="email" value={form.email} onChange={set("email")} aria-invalid={!!errors.email} />
            </Field>
            <Field label="Organization" htmlFor="company" hint={errors.company}>
              <Input id="company" autoComplete="organization" value={form.company} onChange={set("company")} aria-invalid={!!errors.company} />
            </Field>
            <Field label="Claim volume" htmlFor="volume">
              <Select id="volume" label="Claim volume" value={form.volume} onValueChange={(v) => setForm({ ...form, volume: v })} options={VOLUMES.map((v) => ({ value: v, label: v }))} />
            </Field>
            <Field label="Anything we should know (optional)" htmlFor="message">
              <Textarea id="message" value={form.message} onChange={set("message")} />
            </Field>
            <Button type="submit" className="w-full">
              Request a demo
            </Button>
          </form>
        )}
      </main>
    </div>
  );
}
