"use client";

import type { ReactNode } from "react";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Separator } from "@/components/ui/separator";

interface Props {
  expanded: boolean;
  onToggle: () => void;
  trigger: ReactNode;
  children: ReactNode;
  className?: string;
}

export default function AccordionCard({
  expanded,
  onToggle,
  trigger,
  children,
  className = "",
}: Props) {
  return (
    <Collapsible open={expanded} onOpenChange={onToggle}>
      <div
        className={`rounded-lg border transition-shadow ${
          expanded ? "shadow-sm" : ""
        } ${className}`}
      >
        <CollapsibleTrigger className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-muted/30 transition-colors rounded-lg">
          {trigger}
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="px-4 pb-4 space-y-4">
            <Separator />
            {children}
          </div>
        </CollapsibleContent>
      </div>
    </Collapsible>
  );
}
