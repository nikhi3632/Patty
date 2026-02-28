import type { Commodity, Trend, TrendSignal } from "@/lib/api";

export function titleCase(s: string): string {
  return s.replace(/\b\w/g, (c) => c.toUpperCase());
}

export interface CommodityViewModel {
  commodity: Commodity;
  trend: Trend | null;
  signal: string;
  leadChangePct: number | null;
}

export function leadSignal(trend: Trend): TrendSignal | null {
  if (trend.trend_signals.length === 0) return null;
  return trend.trend_signals.reduce((best, s) =>
    Math.abs(s.z_score) > Math.abs(best.z_score) ? s : best
  );
}

export function signalColor(signal: string): string {
  if (signal.includes("down")) return "text-green-600";
  if (signal.includes("up")) return "text-red-600";
  return "text-muted-foreground";
}

export function signalBorder(signal: string): string {
  if (signal.includes("down")) return "border-l-green-500";
  if (signal.includes("up")) return "border-l-red-500";
  return "border-l-muted-foreground/20";
}

export function signalLabel(signal: string): string {
  switch (signal) {
    case "strong_up": return "Strong increase";
    case "moderate_up": return "Moderate increase";
    case "strong_down": return "Strong decrease";
    case "moderate_down": return "Moderate decrease";
    case "mixed": return "Mixed signals";
    default: return "Stable";
  }
}

/** User-facing headline: what the z-score means for a buyer. */
export function signalHeadline(signal: string): string {
  if (signal.includes("down")) return "Unusually low";
  if (signal.includes("up")) return "Unusually high";
  if (signal === "mixed") return "Mixed signals";
  return "Normal range";
}

export function trendSummary(trend: Trend): string {
  const s = leadSignal(trend);
  if (!s) return "No price data available";
  const dir = s.change_pct > 0 ? "Up" : "Down";
  const source = s.source === "mars" ? "MARS wholesale" : "NASS national";
  return `${dir} over the past ${s.horizon} ${s.source === "mars" ? "market days" : "months"} (${source})`;
}

/** Get the conversion factor to normalize a NASS unit to per-lb. */
export function unitConversion(unit: string | null | undefined): { factor: number; label: string } {
  if (!unit) return { factor: 1, label: "" };
  const raw = unit.replace(/^\$\s*\/\s*/, "").trim().toUpperCase();
  if (raw === "CWT") return { factor: 1 / 100, label: "lb" };
  return { factor: 1, label: raw.toLowerCase() };
}

/** Convert a raw price using the unit conversion. */
export function convertPrice(price: number, unit: string | null | undefined): number {
  return price * unitConversion(unit).factor;
}

export function fmtPrice(n: number): string {
  return n < 1 ? `$${n.toFixed(2)}` : n < 10 ? `$${n.toFixed(2)}` : `$${n.toFixed(1)}`;
}

/** Price detail line.
 *  NASS: "$0.74 → $1.24/lb, +68% over 5 months" (real per-unit prices)
 *  MARS: "Down over 5 market days" (no dollar amounts — prices are per-carton averages across mixed package sizes)
 */
export function priceDetail(trend: Trend): string | null {
  const s = leadSignal(trend);
  if (!s) return null;
  const sign = s.change_pct > 0 ? "+" : "";
  const period = s.source === "mars" ? "market days" : "months";

  if (s.source === "mars") {
    const dir = s.change_pct > 0 ? "Up" : "Down";
    return `${dir} ${sign}${s.change_pct.toFixed(0)}% over ${s.horizon} ${period}`;
  }

  const conv = unitConversion(s.unit);
  const prev = s.previous_price * conv.factor;
  const curr = s.current_price * conv.factor;
  const unitStr = conv.label ? `/${conv.label}` : "";
  return `${fmtPrice(prev)} → ${fmtPrice(curr)}${unitStr}, ${sign}${s.change_pct.toFixed(0)}% over ${s.horizon} ${period}`;
}

const SIGNAL_SORT_ORDER: Record<string, number> = {
  strong_down: 0,
  moderate_down: 1,
  strong_up: 2,
  moderate_up: 3,
  mixed: 4,
  stable: 5,
};

function signalSortKey(signal: string): number {
  return SIGNAL_SORT_ORDER[signal] ?? 6;
}

const ACTIONABLE_SIGNALS = new Set([
  "strong_down", "moderate_down", "strong_up", "moderate_up", "mixed",
]);

export function partitionViewModels(vms: CommodityViewModel[]) {
  const actionable: CommodityViewModel[] = [];
  const stable: CommodityViewModel[] = [];
  const pending: CommodityViewModel[] = [];

  for (const vm of vms) {
    if (ACTIONABLE_SIGNALS.has(vm.signal)) actionable.push(vm);
    else if (vm.signal === "none") pending.push(vm);
    else stable.push(vm);
  }

  return { actionable, stable, pending };
}

export function buildCommodityViewModels(
  commodities: Commodity[],
  trends: Trend[]
): CommodityViewModel[] {
  const tracked = commodities.filter((c) => c.status === "tracked");

  return tracked
    .map((commodity) => {
      const trend = trends.find((t) => t.commodity_id === commodity.commodity_id) ?? null;
      const signal = trend?.signal ?? "none";
      const lead = trend ? leadSignal(trend) : null;

      return {
        commodity,
        trend,
        signal,
        leadChangePct: lead ? lead.change_pct : null,
      };
    })
    .sort((a, b) => {
      const orderDiff = signalSortKey(a.signal) - signalSortKey(b.signal);
      if (orderDiff !== 0) return orderDiff;
      // Within same signal type, sort by magnitude of change
      const aMag = Math.abs(a.leadChangePct ?? 0);
      const bMag = Math.abs(b.leadChangePct ?? 0);
      return bMag - aMag;
    });
}
