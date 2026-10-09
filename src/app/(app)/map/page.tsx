"use client";

import { useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useGeo } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Card } from "@/components/ui/card";
import { ErrorState, Loading, PageHeader, Skeleton } from "@/components/ui/state";
import { RiskBadge } from "@/components/nexus/risk-badge";

const GeoMap = dynamic(() => import("@/components/nexus/geo-map").then((m) => m.GeoMap), {
  ssr: false,
  loading: () => <Skeleton className="h-[26rem] lg:h-[34rem]" />,
});

export default function MapPage() {
  const { data, isLoading, error, refetch } = useGeo();
  const [selected, setSelected] = useState<string | null>(null);
  return (
    <>
      <PageHeader
        title="Impossible geography"
        description="Pairs of claims that place the same member at two distant locations on the same day. Telehealth, billing-address errors and shared identifiers can also produce these pairs."
      />
      {isLoading ? <Loading /> : null}
      {error ? <ErrorState error={error} onRetry={() => refetch()} /> : null}
      {data ? (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_22rem]">
          <Card className="overflow-hidden">
            <GeoMap events={data} selectedId={selected} onSelect={setSelected} />
          </Card>
          <Card className="max-h-[34rem] overflow-y-auto">
            <h2 className="sticky top-0 border-b bg-card px-4 py-3 text-sm font-semibold">{data.length} location conflicts</h2>
            <ul className="divide-y">
              {data.map((e) => {
                const speed = e.minutesApart ? Math.round(e.distanceKm / (e.minutesApart / 60)) : null;
                const active = selected === e.id;
                return (
                  <li key={e.id}>
                    <button
                      type="button"
                      aria-pressed={active}
                      onClick={() => setSelected(active ? null : e.id)}
                      className={cn("block w-full px-4 py-3 text-left text-sm hover:bg-accent", active && "bg-primary/10")}
                    >
                      <span className="flex items-center justify-between gap-2">
                        <span className="id font-semibold">{e.subject}</span>
                        <RiskBadge level={e.level} />
                      </span>
                      <span className="mt-1 block">
                        {e.a.time && e.b.time ? (
                          <>
                            {e.a.city} at <span className="num">{e.a.time}</span>, then {e.b.city} at <span className="num">{e.b.time}</span>
                          </>
                        ) : (
                          <>
                            {e.a.city} and {e.b.city} on the same day
                          </>
                        )}
                      </span>
                      <span className="num mt-0.5 block text-xs text-muted-foreground">
                        {e.date}: {e.distanceKm.toLocaleString("en-IN")} km apart{speed !== null ? ` in ${e.minutesApart} min (would need ${speed.toLocaleString("en-IN")} km/h)` : ". Claims carry dates, not times."}
                      </span>
                    </button>
                    {active && e.caseId ? (
                      <p className="px-4 pb-3 text-sm">
                        <Link href={`/cases/${e.caseId}?tab=evidence`} className="font-medium text-link underline-offset-4 hover:underline">
                          Open case <span className="id">{e.caseId}</span>
                        </Link>
                      </p>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          </Card>
        </div>
      ) : null}
    </>
  );
}
