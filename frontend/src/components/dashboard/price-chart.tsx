"use client";

import { useEffect, useState } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import { getPriceSeries, type PriceSeries, type TrendSignal, type Calibration } from "@/lib/api";
import { unitConversion, convertPrice, fmtPrice } from "./commodity-data";

interface Props {
  commodityId: string;
  lead: TrendSignal;
  calibration?: Calibration;
}

interface DataPoint {
  date: string;
  price: number;
}

function formatDate(d: string): string {
  const parts = d.split("-");
  const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  const month = months[parseInt(parts[1] ?? "0", 10) - 1] ?? parts[1] ?? "";
  if (parts.length === 2) return `${month} '${(parts[0] ?? "").slice(2)}`;
  return `${month} ${parts[2] ?? ""}`;
}

export default function PriceChart({ commodityId, lead, calibration }: Props) {
  const [state, setState] = useState<{ series: PriceSeries | null; loading: boolean }>({
    series: null,
    loading: true,
  });

  useEffect(() => {
    let cancelled = false;
    getPriceSeries(commodityId, lead.source, lead.market)
      .then((res) => { if (!cancelled) setState({ series: res.data, loading: false }); })
      .catch(() => { if (!cancelled) setState({ series: null, loading: false }); });
    return () => { cancelled = true; };
  }, [commodityId, lead.source, lead.market]);

  const { series, loading } = state;

  if (loading) {
    return (
      <div className="flex h-[180px] items-center justify-center">
        <p className="text-xs text-muted-foreground">Loading chart...</p>
      </div>
    );
  }

  if (!series || series.prices.length < 3) return null;

  // Convert all prices using the unit from the lead signal (e.g. CWT → lb)
  const conv = unitConversion(lead.unit);

  const data: DataPoint[] = series.prices.map((price, i) => ({
    date: series.dates[i] ?? "",
    price: Math.round(price * conv.factor * 100) / 100,
  }));

  const prices = data.map((d) => d.price);
  const minPrice = Math.min(...prices);
  const maxPrice = Math.max(...prices);
  const padding = (maxPrice - minPrice) * 0.15 || 0.1;

  // Comparison windows
  const horizon = lead.horizon;
  const recentStart = Math.max(0, data.length - horizon);
  const priorStart = Math.max(0, data.length - horizon * 2);

  // Baseline = prior window average, converted
  const baseline = convertPrice(lead.previous_price, lead.unit);

  // Normal range band: baseline ± 1 std
  let bandUpper: number | undefined;
  let bandLower: number | undefined;
  if (calibration && calibration.std_change > 0) {
    const stdPct = calibration.std_change / 100;
    bandUpper = baseline * (1 + stdPct);
    bandLower = baseline * (1 - stdPct);
  }

  // Tick labels: first, middle, last
  const tickIndices = [0, Math.floor(data.length / 2), data.length - 1];
  const ticks = [...new Set(
    tickIndices.map((i) => data[i]?.date).filter((d): d is string => d != null)
  )];

  return (
    <div className="mt-2 mb-1">
      <ResponsiveContainer width="100%" height={180}>
        <AreaChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          {/* Prior window shading */}
          {priorStart < recentStart && (
            <ReferenceArea
              x1={data[priorStart]?.date}
              x2={data[recentStart]?.date}
              fill="#94a3b8"
              fillOpacity={0.08}
              strokeOpacity={0}
            />
          )}
          {/* Recent window shading */}
          <ReferenceArea
            x1={data[recentStart]?.date}
            x2={data[data.length - 1]?.date}
            fill={lead.change_pct < 0 ? "#22c55e" : "#ef4444"}
            fillOpacity={0.08}
            strokeOpacity={0}
          />
          {/* Normal range band */}
          {bandUpper !== undefined && bandLower !== undefined && (
            <ReferenceArea
              y1={bandLower}
              y2={bandUpper}
              fill="#94a3b8"
              fillOpacity={0.12}
              strokeOpacity={0}
              label={{ value: "normal range", position: "insideTopRight", fontSize: 10, fill: "#94a3b8" }}
            />
          )}
          {/* Baseline */}
          <ReferenceLine
            y={baseline}
            stroke="#94a3b8"
            strokeDasharray="3 3"
            strokeWidth={1}
            label={{ value: `baseline ${fmtPrice(baseline)}`, position: "insideTopLeft", fontSize: 10, fill: "#94a3b8", offset: 2 }}
          />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 10, fill: "#94a3b8" }}
            tickLine={false}
            axisLine={false}
            ticks={ticks}
            tickFormatter={formatDate}
          />
          <YAxis
            domain={[minPrice - padding, maxPrice + padding]}
            tick={{ fontSize: 10, fill: "#94a3b8" }}
            tickLine={false}
            axisLine={false}
            tickFormatter={fmtPrice}
            width={50}
          />
          <Tooltip
            content={({ active, payload }) => {
              if (!active || !payload?.[0]) return null;
              const d = payload[0].payload as DataPoint;
              return (
                <div className="rounded border bg-background px-2 py-1 text-xs shadow-sm">
                  <p className="font-medium">{fmtPrice(d.price)}{conv.label ? `/${conv.label}` : ""}</p>
                  <p className="text-muted-foreground">{formatDate(d.date)}</p>
                </div>
              );
            }}
          />
          <Area
            type="monotone"
            dataKey="price"
            stroke={lead.change_pct < 0 ? "#22c55e" : "#ef4444"}
            strokeWidth={2}
            fill={lead.change_pct < 0 ? "#22c55e" : "#ef4444"}
            fillOpacity={0.1}
            dot={false}
            activeDot={{ r: 3, strokeWidth: 0 }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
