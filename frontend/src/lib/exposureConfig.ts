/**
 * 익스포져 유형별 폼 구성 정의
 * 이 파일이 동적 폼 렌더링의 단일 소스다.
 */

export type FieldType = "number" | "select" | "boolean" | "text" | "section";

export interface FieldOption {
  value: string;
  label: string;
}

export interface FieldConfig {
  name: string;
  label: string;
  type: FieldType;
  required?: boolean;
  options?: FieldOption[];
  placeholder?: string;
  min?: number;
  max?: number;
  step?: number;
  hint?: string;
  defaultValue?: number | string | boolean;
  /** 이 필드가 표시되려면 다른 필드가 특정 값이어야 한다 */
  showWhen?: { field: string; values: string[] };
}

export interface EntityTypeConfig {
  value: string;
  label: string;
  description?: string;
  fields: FieldConfig[];
}

export interface CategoryConfig {
  id: string;
  label: string;
  labelKo: string;
  icon: string;
  entityTypes: EntityTypeConfig[];
}

// ─── 신용등급 공통 옵션 ─────────────────────────────────────────────────────
const CREDIT_RATING_OPTIONS: FieldOption[] = [
  { value: "", label: "무등급" },
  { value: "AAA", label: "AAA" },
  { value: "AA+", label: "AA+" },
  { value: "AA", label: "AA" },
  { value: "AA-", label: "AA-" },
  { value: "A+", label: "A+" },
  { value: "A", label: "A" },
  { value: "A-", label: "A-" },
  { value: "BBB+", label: "BBB+" },
  { value: "BBB", label: "BBB" },
  { value: "BBB-", label: "BBB-" },
  { value: "BB+", label: "BB+" },
  { value: "BB", label: "BB" },
  { value: "BB-", label: "BB-" },
  { value: "B+", label: "B+" },
  { value: "B", label: "B" },
  { value: "B-", label: "B-" },
  { value: "CCC", label: "CCC 이하" },
];

const OECD_GRADE_OPTIONS: FieldOption[] = [
  { value: "", label: "미적용" },
  { value: "0", label: "0" },
  { value: "1", label: "1" },
  { value: "2", label: "2" },
  { value: "3", label: "3" },
  { value: "4", label: "4" },
  { value: "5", label: "5" },
  { value: "6", label: "6" },
  { value: "7", label: "7" },
];

const DD_GRADE_OPTIONS: FieldOption[] = [
  { value: "A", label: "A등급 (완충자본 포함 최소 규제자본 충족)" },
  { value: "B", label: "B등급 (완충자본 미포함 최소 규제자본 충족)" },
  { value: "C", label: "C등급 (B등급 요건 미충족)" },
];

const SLOTTING_GRADE_OPTIONS: FieldOption[] = [
  { value: "STRONG", label: "우량 (Strong)" },
  { value: "GOOD", label: "양호 (Good)" },
  { value: "SATISFACTORY", label: "보통 (Satisfactory)" },
  { value: "WEAK", label: "취약 (Weak)" },
  { value: "DEFAULT", label: "부도 (Default)" },
];

// ─── 카테고리 설정 ──────────────────────────────────────────────────────────
export const EXPOSURE_CATEGORIES: CategoryConfig[] = [
  // ── 1. 정부 ──────────────────────────────────────────────────────────────
  {
    id: "gov",
    label: "Sovereign / Gov",
    labelKo: "정부·공공기관",
    icon: "🏛️",
    entityTypes: [
      {
        value: "central_gov",
        label: "중앙정부·중앙은행",
        description: "제29조 — 국내외 중앙정부 및 중앙은행",
        fields: [
          { name: "is_korea", label: "대한민국 중앙정부 여부", type: "boolean", hint: "체크 시 원화 표시·조달 익스포져에 0% 적용" },
          { name: "is_local_currency", label: "자국통화(원화/현지통화) 표시·조달", type: "boolean" },
          { name: "external_credit_rating", label: "적격외부신용등급", type: "select", options: CREDIT_RATING_OPTIONS },
          { name: "oecd_grade", label: "OECD 국가신용도등급", type: "select", options: OECD_GRADE_OPTIONS, hint: "등급이 있는 경우 외부신용등급보다 우선 사용 불가" },
        ],
      },
      {
        value: "zero_risk_entity",
        label: "무위험기관",
        description: "제30조 — BIS, IMF, ECB, EU, ESM, EFSF",
        fields: [
          { name: "entity_name", label: "기관명", type: "text", required: true, placeholder: "예: BIS, IMF, ECB", hint: "허용 기관: BIS, IMF, ECB, EU, ESM, EFSF" },
        ],
      },
      {
        value: "mdb_zero",
        label: "우량 국제개발은행 (0%)",
        description: "제34조 나. — 0% 요건 충족 MDB",
        fields: [
          { name: "entity_name", label: "기관명 (참고)", type: "text", placeholder: "예: World Bank, IFC" },
        ],
      },
      {
        value: "mdb_general",
        label: "일반 국제개발은행",
        description: "제34조 가. — 등급 기반 MDB",
        fields: [
          { name: "entity_name", label: "기관명 (참고)", type: "text" },
          { name: "external_credit_rating", label: "적격외부신용등급", type: "select", options: CREDIT_RATING_OPTIONS },
          { name: "oecd_grade", label: "OECD 국가신용도등급", type: "select", options: OECD_GRADE_OPTIONS },
        ],
      },
      {
        value: "pse_gov_like",
        label: "정부간주 공공기관 (국내)",
        description: "제32조 가. — 결손보전 가능 기관 (신보, 기보 등)",
        fields: [
          { name: "external_credit_rating", label: "대한민국 정부 신용등급", type: "select", options: CREDIT_RATING_OPTIONS },
          { name: "oecd_grade", label: "OECD 국가신용도등급 (한국)", type: "select", options: OECD_GRADE_OPTIONS },
        ],
      },
      {
        value: "pse_bank_like",
        label: "은행간주 공공기관 (국내)",
        description: "제32조 나. — 공공기관운영법, 정부출자 50% 이상",
        fields: [
          { name: "external_credit_rating", label: "대한민국 정부 신용등급", type: "select", options: CREDIT_RATING_OPTIONS },
          { name: "oecd_grade", label: "OECD 국가신용도등급 (한국)", type: "select", options: OECD_GRADE_OPTIONS },
        ],
      },
      {
        value: "pse_higher",
        label: "업무감독+재정지원 공공기관",
        description: "제32조 다. — max(은행RW, 50%)",
        fields: [
          { name: "external_credit_rating", label: "대한민국 정부 신용등급", type: "select", options: CREDIT_RATING_OPTIONS },
          { name: "oecd_grade", label: "OECD 국가신용도등급 (한국)", type: "select", options: OECD_GRADE_OPTIONS },
        ],
      },
      {
        value: "pse_foreign",
        label: "외국 공공기관",
        description: "제33조 가. — 해당국 정부 등급 기준 은행 RW",
        fields: [
          { name: "country_gov_external_credit_rating", label: "해당 국가 중앙정부 신용등급", type: "select", options: CREDIT_RATING_OPTIONS, required: true },
          { name: "oecd_grade", label: "해당국 OECD 국가신용도등급", type: "select", options: OECD_GRADE_OPTIONS },
        ],
      },
      {
        value: "pse_foreign_gov_like",
        label: "외국 지방정부 (정부간주)",
        description: "제33조 나. — 해당국 정부 등급 기준 정부 RW",
        fields: [
          { name: "country_gov_external_credit_rating", label: "해당 국가 중앙정부 신용등급", type: "select", options: CREDIT_RATING_OPTIONS, required: true },
          { name: "oecd_grade", label: "해당국 OECD 국가신용도등급", type: "select", options: OECD_GRADE_OPTIONS },
        ],
      },
    ],
  },

  // ── 2. 은행 ──────────────────────────────────────────────────────────────
  {
    id: "bank",
    label: "Bank",
    labelKo: "은행·금융회사",
    icon: "🏦",
    entityTypes: [
      {
        value: "bank_ext",
        label: "은행 (외부신용등급)",
        description: "제35조 가. — 적격외부신용평가기관 등급 보유",
        fields: [
          { name: "external_credit_rating", label: "적격외부신용등급", type: "select", options: CREDIT_RATING_OPTIONS, required: true },
          { name: "oecd_grade", label: "OECD 국가신용도등급", type: "select", options: OECD_GRADE_OPTIONS },
        ],
      },
      {
        value: "bank_dd",
        label: "은행 (실사등급)",
        description: "제35조 나.·다. — 무등급 은행 자체 평가",
        fields: [
          { name: "dd_grade", label: "실사등급", type: "select", options: DD_GRADE_OPTIONS, required: true },
          { name: "cet1_ratio", label: "CET1비율 (%)", type: "number", min: 0, max: 100, step: 0.1, hint: "A등급 우량(30%) 판별: CET1≥14% + 레버리지≥5%" },
          { name: "leverage_ratio", label: "단순기본자본비율 (%)", type: "number", min: 0, max: 100, step: 0.1 },
          { name: "is_foreign_currency", label: "외화 익스포져 여부", type: "boolean" },
          { name: "is_trade_lc", label: "무역 단기신용장 여부", type: "boolean", hint: "체크 시 설립국 하한 미적용" },
          { name: "country_gov_external_credit_rating", label: "설립국 중앙정부 신용등급 (외화 시)", type: "select", options: CREDIT_RATING_OPTIONS, showWhen: { field: "is_foreign_currency", values: ["true"] } },
          { name: "country_gov_oecd_grade", label: "설립국 OECD등급 (외화 시)", type: "select", options: OECD_GRADE_OPTIONS, showWhen: { field: "is_foreign_currency", values: ["true"] } },
        ],
      },
      {
        value: "bank_short_ext",
        label: "단기원화 은행 (외부등급)",
        description: "제35조 라.(1) — 원화·만기 3개월 이내 우대",
        fields: [
          { name: "external_credit_rating", label: "적격외부신용등급", type: "select", options: CREDIT_RATING_OPTIONS, required: true },
        ],
      },
      {
        value: "bank_short_dd",
        label: "단기원화 은행 (실사등급)",
        description: "제35조 라.(2) — 원화·만기 3개월 이내, 무등급",
        fields: [
          { name: "dd_grade", label: "실사등급", type: "select", options: DD_GRADE_OPTIONS, required: true },
        ],
      },
      {
        value: "covered_bond_ext",
        label: "커버드본드 (외부등급)",
        description: "제35의2. 가. — 이중상환청구권부채권",
        fields: [
          { name: "external_credit_rating", label: "커버드본드 신용등급", type: "select", options: CREDIT_RATING_OPTIONS, required: true },
        ],
      },
      {
        value: "covered_bond_unrated",
        label: "커버드본드 (무등급)",
        description: "제35의2. 나. — 발행은행 RW 기반",
        fields: [
          {
            name: "issuing_bank_rw",
            label: "발행은행 위험가중치 (%)",
            type: "select",
            options: [
              { value: "0.20", label: "20%" }, { value: "0.30", label: "30%" },
              { value: "0.40", label: "40%" }, { value: "0.50", label: "50%" },
              { value: "0.75", label: "75%" }, { value: "1.00", label: "100%" },
              { value: "1.50", label: "150%" },
            ],
            required: true,
          },
        ],
      },
      {
        value: "securities_firm",
        label: "증권회사·기타금융회사",
        description: "제36조 — 은행 동등 규제 충족 시 제35조 준용",
        fields: [
          { name: "is_bank_equiv_regulated", label: "은행 동등 규제 충족 여부", type: "boolean" },
          { name: "external_credit_rating", label: "적격외부신용등급", type: "select", options: CREDIT_RATING_OPTIONS },
          { name: "dd_grade", label: "실사등급 (무등급 시)", type: "select", options: [{ value: "", label: "미적용" }, ...DD_GRADE_OPTIONS] },
        ],
      },
    ],
  },

  // ── 3. 기업 ──────────────────────────────────────────────────────────────
  {
    id: "corp",
    label: "Corporate",
    labelKo: "기업·특수금융",
    icon: "🏢",
    entityTypes: [
      {
        value: "general",
        label: "일반기업 (장기등급)",
        description: "제37조 — 외부신용등급 또는 무등급",
        fields: [
          { name: "external_credit_rating", label: "적격외부신용등급", type: "select", options: CREDIT_RATING_OPTIONS },
          { name: "is_sme_legal", label: "중소기업기본법상 중소기업", type: "boolean", hint: "무등급 시 85% 적용" },
          { name: "annual_revenue_eok", label: "연간 매출액 (억원)", type: "number", min: 0, hint: "0 입력 시 미적용 (총자산으로 판정)" },
          { name: "total_assets_eok", label: "총자산 (억원)", type: "number", min: 0, hint: "매출액 기준 부적합 시 2,300억 이하 판정" },
          { name: "country_floor_rw", label: "설립국 중앙정부 위험가중치 (%)", type: "number", min: 0, max: 150, hint: "제37조 나. 무등급 하한 (미입력 시 미적용)" },
        ],
      },
      {
        value: "general_short",
        label: "일반기업 (단기등급)",
        description: "제38조 — 단기 외부신용등급",
        fields: [
          {
            name: "short_grade",
            label: "단기 신용등급",
            type: "select",
            options: [
              { value: "A-1", label: "A-1 (20%)" },
              { value: "A-2", label: "A-2 (50%)" },
              { value: "A-3", label: "A-3 (100%)" },
              { value: "OTHER", label: "기타/투기 (150%)" },
            ],
            required: true,
          },
          { name: "debtor_short_rw", label: "동일 채무자 단기등급 RW (%)", type: "number", min: 0, max: 150, hint: "제38조 나. 무등급 하한 (미입력 시 미적용)" },
        ],
      },
      {
        value: "sl_pf",
        label: "프로젝트금융 (PF)",
        description: "제38조의2 — Project Finance",
        fields: [
          { name: "external_credit_rating", label: "적격외부신용등급 (없으면 무등급)", type: "select", options: CREDIT_RATING_OPTIONS },
          {
            name: "pf_stage",
            label: "PF 운영 단계 (무등급 시)",
            type: "select",
            options: [
              { value: "pre_op", label: "운영전 (Pre-operational) — 130%" },
              { value: "operational", label: "운영 중 (Operational) — 100%" },
              { value: "op_hq", label: "우량 운영 (High Quality) — 80%" },
            ],
          },
          { name: "pf_op_high_quality", label: "우량 운영 5개 요건 직접 충족", type: "boolean" },
        ],
      },
      {
        value: "sl_of",
        label: "오브젝트금융 (OF)",
        description: "제38조의2 — Object Finance",
        fields: [
          { name: "external_credit_rating", label: "적격외부신용등급 (없으면 100%)", type: "select", options: CREDIT_RATING_OPTIONS },
        ],
      },
      {
        value: "sl_cf",
        label: "상품금융 (CF)",
        description: "제38조의2 — Commodity Finance",
        fields: [
          { name: "external_credit_rating", label: "적격외부신용등급 (없으면 100%)", type: "select", options: CREDIT_RATING_OPTIONS },
        ],
      },
      {
        value: "ipre",
        label: "수익창출 부동산금융 (IPRE)",
        description: "슬롯팅 기준 — 임대료 등 현금흐름 의존 부동산",
        fields: [
          { name: "slotting_grade", label: "슬롯팅 등급", type: "select", options: SLOTTING_GRADE_OPTIONS, required: true },
          { name: "slotting_short_or_safe", label: "잔존만기 2년6개월 이내 또는 안전성 입증", type: "boolean", hint: "체크 시 우량·양호 등급에 우대 RW 적용" },
        ],
      },
      {
        value: "hvcre",
        label: "고변동성 상업용부동산 (HVCRE)",
        description: "슬롯팅 기준 — High Volatility CRE",
        fields: [
          { name: "slotting_grade", label: "슬롯팅 등급", type: "select", options: SLOTTING_GRADE_OPTIONS, required: true },
          { name: "slotting_short_or_safe", label: "잔존만기 2년6개월 이내 또는 안전성 입증", type: "boolean" },
        ],
      },
    ],
  },

  // ── 4. CIU ───────────────────────────────────────────────────────────────
  {
    id: "ciu",
    label: "CIU",
    labelKo: "집합투자증권",
    icon: "📊",
    entityTypes: [
      {
        value: "lta",
        label: "Look-Through 방식 (LTA)",
        description: "펀드 기초자산 직접 조회 — 가중평균 RW 입력",
        fields: [
          { name: "ciu_approach", type: "text", label: "", hint: "자동 설정 (lta)" },
          { name: "weighted_avg_rw", label: "기초자산 가중평균 위험가중치 (%)", type: "number", min: 0, max: 1250, required: true },
        ],
      },
      {
        value: "mba",
        label: "위임 기반 방식 (MBA)",
        description: "펀드 위임장 기반 보수적 RW 적용",
        fields: [
          { name: "ciu_approach", type: "text", label: "", hint: "자동 설정 (mba)" },
          { name: "weighted_avg_rw", label: "위임장 기반 가중평균 위험가중치 (%)", type: "number", min: 0, max: 1250, required: true },
        ],
      },
      {
        value: "fba",
        label: "대체 방식 (FBA)",
        description: "정보 부재 시 자동 1,250% 적용",
        fields: [],
      },
    ],
  },

  // ── 5. 부동산 ────────────────────────────────────────────────────────────
  {
    id: "realestate",
    label: "Real Estate",
    labelKo: "부동산개발금융",
    icon: "🏗️",
    entityTypes: [
      {
        value: "cre_non_ipre",
        label: "상업용부동산 — 비수익형 (Non-IPRE)",
        description: "제41조 가. — 상환재원이 담보물 현금흐름에 미의존",
        fields: [
          { name: "re_exposure_type", type: "text", label: "", hint: "자동 설정" },
          { name: "ltv_ratio", label: "LTV 비율 (%)", type: "number", min: 0, max: 200, required: true, hint: "60% 이하 + 적격 요건 충족 시 min(60%, 차주RW)" },
          { name: "is_eligible", label: "적격 요건 충족 여부", type: "boolean" },
          { name: "borrower_risk_weight", label: "차주(차입자) 위험가중치 (%)", type: "number", min: 0, max: 1250, required: true },
        ],
      },
      {
        value: "cre_ipre",
        label: "상업용부동산 — 수익형 (IPRE)",
        description: "제41조 나. — 임대료·매각 등 현금흐름 의존",
        fields: [
          { name: "re_exposure_type", type: "text", label: "", hint: "자동 설정" },
          { name: "ltv_ratio", label: "LTV 비율 (%)", type: "number", min: 0, max: 200, required: true, hint: "≤60%→70%, 60~80%→90%, >80%→110%" },
          { name: "is_eligible", label: "적격 요건 충족 여부", type: "boolean", hint: "미충족 시 150% 적용" },
        ],
      },
      {
        value: "adc",
        label: "부동산개발금융 (ADC)",
        description: "제41조의2 — 기본 150%, 주거용 예외 100%",
        fields: [
          { name: "re_exposure_type", type: "text", label: "", hint: "자동 설정" },
          { name: "is_residential_exception", label: "주거용 예외 요건 충족 ((1)(2) 모두 충족)", type: "boolean", hint: "충족 시 100% 적용" },
        ],
      },
      {
        value: "pf_consortium",
        label: "PF 조합사업비",
        description: "제41조의2 준용 — 기본 150%, 시공사 보증 특례",
        fields: [
          { name: "re_exposure_type", type: "text", label: "", hint: "자동 설정" },
          {
            name: "has_construction_guarantee",
            label: "시공사 연대보증 적용",
            type: "boolean",
            hint: "연대보증이 있는 경우 ON — 시공사 기업 SA 위험가중치 적용",
          },
          {
            name: "contractor_credit_rating",
            label: "시공사 적격외부신용등급",
            type: "select",
            options: CREDIT_RATING_OPTIONS,
            required: true,
            hint: "시공사의 장기 외부신용등급 (기업 익스포져 SA RW 결정)",
            showWhen: { field: "has_construction_guarantee", values: ["true"] },
          },
          {
            name: "guarantor_exposure",
            label: "연대보증 금액 (원)",
            type: "number",
            min: 0,
            hint: "보증금액까지는 시공사 RW, 잔액은 150% 적용. 익스포져 이상이면 전액 보증 처리.",
            showWhen: { field: "has_construction_guarantee", values: ["true"] },
          },
        ],
      },
    ],
  },

  // ── 6. 주식 ──────────────────────────────────────────────────────────────
  {
    id: "equity",
    label: "Equity",
    labelKo: "주식·자본조달",
    icon: "📈",
    entityTypes: [
      { value: "general_listed", label: "일반 상장주식", description: "제38조의3 바. — 250%", fields: [] },
      { value: "unlisted_long_term", label: "비상장 장기보유·출자전환", description: "제38조의3 바. — 250%", fields: [] },
      { value: "unlisted_speculative", label: "투기적 비상장주식 (VC·자본이득)", description: "제38조의3 바. — 400%", fields: [] },
      { value: "govt_sponsored", label: "정부보조 프로그램 주식", description: "제38조의3 사. — 100% (자기자본 10% 한도)", fields: [] },
      { value: "subordinated_debt", label: "후순위채권", description: "제38조의3 아. — 150%", fields: [] },
      { value: "other_capital_instrument", label: "기타 자본조달수단", description: "제38조의3 아. — 150%", fields: [] },
      { value: "non_financial_large", label: "비금융자회사 대규모 출자 (초과분)", description: "제38조의3 자. — 1,250%", fields: [] },
    ],
  },

  // ── 7. 유동화 ────────────────────────────────────────────────────────────
  {
    id: "securitization",
    label: "Securitisation",
    labelKo: "유동화 익스포져",
    icon: "🔗",
    entityTypes: [
      {
        value: "sec_sa",
        label: "표준방법 (SEC-SA)",
        description: "SSFA 공식 기반 — Attachment/Detachment Point, K_SA, W, p 입력",
        fields: [
          {
            name: "attachment_point",
            label: "Attachment Point (A)",
            type: "number",
            required: true,
            min: 0,
            max: 1,
            step: 0.0001,
            placeholder: "예: 0.05 (5%)",
            hint: "손실개시점 — 트랜치 하단 경계. 예: Mezzanine 5~15% → A=0.05",
          },
          {
            name: "detachment_point",
            label: "Detachment Point (D)",
            type: "number",
            required: true,
            min: 0,
            max: 1,
            step: 0.0001,
            placeholder: "예: 0.15 (15%)",
            hint: "손실종료점 — 트랜치 상단 경계. 예: Mezzanine 5~15% → D=0.15",
          },
          {
            name: "k_sa",
            label: "K_SA",
            type: "number",
            required: true,
            min: 0,
            step: 0.0001,
            placeholder: "예: 0.08",
            hint: "기초자산 풀의 표준방법(SA) 기반 자기자본비율 관련 입력값",
          },
          {
            name: "w",
            label: "W (연체·부실 비율)",
            type: "number",
            required: true,
            min: 0,
            max: 1,
            step: 0.0001,
            placeholder: "예: 0.05 (5%)",
            hint: "기초자산 풀 내 연체 또는 부실 자산 비율 (0 ≤ W ≤ 1)",
          },
          {
            name: "p",
            label: "p (감독승수)",
            type: "number",
            required: true,
            min: 0.0001,
            step: 0.1,
            placeholder: "1.0",
            defaultValue: 1.0,
            hint: "일반 유동화: 1.0 (기본값) / 재유동화: 감독기관 지정값 사용",
          },
        ],
      },
    ],
  },
];

export function getCategoryById(id: string): CategoryConfig | undefined {
  return EXPOSURE_CATEGORIES.find((c) => c.id === id);
}

export function getEntityTypeConfig(
  categoryId: string,
  entityTypeValue: string
): EntityTypeConfig | undefined {
  return getCategoryById(categoryId)?.entityTypes.find(
    (e) => e.value === entityTypeValue
  );
}
