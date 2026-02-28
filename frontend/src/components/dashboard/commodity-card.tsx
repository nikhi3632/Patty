"use client";

import { TrendingDown, TrendingUp, Minus } from "lucide-react";
import type { Calibration } from "@/lib/api";
import type { CommodityViewModel } from "./commodity-data";
import { leadSignal, signalBorder, signalColor, signalHeadline, titleCase } from "./commodity-data";
import AccordionCard from "./accordion-card";
import TrendDetail from "./trend-detail";

interface Props {
  vm: CommodityViewModel;
  expanded: boolean;
  onToggle: () => void;
  calibration?: Calibration;
  systemView: boolean;
}

function SignalIcon({ signal }: { signal: string }) {
  if (signal.includes("down")) return <TrendingDown className="h-4 w-4" />;
  if (signal.includes("up")) return <TrendingUp className="h-4 w-4" />;
  return <Minus className="h-4 w-4" />;
}

export default function CommodityCard({
  vm,
  expanded,
  onToggle,
  calibration,
  systemView,
}: Props) {
  const parent = vm.commodity.commodities?.parent ?? vm.commodity.raw_ingredient_name;
  const hasTrend = vm.trend != null;
  const lead = vm.trend ? leadSignal(vm.trend) : null;
  const changePct = lead ? lead.change_pct : null;

  const trigger = (
    <div className="flex items-center justify-between w-full">
      <div className="flex items-center gap-3 min-w-0">
        <div className={signalColor(vm.signal)}>
          <SignalIcon signal={vm.signal} />
        </div>
        <div className="min-w-0">
          <p className="font-medium text-sm truncate">{titleCase(parent)}</p>
          <p className={`text-xs ${signalColor(vm.signal)}`}>
            {hasTrend ? signalHeadline(vm.signal) : "Pending"}
          </p>
        </div>
      </div>
      {changePct != null && vm.signal !== "stable" && (
        <span className={`text-lg font-semibold tabular-nums ${signalColor(vm.signal)}`}>
          {changePct > 0 ? "+" : ""}{changePct.toFixed(0)}%
        </span>
      )}
    </div>
  );

  return (
    <AccordionCard
      expanded={expanded}
      onToggle={onToggle}
      trigger={trigger}
      className={`border-l-4 ${signalBorder(vm.signal)}`}
    >
      {vm.trend ? (
        <TrendDetail
          trend={vm.trend}
          calibration={calibration}
          systemView={systemView}
        />
      ) : (
        <p className="text-sm text-muted-foreground">No trend data yet.</p>
      )}
    </AccordionCard>
  );
}
