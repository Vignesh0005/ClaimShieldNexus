import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import type { Metric } from "@/lib/types";
import { Card } from "@/components/ui/card";

export function MetricCard({ metric, period = "vs. prior 30 days" }: { metric: Metric; period?: string }) {
  const Icon = metric.direction === "up" ? ArrowUpRight : ArrowDownRight;
  return (
    <Card className="glass-panel p-5">
      <p className="text-sm text-muted-foreground">{metric.label}</p>
      <p className="num mt-1 text-2xl font-semibold">{metric.display}</p>
      <p className="mt-1 flex items-center gap-1 text-xs text-muted-foreground">
        <Icon className="size-3.5" aria-hidden />
        <span className="num font-medium text-foreground">{metric.delta}</span>
        <span className="sr-only">{metric.direction === "up" ? "increase" : "decrease"}</span>
        {period}
      </p>
    </Card>
  );
}
