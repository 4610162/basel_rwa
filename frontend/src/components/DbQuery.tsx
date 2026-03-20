"use client";

import { useState, useEffect } from "react";
import { Search, RotateCcw, AlertCircle, InboxIcon } from "lucide-react";
import {
  queryDb,
  getBaseYmList,
  DbQueryRequest,
  DbQueryResponse,
  DbQuerySummary,
  DbQueryRow,
} from "@/lib/api";

// ─── 숫자 포매팅 헬퍼 ─────────────────────────────────────────────────────────

function formatAmount(value: number): string {
  return new Intl.NumberFormat("ko-KR").format(Math.round(value));
}

function formatRw(value: number | null): string {
  if (value === null || value === undefined) return "-";
  return (value * 100).toFixed(2) + "%";
}

// ─── 요약 카드 ────────────────────────────────────────────────────────────────

function SummaryCard({ summary }: { summary: DbQuerySummary }) {
  const cards = [
    { label: "조회 건수", value: summary.record_count.toLocaleString("ko-KR") + " 건" },
    { label: "총 BS잔액", value: formatAmount(summary.total_bs_balance) + " 원" },
    { label: "총 EAD", value: formatAmount(summary.total_ead) + " 원" },
    { label: "총 RWA", value: formatAmount(summary.total_rwa) + " 원" },
    { label: "평균 RW율 (가중)", value: formatRw(summary.avg_rw) },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
      {cards.map((c) => (
        <div
          key={c.label}
          className="bg-navy-800 border border-surface-border rounded-lg p-3 flex flex-col gap-1"
        >
          <span className="text-slate-400 text-xs">{c.label}</span>
          <span className="text-white text-sm font-semibold break-all">{c.value}</span>
        </div>
      ))}
    </div>
  );
}

// ─── 상세 테이블 ──────────────────────────────────────────────────────────────

function DetailTable({ rows }: { rows: DbQueryRow[] }) {
  if (rows.length === 0) return null;

  const headers = ["기준월", "대출번호", "영업상품코드", "BS잔액", "EAD", "RWA", "RW율"];

  function formatBaseYm(ym: string): string {
    if (ym.length === 6) return ym.slice(0, 4) + "-" + ym.slice(4);
    return ym;
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-surface-border">
      <table className="w-full text-sm text-left">
        <thead className="bg-navy-800 text-slate-400 text-xs uppercase">
          <tr>
            {headers.map((h) => (
              <th key={h} className="px-4 py-3 whitespace-nowrap font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-surface-border">
          {rows.map((row, i) => (
            <tr key={i} className="bg-navy-900 hover:bg-navy-800 transition-colors">
              <td className="px-4 py-2.5 whitespace-nowrap text-slate-300">{formatBaseYm(row.base_ym)}</td>
              <td className="px-4 py-2.5 whitespace-nowrap text-slate-300">{row.loan_no}</td>
              <td className="px-4 py-2.5 whitespace-nowrap text-slate-300">{row.product_code}</td>
              <td className="px-4 py-2.5 whitespace-nowrap text-right text-slate-300">{formatAmount(row.bs_balance)}</td>
              <td className="px-4 py-2.5 whitespace-nowrap text-right text-slate-300">{formatAmount(row.ead)}</td>
              <td className="px-4 py-2.5 whitespace-nowrap text-right text-slate-300">{formatAmount(row.rwa)}</td>
              <td className="px-4 py-2.5 whitespace-nowrap text-right text-slate-300">{formatRw(row.rw)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─── 메인 컴포넌트 ────────────────────────────────────────────────────────────

const INITIAL_FORM: DbQueryRequest = {
  query_type: "loan_no",
  base_ym: "",
  loan_no: "",
  product_code: "",
};

export default function DbQuery() {
  const [form, setForm] = useState<DbQueryRequest>(INITIAL_FORM);
  const [baseYmOptions, setBaseYmOptions] = useState<string[]>([]);
  const [result, setResult] = useState<DbQueryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 컴포넌트 마운트 시 기준월 목록 fetch
  useEffect(() => {
    getBaseYmList().then((list) => {
      setBaseYmOptions(list);
      if (list.length > 0) {
        setForm((f) => ({ ...f, base_ym: list[0] }));
      }
    });
  }, []);

  function handleReset() {
    setForm({ ...INITIAL_FORM, base_ym: baseYmOptions[0] ?? "" });
    setResult(null);
    setError(null);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const req: DbQueryRequest = {
        query_type: form.query_type,
        base_ym: form.base_ym,
        loan_no: form.query_type === "loan_no" ? (form.loan_no || null) : null,
        product_code: form.query_type === "product_code" ? (form.product_code || null) : null,
      };
      const res = await queryDb(req);
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "알 수 없는 오류");
    } finally {
      setLoading(false);
    }
  }

  const isSubmitDisabled = loading || !form.base_ym;

  return (
    <div className="h-full overflow-y-auto bg-navy-950">
      <div className="max-w-5xl mx-auto px-4 py-6 space-y-6">
        {/* 조회 폼 */}
        <div className="bg-navy-900 border border-surface-border rounded-xl p-5">
          <h2 className="text-white font-semibold text-base mb-4">조회 조건</h2>
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* 조회 기준 선택 */}
            <div>
              <label className="block text-slate-400 text-xs mb-2">조회 기준</label>
              <div className="flex gap-3">
                {(["loan_no", "product_code"] as const).map((type) => (
                  <label
                    key={type}
                    className={`flex items-center gap-2 px-4 py-2 rounded-lg border cursor-pointer text-sm transition-all ${
                      form.query_type === type
                        ? "border-brand-600 bg-brand-600/10 text-brand-400"
                        : "border-surface-border text-slate-400 hover:border-slate-500"
                    }`}
                  >
                    <input
                      type="radio"
                      className="hidden"
                      value={type}
                      checked={form.query_type === type}
                      onChange={() =>
                        setForm((f) => ({ ...f, query_type: type, loan_no: "", product_code: "" }))
                      }
                    />
                    {type === "loan_no" ? "대출번호 기준" : "영업상품코드 기준"}
                  </label>
                ))}
              </div>
            </div>

            {/* 입력 필드 */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {/* 기준월 드롭다운 */}
              <div>
                <label className="block text-slate-400 text-xs mb-1.5">
                  기준월 <span className="text-red-400">*</span>
                </label>
                <select
                  value={form.base_ym}
                  onChange={(e) => setForm((f) => ({ ...f, base_ym: e.target.value }))}
                  className="w-full bg-navy-800 border border-surface-border rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-brand-500 transition-colors"
                  required
                >
                  {baseYmOptions.length === 0 && (
                    <option value="" disabled>불러오는 중...</option>
                  )}
                  {baseYmOptions.map((ym) => (
                    <option key={ym} value={ym}>
                      {ym}
                    </option>
                  ))}
                </select>
              </div>

              {/* 대출번호 or 영업상품코드 (선택 입력) */}
              {form.query_type === "loan_no" ? (
                <div>
                  <label className="block text-slate-400 text-xs mb-1.5">
                    대출번호 <span className="text-slate-600">(선택)</span>
                  </label>
                  <input
                    type="text"
                    placeholder="미입력 시 전체 조회"
                    value={form.loan_no ?? ""}
                    onChange={(e) => setForm((f) => ({ ...f, loan_no: e.target.value }))}
                    className="w-full bg-navy-800 border border-surface-border rounded-lg px-3 py-2 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-brand-500 transition-colors"
                  />
                </div>
              ) : (
                <div>
                  <label className="block text-slate-400 text-xs mb-1.5">
                    영업상품코드 <span className="text-slate-600">(선택)</span>
                  </label>
                  <input
                    type="text"
                    placeholder="미입력 시 전체 조회"
                    value={form.product_code ?? ""}
                    onChange={(e) => setForm((f) => ({ ...f, product_code: e.target.value }))}
                    className="w-full bg-navy-800 border border-surface-border rounded-lg px-3 py-2 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-brand-500 transition-colors"
                  />
                </div>
              )}
            </div>

            {/* 버튼 */}
            <div className="flex gap-2 pt-1">
              <button
                type="submit"
                disabled={isSubmitDisabled}
                className="flex items-center gap-2 px-5 py-2 rounded-lg bg-brand-600 text-white text-sm font-medium hover:bg-brand-500 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
              >
                <Search className="w-4 h-4" />
                {loading ? "조회 중..." : "조회"}
              </button>
              <button
                type="button"
                onClick={handleReset}
                className="flex items-center gap-2 px-4 py-2 rounded-lg border border-surface-border text-slate-400 text-sm hover:text-slate-200 hover:border-slate-500 transition-all"
              >
                <RotateCcw className="w-4 h-4" />
                초기화
              </button>
            </div>
          </form>
        </div>

        {/* 에러 */}
        {error && (
          <div className="flex items-start gap-3 bg-red-900/20 border border-red-500/30 rounded-xl p-4 text-sm text-red-400">
            <AlertCircle className="w-4 h-4 mt-0.5 flex-none" />
            <span>{error}</span>
          </div>
        )}

        {/* API 레벨 에러 */}
        {result && !result.success && (
          <div className="flex items-start gap-3 bg-red-900/20 border border-red-500/30 rounded-xl p-4 text-sm text-red-400">
            <AlertCircle className="w-4 h-4 mt-0.5 flex-none" />
            <span>[{result.error_code}] {result.message}</span>
          </div>
        )}

        {/* 결과 없음 */}
        {result && result.success && result.rows.length === 0 && (
          <div className="flex flex-col items-center justify-center gap-3 py-16 text-slate-500">
            <InboxIcon className="w-10 h-10" />
            <span className="text-sm">{result.message ?? "조회 결과가 없습니다."}</span>
          </div>
        )}

        {/* 조회 결과 */}
        {result && result.success && result.summary && (
          <div className="space-y-4">
            <SummaryCard summary={result.summary} />
            <DetailTable rows={result.rows} />
          </div>
        )}
      </div>
    </div>
  );
}
