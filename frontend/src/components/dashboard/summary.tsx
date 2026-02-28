"use client";

import { Card, CardContent } from "@/components/ui/card";
import { titleCase, type CommodityViewModel } from "./commodity-data";

interface Props {
  actionable: CommodityViewModel[];
  active: number;
}

function nameList(vms: CommodityViewModel[]): string {
  const names = vms.map((vm) =>
    titleCase(vm.commodity.commodities?.parent ?? vm.commodity.raw_ingredient_name)
  );
  if (names.length <= 2) return names.join(" and ");
  return `${names.slice(0, 2).join(", ")}, and ${names.length - 2} more`;
}

export default function Summary({ actionable, active }: Props) {
  if (active === 0) {
    return (
      <Card className="border-l-4 border-l-muted-foreground/30">
        <CardContent className="py-4">
          <p className="text-sm font-medium leading-relaxed">
            Computing price trends...
          </p>
        </CardContent>
      </Card>
    );
  }

  if (actionable.length === 0) {
    return (
      <Card className="border-l-4 border-l-muted-foreground/30">
        <CardContent className="py-4">
          <p className="text-sm font-medium leading-relaxed">
            All {active} monitored ingredients within their normal price range.
          </p>
        </CardContent>
      </Card>
    );
  }

  const down = actionable.filter((vm) => vm.signal.includes("down"));
  const up = actionable.filter((vm) => vm.signal.includes("up"));
  const hasDown = down.length > 0;

  let sentence: string;
  if (down.length > 0 && up.length === 0) {
    sentence = `${nameList(down)} priced below normal range — good time to negotiate.`;
  } else if (up.length > 0 && down.length === 0) {
    sentence = `${nameList(up)} priced above normal range — watch your costs.`;
  } else {
    sentence = `${nameList(down)} unusually low, ${nameList(up)} unusually high.`;
  }

  return (
    <Card className={`border-l-4 ${hasDown ? "border-l-green-500" : "border-l-red-500"}`}>
      <CardContent className="py-4">
        <p className="text-sm font-medium leading-relaxed">{sentence}</p>
        <p className="mt-1 text-xs text-muted-foreground">
          {actionable.length} of {active} monitored ingredients outside normal range
        </p>
      </CardContent>
    </Card>
  );
}
