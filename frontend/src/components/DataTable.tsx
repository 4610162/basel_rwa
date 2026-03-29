"use client";

import { DataTableWidget } from "@/types/api";

function formatValue(val: unknown, colKey: string): string {
  if (val === null || val === undefined) return "—";
  if (typeof val === "number") {
    if (colKey === "rw") return `${(val * 100).toFixed(2)}%`;
    // Large numbers: add commas
    if (Math.abs(val) >= 1000) return val.toLocaleString("ko-KR", { maximumFractionDigits: 0 });
    return val.toLocaleString("ko-KR", { maximumFractionDigits: 4 });
  }
  return String(val);
}

export default function DataTable({ widget }: { widget: DataTableWidget }) {
  const { title, columns, columnLabels, rows } = widget;

  if (!rows || rows.length === 0) {
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
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-surface-border">
              {columns.map((col) => (
                <th
                  key={col}
                  className="px-4 py-2 text-left text-xs font-medium text-slate-500 uppercase tracking-wide whitespace-nowrap"
                >
                  {columnLabels[col] ?? col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr
                key={i}
                className="border-b border-surface-border/50 hover:bg-navy-800/50 transition-colors"
              >
                {columns.map((col) => (
                  <td
                    key={col}
                    className="px-4 py-2 text-slate-300 whitespace-nowrap tabular-nums"
                  >
                    {formatValue(row[col], col)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
