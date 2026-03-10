/**
 * FastAPI 백엔드 API 클라이언트
 * Next.js rewrites를 통해 /api/* → http://localhost:8000/api/*
 */

const BASE_URL = "/api";

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
  // Bank
  dd_grade?: string;
  cet1_ratio?: number;
  leverage_ratio?: number;
  is_foreign_currency?: boolean;
  is_trade_lc?: boolean;
  country_gov_oecd_grade?: number;
  issuing_bank_rw?: number;
  is_bank_equiv_regulated?: boolean;
  // Corp
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
  // RealEstate
  re_exposure_type?: string;
  ltv_ratio?: number;
  is_eligible?: boolean;
  borrower_risk_weight?: number;
  is_residential_exception?: boolean;
  has_construction_guarantee?: boolean;
  contractor_credit_rating?: string;
  guarantor_exposure?: number;
  // CIU
  ciu_approach?: string;
  weighted_avg_rw?: number;
  // Equity
  equity_type?: string;
  // Securitisation SEC-SA
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

export async function calculateRwa(req: RwaRequest): Promise<RwaResult> {
  const res = await fetch(`${BASE_URL}/calculate/rwa`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "RWA 산출 오류");
  }
  return res.json();
}

export async function* streamChat(
  query: string,
  history: { role: string; content: string }[] = []
): AsyncGenerator<{ type: "sources"; sources: SourceDoc[] } | { type: "chunk"; text: string }> {
  const res = await fetch(`${BASE_URL}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, history }),
  });

  if (!res.ok || !res.body) {
    throw new Error("스트리밍 연결 실패");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const data = line.slice(6).trim();
      if (data === "[DONE]") return;
      try {
        yield JSON.parse(data);
      } catch {
        // ignore malformed JSON
      }
    }
  }
}
