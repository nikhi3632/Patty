"use client";

import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import type { Trend, Calibration } from "@/lib/api";
import { leadSignal, priceDetail, signalLabel } from "./commodity-data";
import PriceChart from "./price-chart";

interface Props {
  trend: Trend;
  calibration?: Calibration;
  systemView: boolean;
}

function lastCheckedLabel(trend: Trend): string {
  const lead = leadSignal(trend);
  if (!lead) return "";
  const source = lead.source === "mars" ? "MARS wholesale" : "NASS national";
  const date = new Date(trend.computed_at);
  const month = date.toLocaleString("en-US", { month: "short", year: "numeric" });
  return `${source} · last checked ${month}`;
}

export default function TrendDetail({ trend, calibration, systemView }: Props) {
  const lead = leadSignal(trend);
  const isStable = trend.signal === "stable";

  // Stable items: minimal detail in normal view, full detail in system view
  if (isStable && !systemView) {
    return (
      <div className="space-y-1">
        <p className="text-sm text-muted-foreground">
          Price is within the expected range. No action needed.
        </p>
        <p className="text-xs text-muted-foreground/70">
          {lastCheckedLabel(trend)}
        </p>
      </div>
    );
  }

  const detail = priceDetail(trend);

  return (
    <div className="space-y-3">
      {/* Actionable: show price story */}
      {!isStable && detail && (
        <p className="text-sm text-foreground">{detail}</p>
      )}

      {/* Stable + system view: show price story too */}
      {isStable && systemView && detail && (
        <p className="text-sm text-foreground">{detail}</p>
      )}

      {/* Price chart */}
      {lead && (
        <PriceChart
          commodityId={trend.commodity_id}
          lead={lead}
          calibration={calibration}
        />
      )}

      {lead && (
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary" className="text-xs">
            {signalLabel(trend.signal)}
          </Badge>
          {!isStable && lead.z_score !== 0 && (
            <span className="text-xs text-muted-foreground">
              typical: ±{Math.abs(Math.round(lead.change_pct / lead.z_score))}%
            </span>
          )}
          {lead.date_range && (
            <span className="text-xs text-muted-foreground">
              {lead.source.toUpperCase()}
              {lead.market ? ` · ${lead.market}` : ""}
              {` · ${lead.date_range}`}
            </span>
          )}
        </div>
      )}

      {systemView && calibration && (
        <>
          <Separator />
          <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs text-muted-foreground">
            <p>Volatility: {calibration.volatility}</p>
            <p>ACF lag: {calibration.autocorrelation_lag}</p>
            <p>Horizon: {calibration.dynamic_horizon}</p>
            <p>Mean change: {calibration.mean_change}%</p>
            <p>Std change: {calibration.std_change}%</p>
            <p>Data points: {calibration.data_points_used}</p>
            <p>Source: {calibration.source}</p>
            {calibration.market && <p>Market: {calibration.market}</p>}
            <p>z-score: {lead?.z_score}</p>
          </div>
        </>
      )}

      {systemView && trend.trend_signals.length > 1 && (
        <>
          <Separator />
          <p className="text-xs font-medium text-muted-foreground">All signals</p>
          <div className="space-y-1">
            {trend.trend_signals.map((s) => (
              <p key={s.id} className="text-xs text-muted-foreground">
                {s.source.toUpperCase()}: ${s.current_price} (was ${s.previous_price}) · {s.change_pct}% · z={s.z_score} · horizon={s.horizon}
                {s.unit ? ` · ${s.unit}` : ""}
              </p>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
