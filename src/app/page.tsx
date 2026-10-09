import Link from "next/link";
import { PlugZap, Scale, Share2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { FunnelChart } from "@/components/nexus/funnel-chart";
import { PublicHeader } from "@/components/shell/public-header";

const STAGES = [
  { key: "claims", label: "Claims", value: 5000 },
  { key: "alerts", label: "Alerts", value: 640 },
  { key: "clusters", label: "Clusters", value: 48 },
  { key: "cases", label: "SIU cases", value: 12 },
];

const STEPS = [
  { name: "Ingest", body: "Claims arrive as events from your existing system. Field names are mapped once during setup." },
  { name: "Detect", body: "Billing rules, anomaly models and a provider-member graph each look for a different kind of pattern." },
  { name: "Score", body: "Signals combine into a risk score, a member-harm score and an estimate of review effort." },
  { name: "Explain", body: "Each case gets a brief: the evidence, where it came from, and what the system does not know." },
  { name: "Route", body: "Cases that fit your team's capacity go to a human auditor, who makes every decision." },
];

const REASONS = [
  { icon: PlugZap, title: "Plugs into what you run", body: "Event-driven ingest sits beside your claims platform. No change to adjudication, and nothing is pended or denied automatically." },
  { icon: Share2, title: "Sees patterns across providers", body: "Referral loops and shared addresses only show up in the graph. Claim-by-claim rules cannot find them." },
  { icon: Scale, title: "Built for accountable review", body: "A person decides every case. Each view and decision is logged, and the model card reports bias checks and known limits." },
];

export default function LandingPage() {
  return (
    <div className="min-h-dvh bg-background">
      <PublicHeader />
      <main id="main">
        <section className="mx-auto max-w-6xl px-4 pb-16 pt-14 sm:px-6 sm:pt-20">
          <h1 className="max-w-[18ch] text-4xl font-semibold leading-[1.05] tracking-tight sm:text-6xl">AI-powered FWA detection for payers</h1>
          <p className="mt-5 max-w-[52ch] text-lg text-muted-foreground sm:text-xl">
            From thousands of alerts to a ranked, evidence-backed, human-reviewed set of cases.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Button asChild size="lg">
              <Link href="/demo">Request a demo</Link>
            </Button>
            <Button asChild size="lg" variant="outline">
              <a href="#how-it-works">See how it works</a>
            </Button>
          </div>

          <div className="mt-12 rounded-lg border bg-card p-5 sm:p-8">
            <div className="mb-6 flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="text-base font-semibold">One month of claims, reduced to what a team can review</h2>
              <p className="text-sm text-muted-foreground">Synthetic data for a single plan</p>
            </div>
            <FunnelChart stages={STAGES} animate size="lg" />
            <p className="mt-5 max-w-[70ch] text-sm text-muted-foreground">
              99.8% of claims never reach an investigator. The 12 that do arrive with evidence, limitations and a recommended next step.
            </p>
          </div>
        </section>

        <section id="how-it-works" className="scroll-mt-10 border-y bg-card">
          <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
            <h2 className="text-2xl font-semibold sm:text-3xl">How it works</h2>
            <ol className="mt-8 grid gap-6 sm:grid-cols-2 lg:grid-cols-5 lg:gap-0">
              {STEPS.map((s, i) => (
                <li key={s.name} className="relative lg:pr-6">
                  <div className="flex items-center gap-3">
                    <span className="num flex size-8 shrink-0 items-center justify-center rounded-full bg-primary text-sm font-semibold text-primary-foreground">{i + 1}</span>
                    {i < STEPS.length - 1 ? <span className="hidden h-px flex-1 bg-border lg:block" aria-hidden /> : null}
                  </div>
                  <h3 className="mt-4 text-base font-semibold">{s.name}</h3>
                  <p className="mt-1 text-sm text-muted-foreground">{s.body}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section id="why" className="mx-auto max-w-6xl scroll-mt-10 px-4 py-16 sm:px-6">
          <h2 className="text-2xl font-semibold sm:text-3xl">Why ClaimShield</h2>
          <div className="mt-8 grid gap-x-10 gap-y-8 md:grid-cols-3">
            {REASONS.map((r) => (
              <div key={r.title} className="border-t-2 border-primary pt-4">
                <r.icon className="size-5 text-link" aria-hidden />
                <h3 className="mt-3 text-base font-semibold">{r.title}</h3>
                <p className="mt-1 text-sm text-muted-foreground">{r.body}</p>
              </div>
            ))}
          </div>
          <div className="mt-14 flex flex-wrap items-center justify-between gap-4 rounded-lg bg-primary p-6 text-primary-foreground sm:p-8">
            <div>
              <h2 className="text-xl font-semibold">See it with a test scheme</h2>
              <p className="mt-1 max-w-[56ch] text-sm text-slate-300">Sign in to the demo workspace, inject a synthetic billing pattern and follow it from alert to reviewed case.</p>
            </div>
            <div className="dark flex flex-wrap gap-3">
              <Button asChild size="lg">
                <Link href="/login">Open the demo workspace</Link>
              </Button>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t bg-card">
        <div className="mx-auto grid max-w-6xl gap-8 px-4 py-10 text-sm sm:grid-cols-4 sm:px-6">
          <nav aria-label="Product">
            <h2 className="font-semibold">Product</h2>
            <ul className="mt-2 space-y-1.5 text-muted-foreground">
              <li><a className="hover:text-foreground" href="#how-it-works">How it works</a></li>
              <li><a className="hover:text-foreground" href="#why">Features</a></li>
              <li><Link className="hover:text-foreground" href="/login">Demo workspace</Link></li>
            </ul>
          </nav>
          <nav aria-label="Company">
            <h2 className="font-semibold">Company</h2>
            <ul className="mt-2 space-y-1.5 text-muted-foreground">
              <li><Link className="hover:text-foreground" href="/demo">Request a demo</Link></li>
              <li><Link className="hover:text-foreground" href="/login">Log in</Link></li>
            </ul>
          </nav>
          <div>
            <h2 className="font-semibold">Legal</h2>
            <p className="mt-2 text-muted-foreground">ClaimShield Nexus supports human review. It does not adjudicate, deny or recoup claims.</p>
          </div>
          <div>
            <h2 className="font-semibold">Disclaimer</h2>
          </div>
        </div>
      </footer>
    </div>
  );
}
