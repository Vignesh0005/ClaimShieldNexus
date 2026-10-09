"use client";

import { AlertTriangle } from "lucide-react";
import { useModels } from "@/lib/api";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorState, Loading, PageHeader } from "@/components/ui/state";
import { Table, Td, Th, Tr } from "@/components/ui/table";

const fmt = (v: number | null | undefined) => (v === null || v === undefined ? "Not yet measured" : v.toFixed(2));

export default function ModelsPage() {
  const { data, isLoading, error, refetch } = useModels();
  return (
    <>
      <PageHeader title="Model card" description="What the scoring model is for, how it was evaluated, and where it falls short. Read the limitations before relying on any score." />
      {isLoading ? <Loading /> : null}
      {error ? <ErrorState error={error} onRetry={() => refetch()} /> : null}
      {data ? (
        <div className="space-y-4">
          <Card className="border-amber-500/60 bg-amber-500/10 p-4 sm:p-5">
            <h2 className="flex items-center gap-2 text-base font-semibold">
              <AlertTriangle className="size-5 text-amber-800 dark:text-amber-200" aria-hidden />
              Important limitations
            </h2>
            {data.syntheticWarning ? <p className="mt-2 text-sm font-medium">{data.syntheticWarning}</p> : null}
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
              {data.limitations.map((l) => (
                <li key={l}>{l}</li>
              ))}
            </ul>
          </Card>

          <Card className="p-4 sm:p-5">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="text-lg font-semibold">
                <span className="font-mono">{data.name}</span> <span className="id text-muted-foreground">{data.version}</span>
              </h2>
              <p className="text-sm text-muted-foreground">
                Trained <time dateTime={data.trainedAt} className="id">{data.trainedAt}</time>
                {data.trainingSamples ? <span className="num"> on {data.trainingSamples.toLocaleString("en-IN")} claims</span> : null}
              </p>
            </div>
            <div className="mt-4 grid gap-6 md:grid-cols-2">
              <div>
                <h3 className="text-sm font-semibold">Intended use</h3>
                <p className="mt-1 max-w-[70ch] text-sm">{data.intendedUse}</p>
                <h3 className="mt-4 text-sm font-semibold">Training data</h3>
                <p className="mt-1 max-w-[70ch] text-sm">{data.trainingData}</p>
              </div>
              <div>
                <h3 className="text-sm font-semibold">Not intended for</h3>
                <ul className="mt-1 list-disc space-y-1 pl-5 text-sm">
                  {data.outOfScope.map((o) => (
                    <li key={o}>{o}</li>
                  ))}
                </ul>
                <h3 className="mt-4 text-sm font-semibold">Fairness</h3>
                <p className="mt-1 max-w-[70ch] text-sm">{data.fairness ?? "Not yet measured."}</p>
              </div>
            </div>
          </Card>

          {data.evaluation ? (
            <Card className="overflow-hidden">
              <CardHeader className="pb-3">
                <div>
                  <CardTitle>Evaluation</CardTitle>
                  <CardDescription>
                    Random split mixes claims from the same providers into training and test data, which flatters the model. Provider split tests only on providers the model never saw
                    {data.providerSplitFolds ? ` (${data.providerSplitFolds} folds)` : ""} and is the more realistic figure.
                  </CardDescription>
                </div>
              </CardHeader>
              <Table>
                <caption className="sr-only">Model metrics on random and provider splits</caption>
                <thead>
                  <tr>
                    <Th>Metric</Th>
                    <Th className="text-right">Random split</Th>
                    <Th className="text-right">Provider split (unseen providers)</Th>
                  </tr>
                </thead>
                <tbody>
                  {data.evaluation.map((m) => (
                    <Tr key={m.label}>
                      <Td>{m.label}</Td>
                      <Td className="num text-right">{fmt(m.random)}</Td>
                      <Td className="num text-right font-semibold">{fmt(m.providerSplit)}</Td>
                    </Tr>
                  ))}
                </tbody>
              </Table>
              {data.evaluationNote ? <p className="border-t px-4 py-3 text-sm text-muted-foreground">{data.evaluationNote}</p> : null}
            </Card>
          ) : data.metrics ? (
            <dl className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              {data.metrics.map((m) => (
                <Card key={m.label} className="p-4">
                  <dt className="text-sm text-muted-foreground">{m.label}</dt>
                  <dd className="num mt-1 text-2xl font-semibold">{m.value.toFixed(2)}</dd>
                  <dd className="mt-1 text-xs text-muted-foreground">{m.note}</dd>
                </Card>
              ))}
            </dl>
          ) : null}

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <div>
                  <CardTitle>Which features dominate</CardTitle>
                  <CardDescription>Share of the model's total gain.</CardDescription>
                </div>
              </CardHeader>
              <CardContent>
                <dl className="space-y-2">
                  {data.features.slice(0, 10).map((f) => (
                    <div key={f.name} className="grid grid-cols-[minmax(0,13rem)_1fr_2.5rem] items-center gap-3 text-sm">
                      <dt className="truncate font-mono text-xs">{f.name}</dt>
                      <dd className="h-2.5 overflow-hidden rounded-sm bg-secondary" aria-hidden>
                        <div className="h-full rounded-sm bg-electric" style={{ width: `${(f.importance / (data.features[0]?.importance || 1)) * 100}%` }} />
                      </dd>
                      <dd className="num text-right">{Math.round(f.importance * 100)}%</dd>
                    </div>
                  ))}
                </dl>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Bias analysis</CardTitle>
              </CardHeader>
              <CardContent>
                {data.biasAnalysis?.length ? (
                  <ul className="list-disc space-y-1.5 pl-5 text-sm">
                    {data.biasAnalysis.map((b) => (
                      <li key={b}>{b}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-muted-foreground">Not yet measured.</p>
                )}
              </CardContent>
            </Card>
          </div>

          <Card className="p-4 sm:p-5">
            <h2 className="text-sm font-semibold">Version history</h2>
            <ol className="mt-2 divide-y text-sm">
              {data.history.map((h) => (
                <li key={h.version} className="grid gap-x-4 py-2 sm:grid-cols-[5rem_7rem_1fr]">
                  <span className="id font-medium">{h.version}</span>
                  <time dateTime={h.date} className="id text-muted-foreground">{h.date}</time>
                  <span>{h.note}</span>
                </li>
              ))}
            </ol>
          </Card>
        </div>
      ) : null}
    </>
  );
}
