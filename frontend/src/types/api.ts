export type ChatMode = "agent" | "data_analysis";
export type ChatRole = "user" | "assistant";

export interface RwaRequest {
  exposure_category: string;
  entity_type: string;
  exposure: number;
  entity_name?: string;
  external_credit_rating?: string;
  oecd_grade?: number;
  is_local_currency?: boolean;
  is_korea?: boolean;
  pse_category?: string;
  country_gov_external_credit_rating?: string;
  dd_grade?: string;
  cet1_ratio?: number;
  leverage_ratio?: number;
  is_foreign_currency?: boolean;
  is_trade_lc?: boolean;
  country_gov_oecd_grade?: number;
  issuing_bank_rw?: number;
  is_bank_equiv_regulated?: boolean;
  short_grade?: string;
  is_sme_legal?: boolean;
  annual_revenue_eok?: number;
  total_assets_eok?: number;
  country_floor_rw?: number;
  debtor_short_rw?: number;
  pf_stage?: string;
  pf_op_high_quality?: boolean;
  slotting_grade?: string;
  slotting_short_or_safe?: boolean;
  re_exposure_type?: string;
  ltv_ratio?: number;
  is_eligible?: boolean;
  borrower_risk_weight?: number;
  is_residential_exception?: boolean;
  has_construction_guarantee?: boolean;
  contractor_credit_rating?: string;
  guarantor_exposure?: number;
  ciu_approach?: string;
  weighted_avg_rw?: number;
  equity_type?: string;
  attachment_point?: number;
  detachment_point?: number;
  k_sa?: number;
  w?: number;
  p?: number;
}

export interface RwaResult {
  entity_type: string;
  risk_weight: number;
  risk_weight_pct: string;
  rwa: number;
  basis: string;
}

export interface SourceDoc {
  content: string;
  metadata: Record<string, unknown>;
}

export interface DbQueryRequest {
  query_type?: "loan_no" | "product_code" | null;
  base_ym: string;              // "YYYY-MM" 또는 "" (전체 기간)
  loan_no?: string | null;
  product_code?: string | null;
  product_code_nm?: string | null;  // 영업상품코드명 완전일치 필터
}

export interface DbQuerySummary {
  total_bs_balance: number;
  total_ead: number;
  total_rwa: number;
  avg_rw: number | null;
  avg_pd: number | null;
  avg_lgd: number | null;
  avg_ccf: number | null;
  record_count: number;
}

export interface DbQueryRow {
  base_ym: string;
  loan_no: string;
  product_code: string;
  product_code_nm: string;
  pd: number;
  lgd: number;
  ccf: number;
  bs_balance: number;
  ead: number;
  rwa: number;
  rw: number | null;
}

export interface DbQueryResponse {
  success: boolean;
  query: Record<string, unknown>;
  summary: DbQuerySummary | null;
  rows: DbQueryRow[];
  message?: string;
  error_code?: string;
}

export interface ChatHistoryItem {
  role: ChatRole;
  content: string;
}

// ── 데이터 분석 위젯 타입 ───────────────────────────────────────────────────────

export interface DataTableWidget {
  type: "data_table";
  title: string;
  columns: string[];
  columnLabels: Record<string, string>;
  rows: Record<string, unknown>[];
}

export interface LineChartWidget {
  type: "line_chart";
  title: string;
  xKey: string;
  yKeys: string[];
  yLabels: Record<string, string>;
  data: Record<string, unknown>[];
}

export interface BarChartWidget {
  type: "bar_chart";
  title: string;
  xKey: string;
  yKeys: string[];
  yLabels: Record<string, string>;
  data: Record<string, unknown>[];
}

export type DataWidget = DataTableWidget | LineChartWidget | BarChartWidget;

// ── SSE 스트림 이벤트 ───────────────────────────────────────────────────────────

export type ChatStreamEvent =
  | { type: "sources"; sources: SourceDoc[] }
  | { type: "status"; text: string }
  | { type: "chunk"; text: string }
  | { type: "widgets"; widgets: DataWidget[] };
