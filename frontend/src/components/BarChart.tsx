"use client";

import {
  BarChart as RechartsBarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { BarChartWidget } from "@/types/api";

const BAR_COLORS = ["#6366f1", "#22d3ee", "#f59e0b", "#34d399"];

function formatYValue(value: number, key: string): string {
  if (key === "rw") return `${(value * 100).toFixed(2)}%`;
  if (Math.abs(value) >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(1)}B`;
  if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (Math.abs(value) >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return value.toLocaleString("ko-KR", { maximumFractionDigits: 4 });
}

export default function BarChart({ widget }: { widget: BarChartWidget }) {
  const { title, xKey, yKeys, yLabels, data } = widget;

  if (!data || data.length === 0) {
    return (
      <div className="bg-navy-900 border border-surface-border rounded-xl px-4 py-3 text-slate-500 text-sm">
        {title} — 데이터 없음
      </div>
    );
  }

  return (
    <div className="bg-navy-900 border border-surface-border rounded-xl overflow-hidden">
      {title && (
        <div className="px-4 py-2.5 border-b border-surface-border text-xs font-medium text-slate-400 uppercase tracking-wide">
          {title}
        </div>
      )}
      <div className="px-4 py-4">
        <ResponsiveContainer width="100%" height={260}>
          <RechartsBarChart data={data} margin={{ top: 4, right: 16, left: 8, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis
              dataKey={xKey}
              tick={{ fill: "#64748b", fontSize: 11 }}
              axisLine={{ stroke: "#334155" }}
              tickLine={false}
            />
            <YAxis
              tickFormatter={(v) =>
                yKeys.length === 1 ? formatYValue(v as number, yKeys[0]) : String(v)
              }
              tick={{ fill: "#64748b", fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              width={60}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "#0f172a",
                border: "1px solid #1e293b",
                borderRadius: "8px",
                fontSize: "12px",
                color: "#e2e8f0",
              }}
              formatter={(value: unknown, name: string | number | undefined) => {
                const key = String(name ?? "");
                return [formatYValue(value as number, key), yLabels[key] ?? key] as [string, string];
              }}
              labelStyle={{ color: "#94a3b8" }}
            />
            {yKeys.length > 1 && (
              <Legend
                formatter={(value) => yLabels[value] ?? value}
                wrapperStyle={{ fontSize: "11px", paddingTop: "8px" }}
              />
            )}
            {yKeys.map((key, i) => (
              <Bar
                key={key}
                dataKey={key}
                name={key}
                fill={BAR_COLORS[i % BAR_COLORS.length]}
                radius={[3, 3, 0, 0]}
                maxBarSize={48}
              />
            ))}
          </RechartsBarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
