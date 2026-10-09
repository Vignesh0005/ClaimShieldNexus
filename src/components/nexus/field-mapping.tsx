"use client";

import { useRef, useState } from "react";
import { Plus, Trash2, Upload } from "lucide-react";
import type { FieldMap } from "@/stores";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/form";
import { Select } from "@/components/ui/select";
import { Table, Td, Th, Tr } from "@/components/ui/table";
import { StatusPill } from "./risk-badge";

export const TARGET_FIELDS = [
  "claim_id",
  "member_id",
  "provider_id",
  "service_date",
  "procedure_code",
  "diagnosis_code",
  "billed_amount",
  "paid_amount",
  "place_of_service",
  "units",
  "modifier",
];

export const REQUIRED_FIELDS = ["claim_id", "member_id", "provider_id", "service_date", "procedure_code", "billed_amount"];

const PATTERNS: [RegExp, string][] = [
  [/^(clm|claim)/, "claim_id"],
  [/^(mbr|mem|member|subscriber|patient)/, "member_id"],
  [/^(prv|prov|provider|npi|rendering)/, "provider_id"],
  [/(svc|service|dos).*(dt|date)|^dos$/, "service_date"],
  [/(bill|charge)/, "billed_amount"],
  [/(paid|pay|allowed)/, "paid_amount"],
  [/(pos|place)/, "place_of_service"],
  [/^(unit|qty)/, "units"],
  [/^mod/, "modifier"],
];

export function detectTarget(source: string): string | null {
  const s = source.trim().toLowerCase();
  for (const [re, target] of PATTERNS) if (re.test(s)) return target;
  return null;
}

export function FieldMappingTable({ mapping, onChange, readOnly }: { mapping: FieldMap[]; onChange: (m: FieldMap[]) => void; readOnly?: boolean }) {
  const file = useRef<HTMLInputElement>(null);
  const [status, setStatus] = useState("");
  const update = (i: number, patch: Partial<FieldMap>) => onChange(mapping.map((m, j) => (j === i ? { ...m, ...patch } : m)));
  const missing = REQUIRED_FIELDS.filter((f) => !mapping.some((m) => m.target === f && m.source.trim()));

  const onFile = async (f: File | undefined) => {
    if (!f) return;
    const header = (await f.text()).split(/\r?\n/)[0] ?? "";
    const columns = header.split(/[,;\t|]/).map((c) => c.trim().replace(/^"|"$/g, "")).filter(Boolean);
    if (!columns.length) {
      setStatus(`No column names were found in the first line of ${f.name}. Check that the file has a header row.`);
      return;
    }
    const used = new Set<string>();
    const next: FieldMap[] = columns.map((c) => {
      const t = detectTarget(c);
      if (t && !used.has(t)) {
        used.add(t);
        return { source: c, target: t, detection: "auto" };
      }
      return { source: c, target: "", detection: "manual" };
    });
    onChange(next);
    setStatus(`Read ${columns.length} columns from ${f.name}. ${used.size} were matched automatically; check the rest.`);
  };

  return (
    <div className="space-y-3">
      <div className="rounded-lg border">
        <Table>
          <caption className="sr-only">Mapping from your claim fields to ClaimShield fields</caption>
          <thead>
            <tr>
              <Th>Your field</Th>
              <Th>ClaimShield field</Th>
              <Th>Detection</Th>
              {readOnly ? null : <Th className="w-10"><span className="sr-only">Remove</span></Th>}
            </tr>
          </thead>
          <tbody>
            {mapping.map((m, i) => (
              <Tr key={i}>
                <Td>
                  <Input aria-label={`Your field, row ${i + 1}`} className="h-8 min-w-36 font-mono text-xs" value={m.source} disabled={readOnly} onChange={(e) => update(i, { source: e.target.value })} />
                </Td>
                <Td>
                  <Select
                    label={`ClaimShield field for ${m.source || `row ${i + 1}`}`}
                    className="h-8 min-w-44 font-mono text-xs"
                    value={m.target}
                    disabled={readOnly}
                    placeholder="Choose a field"
                    onValueChange={(v) => update(i, { target: v, detection: "manual" })}
                    options={TARGET_FIELDS.map((t) => ({ value: t, label: t }))}
                  />
                </Td>
                <Td>{m.target ? <StatusPill tone={m.detection === "auto" ? "good" : "neutral"}>{m.detection === "auto" ? "Auto-detected" : "Manual"}</StatusPill> : <StatusPill tone="warn">Not mapped</StatusPill>}</Td>
                {readOnly ? null : (
                  <Td>
                    <Button variant="ghost" size="icon" className="size-8" aria-label={`Remove mapping for ${m.source || `row ${i + 1}`}`} onClick={() => onChange(mapping.filter((_, j) => j !== i))}>
                      <Trash2 />
                    </Button>
                  </Td>
                )}
              </Tr>
            ))}
          </tbody>
        </Table>
      </div>
      {readOnly ? null : (
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onClick={() => onChange([...mapping, { source: "", target: "", detection: "manual" }])}>
            <Plus /> Add mapping
          </Button>
          <Button variant="outline" size="sm" onClick={() => file.current?.click()}>
            <Upload /> Upload sample CSV to auto-detect
          </Button>
          <input ref={file} type="file" accept=".csv,text/csv,text/plain" className="sr-only" tabIndex={-1} aria-hidden onChange={(e) => onFile(e.target.files?.[0])} />
        </div>
      )}
      <p aria-live="polite" className="text-xs text-muted-foreground">
        {status}
        {status && missing.length ? " " : ""}
        {missing.length ? `Still required: ${missing.join(", ")}.` : "All required fields are mapped."}
      </p>
    </div>
  );
}
