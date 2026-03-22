"use client";

import { formatKRW } from "@/lib/utils";
import { TrendingUp, Scale, BookOpen, ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { RwaResult } from "@/types/api";

interface Props {
  result: RwaResult;
  exposure: number;
  categoryLabel: string;
  entityLabel: string;
}

function getRiskColor(rw: number) {
  if (rw <= 0.20) return { text: "text-emerald-400", bg: "bg-emerald-400/10", border: "border-emerald-500/30", bar: "bg-emerald-500" };
  if (rw <= 0.50) return { text: "text-sky-400", bg: "bg-sky-400/10", border: "border-sky-500/30", bar: "bg-sky-500" };
  if (rw <= 1.00) return { text: "text-amber-400", bg: "bg-amber-400/10", border: "border-amber-500/30", bar: "bg-amber-500" };
  if (rw <= 1.50) return { text: "text-orange-400", bg: "bg-orange-400/10", border: "border-orange-500/30", bar: "bg-orange-500" };
  return { text: "text-red-400", bg: "bg-red-400/10", border: "border-red-500/30", bar: "bg-red-500" };
}

export default function RwaResultCard({ result, exposure, categoryLabel, entityLabel }: Props) {
  const color = getRiskColor(result.risk_weight);
  const capitalCharge = result.rwa * 0.08; // 8% 최소 자기자본비율 기준
  const barWidth = Math.min((result.risk_weight / 12.5) * 100, 100); // 최대 1250% 기준

  return (
    <div className="space-y-3">
      {/* Risk Weight Card */}
      <div className={cn("rounded-xl border p-4", color.bg, color.border)}>
        <div className="text-xs text-slate-400 mb-1">위험가중치</div>
        <div className={cn("text-4xl font-bold tracking-tight", color.text)}>
          {result.risk_weight_pct}
        </div>
        {/* Risk bar */}
        <div className="mt-3 h-1.5 bg-navy-900/60 rounded-full overflow-hidden">
          <div
            className={cn("h-full rounded-full transition-all duration-700", color.bar)}
            style={{ width: `${barWidth}%` }}
          />
        </div>
        <div className="flex justify-between text-xs text-slate-600 mt-1">
          <span>0%</span>
          <span>1,250%</span>
        </div>
      </div>

      {/* RWA & Exposure */}
      <div className="grid grid-cols-1 gap-2">
        <MetricRow
          icon={<ArrowRight className="w-3.5 h-3.5" />}
          label="익스포져"
          value={formatKRW(exposure)}
          valueClass="text-slate-300"
        />
        <div className="border-t border-surface-border" />
        <MetricRow
          icon={<TrendingUp className="w-3.5 h-3.5 text-brand-400" />}
          label="위험가중자산 (RWA)"
          value={formatKRW(result.rwa)}
          valueClass="text-brand-300 font-semibold"
        />
        <MetricRow
          icon={<Scale className="w-3.5 h-3.5 text-amber-400" />}
          label="최소 자기자본 (8% 기준)"
          value={formatKRW(capitalCharge)}
          valueClass="text-amber-300"
        />
      </div>

      {/* Regulatory Basis */}
      <div className="bg-navy-900/60 border border-surface-border rounded-lg px-3 py-2.5">
        <div className="flex items-start gap-2">
          <BookOpen className="w-3.5 h-3.5 text-slate-500 flex-none mt-0.5" />
          <div>
            <div className="text-xs text-slate-500 mb-0.5">적용 근거</div>
            <div className="text-xs text-slate-300 leading-relaxed">{result.basis}</div>
          </div>
        </div>
      </div>

      {/* Entity info */}
      <div className="text-xs text-slate-600 space-y-0.5 pt-1">
        <div>유형: <span className="text-slate-500">{categoryLabel}</span></div>
        <div>구분: <span className="text-slate-500">{entityLabel}</span></div>
      </div>
    </div>
  );
}

function MetricRow({
  icon,
  label,
  value,
  valueClass,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  valueClass?: string;
}) {
  return (
    <div className="flex items-center justify-between gap-2 py-0.5">
      <div className="flex items-center gap-1.5 text-xs text-slate-500">
        {icon}
        {label}
      </div>
      <span className={cn("text-sm tabular-nums", valueClass)}>{value}</span>
    </div>
  );
}
