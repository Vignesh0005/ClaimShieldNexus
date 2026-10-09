"use client";

import * as React from "react";
import * as SelectPrimitive from "@radix-ui/react-select";
import { Check, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

export interface Option {
  value: string;
  label: string;
}

// Single-purpose select: every use in this app is a flat list of options.
export function Select({
  value,
  onValueChange,
  options,
  label,
  id,
  className,
  disabled,
  placeholder,
}: {
  value: string;
  onValueChange: (v: string) => void;
  options: Option[];
  label: string;
  id?: string;
  className?: string;
  disabled?: boolean;
  placeholder?: string;
}) {
  return (
    // Radix can emit an empty value when the option list changes under a controlled value; no select here has an empty option.
    <SelectPrimitive.Root value={value} onValueChange={(v) => v !== "" && onValueChange(v)} disabled={disabled}>
      <SelectPrimitive.Trigger
        id={id}
        aria-label={label}
        className={cn(
          "inline-flex h-9 w-full items-center justify-between gap-2 rounded-md border border-input bg-card px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60 [&>span]:truncate",
          className,
        )}
      >
        <SelectPrimitive.Value placeholder={placeholder} />
        <SelectPrimitive.Icon>
          <ChevronDown className="size-4 text-muted-foreground" aria-hidden />
        </SelectPrimitive.Icon>
      </SelectPrimitive.Trigger>
      <SelectPrimitive.Portal>
        <SelectPrimitive.Content
          position="popper"
          sideOffset={4}
          className="z-50 max-h-72 min-w-[var(--radix-select-trigger-width)] overflow-hidden rounded-md border bg-popover text-popover-foreground shadow-lg"
        >
          <SelectPrimitive.Viewport className="p-1">
            {options.map((o) => (
              <SelectPrimitive.Item
                key={o.value}
                value={o.value}
                className="relative flex cursor-default select-none items-center rounded-sm py-1.5 pl-7 pr-3 text-sm outline-none data-[highlighted]:bg-accent"
              >
                <SelectPrimitive.ItemIndicator className="absolute left-2">
                  <Check className="size-3.5" aria-hidden />
                </SelectPrimitive.ItemIndicator>
                <SelectPrimitive.ItemText>{o.label}</SelectPrimitive.ItemText>
              </SelectPrimitive.Item>
            ))}
          </SelectPrimitive.Viewport>
        </SelectPrimitive.Content>
      </SelectPrimitive.Portal>
    </SelectPrimitive.Root>
  );
}
