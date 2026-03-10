"""
RWA 산출 서비스 — 익스포져 카테고리별 Calculator 디스패치
"""
from __future__ import annotations

from app.schemas.rwa import RwaCalculationRequest, RwaResult


def calculate_rwa(req: RwaCalculationRequest) -> RwaResult:
    category = req.exposure_category.lower()

    dispatch = {
        "gov": _calc_gov,
        "bank": _calc_bank,
        "corp": _calc_corp,
        "ciu": _calc_ciu,
        "realestate": _calc_realestate,
        "equity": _calc_equity,
        "securitization": _calc_securitization,
    }

    handler = dispatch.get(category)
    if handler is None:
        raise ValueError(f"지원하지 않는 익스포져 카테고리: {category!r}")

    result_dict = handler(req)
    rw = result_dict["risk_weight"]
    return RwaResult(
        entity_type=result_dict["entity_type"],
        risk_weight=rw,
        risk_weight_pct=f"{rw * 100:.1f}%",
        rwa=result_dict["rwa"],
        basis=result_dict["basis"],
    )


# ── Gov ────────────────────────────────────────────────────────────────────────

def _calc_gov(req: RwaCalculationRequest) -> dict:
    from rwa.sa.gov.calculator import SovereignCalculator, GovEntityType, GovExposureInput

    calc = SovereignCalculator()
    inp = GovExposureInput(
        exposure=req.exposure,
        entity_type=GovEntityType(req.entity_type),
        external_credit_rating=req.external_credit_rating,
        oecd_grade=req.oecd_grade,
        is_local_currency=req.is_local_currency,
        is_korea=req.is_korea,
        entity_name=req.entity_name,
        pse_category=req.pse_category,
        country_gov_external_credit_rating=req.country_gov_external_credit_rating,
    )
    return dict(calc.calc_rwa(inp))


# ── Bank ───────────────────────────────────────────────────────────────────────

def _calc_bank(req: RwaCalculationRequest) -> dict:
    from rwa.sa.bank.calculator import BankCalculator, BankEntityType, BankExposureInput

    calc = BankCalculator()
    inp = BankExposureInput(
        exposure=req.exposure,
        entity_type=BankEntityType(req.entity_type),
        external_credit_rating=req.external_credit_rating,
        oecd_grade=req.oecd_grade,
        dd_grade=req.dd_grade,
        cet1_ratio=req.cet1_ratio,
        leverage_ratio=req.leverage_ratio,
        is_foreign_currency=req.is_foreign_currency,
        is_trade_lc=req.is_trade_lc,
        country_gov_external_credit_rating=req.country_gov_external_credit_rating,
        country_gov_oecd_grade=req.country_gov_oecd_grade,
        issuing_bank_rw=req.issuing_bank_rw,
        is_bank_equiv_regulated=req.is_bank_equiv_regulated,
        entity_name=req.entity_name,
    )
    return dict(calc.calc_rwa(inp))


# ── Corp ───────────────────────────────────────────────────────────────────────

def _calc_corp(req: RwaCalculationRequest) -> dict:
    from rwa.sa.corp.calculator import (
        CorporateCalculator, CorpEntityType, CorporateExposureInput, PFStage, SlottingGrade
    )

    calc = CorporateCalculator()
    pf_stage_map = {
        "pre_op": PFStage.PRE_OPERATIONAL,
        "operational": PFStage.OPERATIONAL,
        "op_hq": PFStage.OPERATIONAL_HIGH_QUALITY,
    }
    pf_stage = pf_stage_map.get(req.pf_stage, PFStage.OPERATIONAL)

    slotting_grade = None
    if req.slotting_grade:
        slotting_grade = SlottingGrade(req.slotting_grade.upper())

    inp = CorporateExposureInput(
        exposure=req.exposure,
        entity_type=CorpEntityType(req.entity_type),
        external_credit_rating=req.external_credit_rating,
        short_grade=req.short_grade,
        is_sme_legal=req.is_sme_legal,
        annual_revenue_eok=req.annual_revenue_eok,
        total_assets_eok=req.total_assets_eok,
        country_floor_rw=req.country_floor_rw,
        debtor_short_rw=req.debtor_short_rw,
        pf_stage=pf_stage,
        pf_op_high_quality=req.pf_op_high_quality,
        slotting_grade=slotting_grade,
        slotting_short_or_safe=req.slotting_short_or_safe,
        entity_name=req.entity_name,
    )
    return dict(calc.calc_rwa(inp))


# ── CIU ───────────────────────────────────────────────────────────────────────

def _calc_ciu(req: RwaCalculationRequest) -> dict:
    from rwa.sa.ciu.calculator import CIUApproach, CIUInput, CIUCalculator as CiuCalculator

    calc = CiuCalculator()
    approach_map = {
        "lta": CIUApproach.LTA,
        "mba": CIUApproach.MBA,
        "fba": CIUApproach.FBA,
    }
    approach_key = (req.ciu_approach or req.entity_type or "fba").lower()
    approach = approach_map.get(approach_key, CIUApproach.FBA)

    inp = CIUInput(
        exposure=req.exposure,
        approach=approach,
        weighted_avg_rw=req.weighted_avg_rw,
    )
    return dict(calc.calc_rwa(inp))


# ── RealEstate ────────────────────────────────────────────────────────────────

def _calc_realestate(req: RwaCalculationRequest) -> dict:
    from rwa.sa.realestate.calculator import (
        RealEstateCalculator, RealEstateExposureType, RealEstateExposureInput
    )
    from rwa.sa.corp.calculator import (
        CorporateCalculator, CorpEntityType, CorporateExposureInput
    )

    calc = RealEstateCalculator()
    type_str = req.re_exposure_type or req.entity_type

    # ── 시공사 연대보증 처리 ──────────────────────────────────────────────────
    # has_construction_guarantee 플래그(명시적) 또는 contractor_credit_rating 존재로 판단
    has_guarantee = req.has_construction_guarantee or bool(req.contractor_credit_rating)

    guarantor_corp_rwa = None
    if has_guarantee and req.contractor_credit_rating:
        # 시공사의 기업 익스포져 SA 위험가중치를 1원 기준으로 산출 (RW만 사용)
        corp_calc = CorporateCalculator()
        corp_inp = CorporateExposureInput(
            exposure=1.0,
            entity_type=CorpEntityType("general"),
            external_credit_rating=req.contractor_credit_rating,
        )
        guarantor_corp_rwa = dict(corp_calc.calc_rwa(corp_inp))

    inp = RealEstateExposureInput(
        exposure=req.exposure,
        exposure_type=RealEstateExposureType(type_str),
        ltv=req.ltv_ratio,
        meets_eligibility=req.is_eligible,
        borrower_rw=req.borrower_risk_weight,
        is_residential_exception=req.is_residential_exception,
        has_construction_guarantee=has_guarantee,
        guarantor_corp_rwa=guarantor_corp_rwa,
        guarantor_exposure=req.guarantor_exposure,
    )
    return dict(calc.calc_rwa(inp))


# ── Securitisation (SEC-SA) ───────────────────────────────────────────────────

def _calc_securitization(req: RwaCalculationRequest) -> dict:
    from rwa.sa.securitization.calculator import SecuritizationCalculator, SecuritizationInput

    # 필수 입력값 확인
    missing = [
        f for f, v in [
            ("attachment_point", req.attachment_point),
            ("detachment_point", req.detachment_point),
            ("k_sa", req.k_sa),
            ("w", req.w),
        ]
        if v is None
    ]
    if missing:
        raise ValueError(f"유동화 SEC-SA 필수 입력값 누락: {', '.join(missing)}")

    calc = SecuritizationCalculator()
    inp = SecuritizationInput(
        exposure=req.exposure,
        attachment_point=req.attachment_point,   # type: ignore[arg-type]
        detachment_point=req.detachment_point,   # type: ignore[arg-type]
        k_sa=req.k_sa,                           # type: ignore[arg-type]
        w=req.w,                                 # type: ignore[arg-type]
        p=req.p,
    )
    return dict(calc.calc_rwa(inp))


# ── Equity ────────────────────────────────────────────────────────────────────

def _calc_equity(req: RwaCalculationRequest) -> dict:
    from rwa.sa.equity.calculator import EquityCalculator, EquityType, EquityInput

    calc = EquityCalculator()
    equity_type_str = req.equity_type or req.entity_type
    inp = EquityInput(
        exposure=req.exposure,
        equity_type=EquityType(equity_type_str),
    )
    return dict(calc.calc_rwa(inp))
