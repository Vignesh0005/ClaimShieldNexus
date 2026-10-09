"use client";

import { useEffect, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { cn, num } from "@/lib/utils";

interface Stage {
  key: string;
  label: string;
  value: number;
}

const FILL = ["bg-slate-400 dark:bg-slate-500", "bg-electric", "bg-evidence", "bg-risk-critical"];

function useCountUp(target: number, run: boolean, delayMs: number) {
  const reduced = useReducedMotion();
  const [v, setV] = useState(run && !reduced ? 0 : target);
  useEffect(() => {
    if (!run || reduced) {
      setV(target);
      return;
    }
    let raf = 0;
    const start = performance.now() + delayMs;
    const tick = (now: number) => {
      const t = Math.min(1, Math.max(0, (now - start) / 900));
      setV(Math.round(target * (1 - Math.pow(1 - t, 3))));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, run, reduced, delayMs]);
  return v;
}

function Row({ stage, prev, index, max, animate, large }: { stage: Stage; prev?: Stage; index: number; max: number; animate: boolean; large: boolean }) {
  const value = useCountUp(stage.value, animate, index * 350);
  // Log scale: a linear scale would make the last stage (about 0.2% of claims) invisible.
  const width = Math.max(4, (Math.log10(Math.max(stage.value, 1) + 1) / Math.log10(max + 1)) * 100);
  const kept = prev && prev.value ? (stage.value / prev.value) * 100 : null;
  return (
    <li className={cn("grid items-center gap-x-3", large ? "grid-cols-[5.5rem_1fr] sm:grid-cols-[7rem_1fr]" : "grid-cols-[5rem_1fr]")}>
      <span className={cn("text-muted-foreground", large ? "text-sm sm:text-base" : "text-sm")}>{stage.label}</span>
      <div className="flex min-w-0 items-center gap-3">
        <motion.div
          className={cn("origin-left rounded-sm", FILL[index % FILL.length], large ? "h-9 sm:h-11" : "h-6")}
          style={{ width: `${width}%` }}
          initial={animate ? { scaleX: 0 } : false}
          animate={{ scaleX: 1 }}
          transition={{ duration: 0.7, delay: index * 0.35, ease: [0.2, 0.7, 0.2, 1] }}
        />
        <span className={cn("num shrink-0 font-semibold", large ? "text-xl sm:text-3xl" : "text-sm")}>{num(value)}</span>
        {kept !== null ? (
          <span className={cn("hidden shrink-0 text-muted-foreground sm:inline", large ? "text-sm" : "text-xs")}>
            {kept < 10 ? kept.toFixed(1) : Math.round(kept)}% of {prev!.label.toLowerCase()}
          </span>
        ) : null}
      </div>
    </li>
  );
}

export function FunnelChart({ stages, animate = false, size = "md", className }: { stages: Stage[]; animate?: boolean; size?: "md" | "lg"; className?: string }) {
  const max = Math.max(...stages.map((s) => s.value), 1);
  const large = size === "lg";
  return (
    <figure className={className}>
      <ol className={cn(large ? "space-y-3" : "space-y-2")} aria-label={`Alert-to-case funnel: ${stages.map((s) => `${s.label} ${num(s.value)}`).join(", ")}`}>
        {stages.map((s, i) => (
          <Row key={s.key} stage={s} prev={stages[i - 1]} index={i} max={max} animate={animate} large={large} />
        ))}
      </ol>
      <figcaption className="mt-3 text-xs text-muted-foreground">Bar length uses a log scale so the final stage stays visible.</figcaption>
    </figure>
  );
}
