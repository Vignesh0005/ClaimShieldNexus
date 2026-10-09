"use client";

import { useNetwork } from "@/lib/api";
import { ErrorState, Loading, PageHeader } from "@/components/ui/state";
import { NetworkGraph } from "@/components/nexus/network-graph";

export default function NetworkPage() {
  const { data, isLoading, error, refetch } = useNetwork(null);
  return (
    <>
      <PageHeader
        title="Network"
        description="Providers, members and facilities for this tenant, joined by referrals and claims. Move the time slider to see how referral loops formed. A loop is a pattern to review; integrated care groups can produce the same shape."
      />
      {isLoading ? <Loading label="Loading network" /> : null}
      {error ? <ErrorState error={error} onRetry={() => refetch()} /> : null}
      {data ? <NetworkGraph data={data} height={600} /> : null}
    </>
  );
}
