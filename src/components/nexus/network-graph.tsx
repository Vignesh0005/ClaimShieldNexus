"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { Core, LayoutOptions } from "cytoscape";
import { useTheme } from "next-themes";
import { Pause, Play } from "lucide-react";
import type { GraphNode, NetworkData } from "@/lib/types";
import { inr } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Slider } from "@/components/ui/form";
import { Select } from "@/components/ui/select";
import { RiskBadge } from "./risk-badge";

type Filter = "all" | "loop" | "provider" | "member" | "facility";
type LayoutName = "cose" | "concentric" | "circle" | "grid";

const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const monthLabel = (m: string) => `${MONTH_NAMES[Number(m.slice(5, 7)) - 1]} ${m.slice(0, 4)}`;

function monthsBetween(from: string, to: string) {
  const out: string[] = [];
  let y = Number(from.slice(0, 4));
  let m = Number(from.slice(5, 7));
  for (let i = 0; i < 120; i++) {
    const cur = `${y}-${String(m).padStart(2, "0")}`;
    out.push(cur);
    if (cur >= to) break;
    m += 1;
    if (m > 12) {
      m = 1;
      y += 1;
    }
  }
  return out;
}

const matches = (n: GraphNode, f: Filter) => f === "all" || (f === "loop" ? !!n.inLoop : n.type === f);

export function TimeTravelSlider({ months, index, onChange }: { months: string[]; index: number; onChange: (i: number) => void }) {
  const [playing, setPlaying] = useState(false);
  useEffect(() => {
    if (!playing) return;
    if (index >= months.length - 1) {
      setPlaying(false);
      return;
    }
    const t = setTimeout(() => onChange(index + 1), 700);
    return () => clearTimeout(t);
  }, [playing, index, months.length, onChange]);
  return (
    <div className="flex items-center gap-3">
      <Button
        variant="outline"
        size="icon"
        aria-label={playing ? "Pause time travel" : "Play time travel from the start"}
        onClick={() => {
          if (!playing && index >= months.length - 1) onChange(0);
          setPlaying(!playing);
        }}
      >
        {playing ? <Pause /> : <Play />}
      </Button>
      <span className="hidden text-xs text-muted-foreground sm:inline">{monthLabel(months[0])}</span>
      <Slider
        thumbLabel="Show network as of"
        valueText={monthLabel(months[index])}
        min={0}
        max={months.length - 1}
        step={1}
        value={[index]}
        onValueChange={([v]) => {
          setPlaying(false);
          onChange(v);
        }}
      />
      <span className="hidden text-xs text-muted-foreground sm:inline">{monthLabel(months[months.length - 1])}</span>
      <span className="num w-20 shrink-0 text-right text-sm font-medium">{monthLabel(months[index])}</span>
    </div>
  );
}

const LEGEND: [string, string, boolean][] = [
  ["Providers in referral loop", "#DC2626", false],
  ["Other providers", "#64748B", false],
  ["Members", "#047857", false],
  ["Facilities", "#F59E0B", false],
  ["Referrals", "#334155", true],
  ["Claims", "#94A3B8", true],
];

function NodeDetails({ node, counts }: { node: GraphNode | undefined; counts: Record<string, number> }) {
  if (!node) {
    return <p className="text-sm text-muted-foreground">Select a node in the graph, or choose one from the list above, to see its details.</p>;
  }
  const rows: [string, React.ReactNode][] = [];
  if (node.name) rows.push(["Name", node.name]);
  rows.push(["Type", node.type[0].toUpperCase() + node.type.slice(1)]);
  if (node.specialty) rows.push(["Specialty", node.specialty]);
  rows.push(["Claims", node.claims.toLocaleString("en-IN")]);
  rows.push(["Total billed", inr(node.amount)]);
  if (node.risk !== undefined) rows.push(["Risk", <RiskBadge key="r" score={node.risk} />]);
  const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
  rows.push(["Connections", [plural(counts.provider, "provider", "providers"), plural(counts.member, "member", "members"), plural(counts.facility, "facility", "facilities")].join(", ")]);
  if (node.sharedAddresses !== undefined) rows.push(["Shared addresses", node.sharedAddresses]);
  if (node.priorInvestigations !== undefined) rows.push(["Prior investigations", node.priorInvestigations]);
  rows.push(["First seen", monthLabel(node.firstSeen)]);
  return (
    <dl className="divide-y text-sm">
      {rows.map(([k, v]) => (
        <div key={k} className="flex items-center justify-between gap-3 py-1.5">
          <dt className="text-muted-foreground">{k}</dt>
          <dd className="num text-right">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

export function NetworkGraph({ data, height = 520 }: { data: NetworkData; height?: number }) {
  const container = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const { resolvedTheme } = useTheme();
  const months = useMemo(() => monthsBetween(data.range.from, data.range.to), [data.range.from, data.range.to]);
  const [index, setIndex] = useState(months.length - 1);
  const [filter, setFilter] = useState<Filter>("all");
  const [layout, setLayout] = useState<LayoutName>("cose");
  const [zoom, setZoom] = useState(1);
  const [selectedId, setSelectedId] = useState<string | null>(data.centerId ?? null);
  const [ready, setReady] = useState(false);
  const cutoff = months[Math.min(index, months.length - 1)];

  const byId = useMemo(() => new Map(data.nodes.map((n) => [n.id, n])), [data.nodes]);

  const visible = useMemo(() => {
    const ids = new Set(data.nodes.filter((n) => n.firstSeen <= cutoff && matches(n, filter)).map((n) => n.id));
    const edges = data.edges.filter((e) => e.date <= cutoff && ids.has(e.source) && ids.has(e.target));
    return { ids, edges };
  }, [data, cutoff, filter]);

  const counts = useMemo(() => {
    const c: Record<string, number> = { provider: 0, member: 0, facility: 0 };
    if (!selectedId) return c;
    const seen = new Set<string>();
    for (const e of visible.edges) {
      const other = e.source === selectedId ? e.target : e.target === selectedId ? e.source : null;
      if (!other || seen.has(other)) continue;
      seen.add(other);
      const n = byId.get(other);
      if (n) c[n.type] += 1;
    }
    return c;
  }, [selectedId, visible, byId]);

  // Build the graph once per dataset; time travel and filters only toggle visibility.
  useEffect(() => {
    let cy: Core | null = null;
    let cancelled = false;
    setReady(false);
    import("cytoscape").then(({ default: cytoscape }) => {
      if (cancelled || !container.current) return;
      const size = { provider: 26, facility: 22, member: 10 };
      cy = cytoscape({
        container: container.current,
        minZoom: 0.2,
        maxZoom: 3,
        elements: [
          ...data.nodes.map((n) => ({
            data: { id: n.id, label: n.type === "member" ? "" : n.label, type: n.type, loop: n.inLoop ? 1 : 0, size: n.inLoop ? 32 : size[n.type] },
          })),
          ...data.edges.map((e) => ({ data: { id: e.id, source: e.source, target: e.target, type: e.type } })),
        ],
        style: [
          {
            selector: "node",
            style: {
              width: "data(size)",
              height: "data(size)",
              label: "data(label)",
              "font-size": 9,
              "font-family": "ui-monospace, monospace",
              "text-valign": "bottom",
              "text-margin-y": 4,
              "background-fill": "radial-gradient",
              "background-gradient-stop-colors": "#CBD5E1 #64748B" as unknown as string[],
              "border-width": 1,
              "border-color": "#0F172A",
            },
          },
          { selector: "node[loop = 1]", style: { "background-gradient-stop-colors": "#FCA5A5 #DC2626" as unknown as string[] } },
          { selector: 'node[type = "member"]', style: { "background-gradient-stop-colors": "#D1FAE5 #047857" as unknown as string[], "border-width": 0 } },
          { selector: 'node[type = "facility"]', style: { "background-gradient-stop-colors": "#FDE68A #F59E0B" as unknown as string[], shape: "round-rectangle" } },
          { selector: "edge", style: { width: 1, "line-color": "#94A3B8", opacity: 0.45, "curve-style": "bezier" } },
          {
            selector: 'edge[type = "referral"]',
            style: { width: 2.5, "line-color": "#334155", opacity: 0.95, "target-arrow-shape": "triangle", "target-arrow-color": "#334155", "arrow-scale": 0.9 },
          },
          { selector: ".hidden", style: { display: "none" } },
          { selector: "node:selected", style: { "border-width": 4, "border-color": "#047857" } },
        ],
        layout: { name: "cose", animate: false, padding: 24, nodeRepulsion: () => 9000, idealEdgeLength: () => 60 } as LayoutOptions,
      });
      cy.on("tap", "node", (evt) => setSelectedId(evt.target.id()));
      cy.on("zoom", () => cy && setZoom(Math.round(cy.zoom() * 100) / 100));
      cyRef.current = cy;
      setZoom(Math.round(cy.zoom() * 100) / 100);
      setReady(true);
    });
    return () => {
      cancelled = true;
      cy?.destroy();
      cyRef.current = null;
    };
  }, [data]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy || !ready) return;
    const edgeIds = new Set(visible.edges.map((e) => e.id));
    cy.batch(() => {
      cy.nodes().forEach((n) => void n.toggleClass("hidden", !visible.ids.has(n.id())));
      cy.edges().forEach((e) => void e.toggleClass("hidden", !edgeIds.has(e.id())));
    });
  }, [visible, ready]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy || !ready) return;
    cy.style().selector("node").style("color", resolvedTheme === "dark" ? "#E2E8F0" : "#0F172A").update();
  }, [resolvedTheme, ready]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy || !ready) return;
    cy.nodes().unselect();
    if (selectedId) cy.getElementById(selectedId).select();
  }, [selectedId, ready]);

  const runLayout = (name: LayoutName) => {
    setLayout(name);
    const cy = cyRef.current;
    if (!cy) return;
    const options =
      name === "cose"
        ? { name, animate: false, padding: 24, nodeRepulsion: () => 9000, idealEdgeLength: () => 60 }
        : name === "concentric"
          ? { name, padding: 24, minNodeSpacing: 8, concentric: (n: { data: (k: string) => number }) => n.data("size"), levelWidth: () => 8 }
          : { name, padding: 24 };
    cy.elements().not(".hidden").layout(options as LayoutOptions).run();
  };

  const applyZoom = (level: number) => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.zoom({ level, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } });
  };

  const selectable = data.nodes.filter((n) => n.type !== "member" && visible.ids.has(n.id));
  const shown = { provider: 0, member: 0, facility: 0 };
  for (const id of visible.ids) shown[byId.get(id)!.type] += 1;

  return (
    <div className="grid gap-4 wide:grid-cols-[minmax(0,1fr)_20rem] lg:grid-cols-[minmax(0,1fr)_18rem]">
      <div className="min-w-0 space-y-3">
        <Card className="relative overflow-hidden">
          <div
            ref={container}
            style={{ height }}
            role="img"
            aria-label={`Network graph as of ${monthLabel(cutoff)} showing ${shown.provider} providers, ${shown.member} members and ${shown.facility} facilities, with ${visible.edges.filter((e) => e.type === "referral").length} referral links and ${visible.edges.filter((e) => e.type === "claim").length} claim links. Use the node list to select a node with the keyboard.`}
          />
          {!ready ? <p className="absolute inset-0 flex items-center justify-center text-sm text-muted-foreground">Laying out graph</p> : null}
          <ul className="flex flex-wrap gap-x-4 gap-y-1 border-t px-3 py-2 text-xs text-muted-foreground">
            {LEGEND.map(([label, color, isEdge]) => (
              <li key={label} className="flex items-center gap-1.5">
                <span className={isEdge ? "h-0.5 w-4" : "size-2.5 rounded-full"} style={{ background: color }} aria-hidden />
                {label}
              </li>
            ))}
          </ul>
        </Card>
        <Card className="space-y-3 p-3">
          <TimeTravelSlider months={months} index={index} onChange={setIndex} />
          <div className="grid gap-3 sm:grid-cols-3">
            <Select
              label="Filter nodes"
              value={filter}
              onValueChange={(v) => setFilter(v as Filter)}
              options={[
                { value: "all", label: "Filter: all nodes" },
                { value: "loop", label: "Filter: referral loop only" },
                { value: "provider", label: "Filter: providers" },
                { value: "member", label: "Filter: members" },
                { value: "facility", label: "Filter: facilities" },
              ]}
            />
            <Select
              label="Layout"
              value={layout}
              onValueChange={(v) => runLayout(v as LayoutName)}
              options={[
                { value: "cose", label: "Layout: force" },
                { value: "concentric", label: "Layout: concentric" },
                { value: "circle", label: "Layout: circle" },
                { value: "grid", label: "Layout: grid" },
              ]}
            />
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">Zoom</span>
              <Slider thumbLabel="Zoom" valueText={`${Math.round(zoom * 100)}%`} min={0.2} max={3} step={0.05} value={[zoom]} onValueChange={([v]) => applyZoom(v)} />
            </div>
          </div>
        </Card>
      </div>

      <Card className="h-fit p-4">
        <h3 className="text-sm font-semibold">Node details</h3>
        <Select
          className="mt-2"
          label="Select a node"
          placeholder="Select a provider or facility"
          value={selectedId && selectable.some((n) => n.id === selectedId) ? selectedId : ""}
          onValueChange={setSelectedId}
          options={selectable.map((n) => ({ value: n.id, label: `${n.id}${n.inLoop ? " (in loop)" : ""}` }))}
        />
        {selectedId ? <p className="id mt-3 font-semibold">{selectedId}</p> : null}
        <div className="mt-2">
          <NodeDetails node={selectedId ? byId.get(selectedId) : undefined} counts={counts} />
        </div>
      </Card>
    </div>
  );
}
