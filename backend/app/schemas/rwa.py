"""
Pydantic 스키마 — RWA 산출 요청/응답

익스포져 카테고리별로 필요한 필드를 모두 Optional로 선언하고,
서비스 레이어에서 entity_type 기반으로 필수 필드를 검증한다.
"""
from typing import Optional
from pydantic import BaseModel, Field, model_validator


# ── 응답 스키마 ────────────────────────────────────────────────────────────────

class RwaResult(BaseModel):
    entity_type: str
    risk_weight: float          # 예: 0.20 = 20%
    risk_weight_pct: str        # 예: "20.0%"
    rwa: float
    basis: str


# ── 공통 필드 ──────────────────────────────────────────────────────────────────

class RwaCalculationRequest(BaseModel):
    # --- 공통 필드 ---
    exposure_category: str = Field(
        ...,
        description="익스포져 카테고리: gov | bank | corp | ciu | realestate | equity",
    )
    entity_type: str = Field(..., description="엔티티 세부 유형 (각 카테고리 Enum 값)")
    exposure: float = Field(..., gt=0, description="익스포져 금액 (원화, 단위: 원)")
    entity_name: Optional[str] = None

    # --- 신용등급 ---
    external_credit_rating: Optional[str] = Field(None, description="적격외부신용등급 (예: AA-, BBB+)")
    oecd_grade: Optional[int] = Field(None, ge=0, le=7, description="OECD 국가신용도등급 (0~7)")
    is_local_currency: bool = False

    # --- 정부(Gov) 전용 ---
    is_korea: bool = True
    pse_category: Optional[str] = None                     # local_gov_krw | pse_type1 | ...
    country_gov_external_credit_rating: Optional[str] = None

    # --- 은행(Bank) 전용 ---
    dd_grade: Optional[str] = Field(None, description="실사등급: A | B | C")
    cet1_ratio: Optional[float] = Field(None, ge=0, le=1, description="CET1비율 (0~1)")
    leverage_ratio: Optional[float] = Field(None, ge=0, le=1, description="단순기본자본비율 (0~1)")
    is_foreign_currency: bool = False
    is_trade_lc: bool = False
    country_gov_oecd_grade: Optional[int] = Field(None, ge=0, le=7)
    issuing_bank_rw: Optional[float] = None                # 커버드본드 발행은행 RW
    is_bank_equiv_regulated: bool = True

    # --- 기업(Corp) 전용 ---
    short_grade: Optional[str] = Field(None, description="단기등급: A-1 | A-2 | A-3 | OTHER")
    is_sme_legal: bool = False
    annual_revenue_eok: float = Field(0.0, ge=0, description="연간 매출액 (억원)")
    total_assets_eok: float = Field(0.0, ge=0, description="총자산 (억원)")
    country_floor_rw: Optional[float] = None
    debtor_short_rw: Optional[float] = None
    pf_stage: str = "operational"                          # pre_op | operational | op_hq
    pf_op_high_quality: bool = False
    slotting_grade: Optional[str] = None                   # STRONG | GOOD | SATISFACTORY | WEAK | DEFAULT
    slotting_short_or_safe: bool = False

    # --- 부동산(RealEstate) 전용 ---
    re_exposure_type: Optional[str] = None                 # cre_non_ipre | cre_ipre | adc | pf_consortium
    ltv_ratio: Optional[float] = Field(None, ge=0, description="LTV 비율 (0~1 또는 %, 서비스에서 정규화)")
    is_eligible: bool = True
    borrower_risk_weight: Optional[float] = None
    is_residential_exception: bool = False
    has_construction_guarantee: bool = False               # [PF조합사업비] 시공사 연대보증 여부
    contractor_credit_rating: Optional[str] = None        # [PF조합사업비] 시공사 적격외부신용등급
    guarantor_exposure: Optional[float] = Field(None, ge=0, description="[PF조합사업비] 시공사 연대보증 금액 (원)")

    # --- CIU 전용 ---
    ciu_approach: Optional[str] = None                     # lta | mba | fba
    weighted_avg_rw: Optional[float] = None

    # --- 주식(Equity) 전용 ---
    equity_type: Optional[str] = None

    # --- 유동화(Securitisation) SEC-SA 전용 ---
    attachment_point: Optional[float] = Field(None, ge=0, description="Attachment Point A (0 ≤ A < D)")
    detachment_point: Optional[float] = Field(None, gt=0, description="Detachment Point D (D > A)")
    k_sa: Optional[float] = Field(None, ge=0, description="기초자산 풀 SA 자기자본비율 관련 값")
    w: Optional[float] = Field(None, ge=0, le=1, description="연체·부실 자산 비율 W (0 ≤ W ≤ 1)")
    p: float = Field(1.0, gt=0, description="감독승수 p (> 0; 일반 유동화=1.0, 재유동화=별도)")

    @model_validator(mode="after")
    def normalize_ltv(self):
        """LTV가 1 초과이면 % 단위로 입력된 것으로 간주하여 정규화."""
        if self.ltv_ratio is not None and self.ltv_ratio > 1:
            self.ltv_ratio = self.ltv_ratio / 100
        return self
