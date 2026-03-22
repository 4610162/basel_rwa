"""
챗봇 수집값 → RwaCalculationRequest 매핑 모듈

3단계에서 수집한 accumulated dict[str, str] (사용자 입력 display 문자열)을
기존 calculate_rwa()가 요구하는 RwaCalculationRequest로 변환한다.

원칙:
- 계산 로직 재구현 금지: 반드시 calculate_rwa()를 호출
- 매핑 실패 시 ValueError를 raise (chat.py에서 catch → 오류 안내)
- LLM 추정 없음: 명확히 매핑 불가한 값은 기본값 또는 None 사용
"""
from __future__ import annotations

import re

from app.schemas.rwa import RwaCalculationRequest, RwaResult
from app.services.exposure_schema import ExposureSchema


# ── 공통 헬퍼 ─────────────────────────────────────────────────────────────────

def _to_float(value_str: str | None, *, default: float | None = None) -> float | None:
    """문자열을 float로 변환. 실패 시 default 반환."""
    if not value_str:
        return default
    try:
        return float(value_str)
    except ValueError:
        return default


def _pct_to_fraction(value_str: str | None) -> float | None:
    """
    "20%" 또는 "20" 형태의 퍼센트 문자열을 분수(0.20)로 변환.
    이미 0~1 범위이면 그대로 반환.
    """
    if not value_str:
        return None
    cleaned = value_str.replace("%", "").strip()
    try:
        val = float(cleaned)
    except ValueError:
        return None
    return val / 100.0 if val > 1.0 else val


def _dd_grade(display: str | None) -> str | None:
    """
    DD등급 display 문자열 → "A" / "B" / "C"
    "A등급 (완충자본 포함 최소 규제자본 충족)" → "A"
    """
    if not display:
        return None
    if display.startswith("A"):
        return "A"
    if display.startswith("B"):
        return "B"
    if display.startswith("C"):
        return "C"
    return None


def _bool_from_display(display: str | None, true_val: str, false_val: str) -> bool:
    """display 문자열로 bool 변환. 기본값 False."""
    if not display:
        return False
    return true_val.lower() in display.lower()


# ── 익스포져 유형별 매퍼 ──────────────────────────────────────────────────────

def _map_corporate(acc: dict[str, str]) -> RwaCalculationRequest:
    """
    기업 익스포져 수집값 → RwaCalculationRequest(exposure_category="corp")

    entity_type 매핑:
        "일반법인"                       → "general"
        "중소기업(SME)"                  → "general" + is_sme_legal=True
        "특수목적금융-PF (프로젝트금융)"  → "sl_pf"
        "특수목적금융-OF (오브젝트금융)"  → "sl_of"
        "특수목적금융-CF (상품금융)"      → "sl_cf"
        "IPRE (수익창출 부동산금융)"      → "ipre"
        "HVCRE (고변동성 상업용부동산)"   → "hvcre"
    """
    exposure = _to_float(acc.get("exposure"), default=0.0) or 0.0
    entity_display = acc.get("entity_type", "일반법인")

    _entity_map: dict[str, tuple[str, bool]] = {
        # (entity_type_enum_value, is_sme_legal_from_type)
        "일반법인":                             ("general", False),
        "중소기업(SME)":                        ("general", True),
        "특수목적금융-PF (프로젝트금융)":        ("sl_pf",   False),
        "특수목적금융-OF (오브젝트금융)":        ("sl_of",   False),
        "특수목적금융-CF (상품금융)":            ("sl_cf",   False),
        "IPRE (수익창출 부동산금융)":            ("ipre",    False),
        "HVCRE (고변동성 상업용부동산)":         ("hvcre",   False),
    }
    entity_type, is_sme_from_type = _entity_map.get(entity_display, ("general", False))

    # is_sme_legal: entity_type에서 파생 OR optional 필드 명시
    is_sme_explicit = _bool_from_display(acc.get("is_sme_legal"), "해당", "미해당")
    is_sme_legal = is_sme_from_type or is_sme_explicit

    # slotting_grade (IPRE/HVCRE 전용)
    _slotting_map = {
        "우량(Strong)":        "STRONG",
        "양호(Good)":          "GOOD",
        "보통(Satisfactory)":  "SATISFACTORY",
        "취약(Weak)":          "WEAK",
        "부도(Default)":       "DEFAULT",
    }
    slotting_raw = acc.get("slotting_grade")
    slotting_grade = _slotting_map.get(slotting_raw) if slotting_raw else None

    # pf_stage (무등급 PF 전용)
    _pf_stage_map = {
        "운영전(Pre-operational) 130%":  "pre_op",
        "운영중(Operational) 100%":      "operational",
        "우량운영(High Quality) 80%":    "op_hq",
    }
    pf_stage_raw = acc.get("pf_stage")
    pf_stage = _pf_stage_map.get(pf_stage_raw, "operational")

    return RwaCalculationRequest(
        exposure_category="corp",
        entity_type=entity_type,
        exposure=exposure,
        external_credit_rating=acc.get("external_credit_rating"),
        is_sme_legal=is_sme_legal,
        pf_stage=pf_stage,
        slotting_grade=slotting_grade,
    )


def _map_bank(acc: dict[str, str]) -> RwaCalculationRequest:
    """
    은행 익스포져 수집값 → RwaCalculationRequest(exposure_category="bank")

    entity_subtype 매핑:
        "일반 (외부등급 보유)"           → "bank_ext"
        "일반 (무등급 — 실사등급 적용)"  → "bank_dd"
        "커버드본드 (외부등급 보유)"      → "covered_bond_ext"
        "커버드본드 (무등급)"            → "covered_bond_unrated"
        "단기원화 (만기 3개월 이내)"     → rating 있으면 "bank_short_ext", 없으면 "bank_short_dd"
        "증권사·기타금융회사"            → "securities_firm"
    """
    exposure = _to_float(acc.get("exposure"), default=0.0) or 0.0
    subtype_display = acc.get("entity_subtype", "")
    rating = acc.get("external_credit_rating")

    _subtype_map = {
        "일반 (외부등급 보유)":          "bank_ext",
        "일반 (무등급 — 실사등급 적용)": "bank_dd",
        "커버드본드 (외부등급 보유)":     "covered_bond_ext",
        "커버드본드 (무등급)":           "covered_bond_unrated",
        "증권사·기타금융회사":           "securities_firm",
    }

    if "단기원화" in subtype_display:
        entity_type = "bank_short_ext" if (rating and rating != "무등급") else "bank_short_dd"
    else:
        entity_type = _subtype_map.get(subtype_display, "bank_ext")

    dd_grade = _dd_grade(acc.get("dd_grade"))
    is_foreign = _bool_from_display(acc.get("is_foreign_currency"), "외화", "원화")
    issuing_bank_rw = _pct_to_fraction(acc.get("issuing_bank_rw"))

    return RwaCalculationRequest(
        exposure_category="bank",
        entity_type=entity_type,
        exposure=exposure,
        external_credit_rating=rating,
        dd_grade=dd_grade,
        is_foreign_currency=is_foreign,
        issuing_bank_rw=issuing_bank_rw,
        country_gov_external_credit_rating=acc.get("country_gov_external_credit_rating"),
    )


def _map_sovereign(acc: dict[str, str]) -> RwaCalculationRequest:
    """
    정부·공공기관 익스포져 수집값 → RwaCalculationRequest(exposure_category="gov")

    entity_subtype 매핑:
        "국내 중앙정부·중앙은행 (한국)"          → "central_gov", is_korea=True
        "외국 중앙정부·중앙은행"                  → "central_gov", is_korea=False
        "무위험기관 (BIS, IMF, ECB, EU, ESM, EFSF)"→ "zero_risk_entity"
        "국내 공공기관 — 정부간주 (신보, 기보 등)" → "pse_gov_like"
        "국내 공공기관 — 은행간주 (정부출자 50% 이상)"→ "pse_bank_like"
        "국내 공공기관 — 업무감독+재정지원"        → "pse_higher"
        "외국 지방정부·공공기관"                   → "pse_foreign"
        "우량 국제개발은행 (World Bank, IFC 등, 0%)"→ "mdb_zero"
        "일반 국제개발은행 (등급 기반)"             → "mdb_general"
    """
    exposure = _to_float(acc.get("exposure"), default=0.0) or 0.0
    subtype_display = acc.get("entity_subtype", "")

    _subtype_map = {
        "국내 중앙정부·중앙은행 (한국)":                "central_gov",
        "외국 중앙정부·중앙은행":                       "central_gov",
        "무위험기관 (BIS, IMF, ECB, EU, ESM, EFSF)":  "zero_risk_entity",
        "국내 공공기관 — 정부간주 (신보, 기보 등)":     "pse_gov_like",
        "국내 공공기관 — 은행간주 (정부출자 50% 이상)": "pse_bank_like",
        "국내 공공기관 — 업무감독+재정지원":             "pse_higher",
        "외국 지방정부·공공기관":                       "pse_foreign",
        "우량 국제개발은행 (World Bank, IFC 등, 0%)":   "mdb_zero",
        "일반 국제개발은행 (등급 기반)":                "mdb_general",
    }
    entity_type = _subtype_map.get(subtype_display, "central_gov")
    is_korea = "국내 중앙정부" in subtype_display

    is_local_str = acc.get("is_local_currency")
    if is_local_str:
        is_local = "자국통화" in is_local_str or "예" in is_local_str
    else:
        # 국내 중앙정부 기본값: 원화 → is_local=True
        is_local = is_korea

    return RwaCalculationRequest(
        exposure_category="gov",
        entity_type=entity_type,
        exposure=exposure,
        external_credit_rating=acc.get("external_credit_rating"),
        is_local_currency=is_local,
        is_korea=is_korea,
        country_gov_external_credit_rating=acc.get("country_gov_external_credit_rating"),
    )


def _map_real_estate(acc: dict[str, str]) -> RwaCalculationRequest:
    """
    부동산 익스포져 수집값 → RwaCalculationRequest(exposure_category="realestate")

    re_exposure_type 매핑:
        "상업용 비IPRE (Non-IPRE CRE)" → "cre_non_ipre"
        "상업용 IPRE (수익창출형 CRE)" → "cre_ipre"
        "부동산개발금융 ADC"            → "adc"
        "PF 조합사업비"                 → "pf_consortium"
    """
    exposure = _to_float(acc.get("exposure"), default=0.0) or 0.0

    _type_map = {
        "상업용 비IPRE (Non-IPRE CRE)": "cre_non_ipre",
        "상업용 IPRE (수익창출형 CRE)": "cre_ipre",
        "부동산개발금융 ADC":            "adc",
        "PF 조합사업비":                 "pf_consortium",
    }
    re_type_display = acc.get("re_exposure_type", "")
    re_exposure_type = _type_map.get(re_type_display, "cre_non_ipre")

    ltv_raw = acc.get("ltv_ratio")
    ltv_ratio = _to_float(ltv_raw)  # normalize_ltv validator가 >1 시 /100 처리

    is_eligible = not _bool_from_display(acc.get("is_eligible"), "미충족", "충족")
    # "충족" → True(eligible), "미충족" → False
    if acc.get("is_eligible") == "미충족":
        is_eligible = False
    elif acc.get("is_eligible") == "충족":
        is_eligible = True
    else:
        is_eligible = True  # default

    borrower_rw_raw = acc.get("borrower_risk_weight")
    borrower_rw = _pct_to_fraction(borrower_rw_raw)

    is_residential_exception = _bool_from_display(
        acc.get("is_residential_exception"), "충족", "미충족"
    )
    has_guarantee = _bool_from_display(
        acc.get("has_construction_guarantee"), "예", "아니오"
    )
    contractor_rating = acc.get("contractor_credit_rating")

    return RwaCalculationRequest(
        exposure_category="realestate",
        entity_type=re_exposure_type,
        exposure=exposure,
        re_exposure_type=re_exposure_type,
        ltv_ratio=ltv_ratio,
        is_eligible=is_eligible,
        borrower_risk_weight=borrower_rw,
        is_residential_exception=is_residential_exception,
        has_construction_guarantee=has_guarantee,
        contractor_credit_rating=contractor_rating,
    )


def _map_equity(acc: dict[str, str]) -> RwaCalculationRequest:
    """
    주식 익스포져 수집값 → RwaCalculationRequest(exposure_category="equity")

    equity_type 매핑:
        "일반 상장주식 (250%)"               → "general_listed"
        "비상장 장기보유·출자전환 (250%)"     → "unlisted_long_term"
        "투기적 비상장주식 / VC (400%)"      → "unlisted_speculative"
        "정부보조 프로그램 주식 (100%)"       → "govt_sponsored"
        "후순위채권·기타 자본조달수단 (150%)" → "subordinated_debt"
        "비금융자회사 대규모 출자 초과분 (1250%)"→ "non_financial_large"
    """
    exposure = _to_float(acc.get("exposure"), default=0.0) or 0.0

    _type_map = {
        "일반 상장주식 (250%)":               "general_listed",
        "비상장 장기보유·출자전환 (250%)":     "unlisted_long_term",
        "투기적 비상장주식 / VC (400%)":      "unlisted_speculative",
        "정부보조 프로그램 주식 (100%)":       "govt_sponsored",
        "후순위채권·기타 자본조달수단 (150%)": "subordinated_debt",
        "비금융자회사 대규모 출자 초과분 (1250%)": "non_financial_large",
    }
    equity_display = acc.get("equity_type", "")
    equity_type = _type_map.get(equity_display, "general_listed")

    return RwaCalculationRequest(
        exposure_category="equity",
        entity_type=equity_type,
        exposure=exposure,
        equity_type=equity_type,
    )


def _map_ciu(acc: dict[str, str]) -> RwaCalculationRequest:
    """
    CIU 익스포져 수집값 → RwaCalculationRequest(exposure_category="ciu")

    ciu_approach 매핑:
        "LTA — 투시법 (기초자산 직접 조회)" → "lta"
        "MBA — 위임기준법 (투자제한 기반)"  → "mba"
        "FBA — 폴백법 (정보 없는 경우, 1250% 적용)" → "fba"

    weighted_avg_rw: 사용자 입력이 퍼센트(%) 단위이므로 분수로 변환
        "75" 또는 "75%" → 0.75
    """
    exposure = _to_float(acc.get("exposure"), default=0.0) or 0.0

    _approach_map = {
        "LTA — 투시법 (기초자산 직접 조회)":          "lta",
        "MBA — 위임기준법 (투자제한 기반)":            "mba",
        "FBA — 폴백법 (정보 없는 경우, 1250% 적용)": "fba",
    }
    approach_display = acc.get("ciu_approach", "")
    ciu_approach = _approach_map.get(approach_display, "fba")

    weighted_avg_rw = _pct_to_fraction(acc.get("weighted_avg_rw"))

    return RwaCalculationRequest(
        exposure_category="ciu",
        entity_type=ciu_approach,
        exposure=exposure,
        ciu_approach=ciu_approach,
        weighted_avg_rw=weighted_avg_rw,
    )


# ── 메인 공개 함수 ────────────────────────────────────────────────────────────

def map_to_rwa_request(
    accumulated: dict[str, str], schema: ExposureSchema
) -> RwaCalculationRequest:
    """
    수집된 필드값 dict를 RwaCalculationRequest로 변환한다.

    Raises:
        ValueError: 지원하지 않는 익스포져 유형이거나 변환 불가한 경우
    """
    _mapper = {
        "corporate":  _map_corporate,
        "bank":       _map_bank,
        "sovereign":  _map_sovereign,
        "real_estate": _map_real_estate,
        "equity":     _map_equity,
        "ciu":        _map_ciu,
    }

    mapper_fn = _mapper.get(schema.id)
    if mapper_fn is None:
        raise ValueError(
            f"'{schema.label}' 유형은 계산기가 구현되어 있지 않습니다."
        )

    return mapper_fn(accumulated)


def format_calc_result(
    result: RwaResult,
    accumulated: dict[str, str],
    schema: ExposureSchema,
    sources: dict[str, str] | None = None,
) -> str:
    """
    RwaResult와 수집값을 마크다운 응답 문자열로 포맷팅한다.

    sources가 전달되면 각 필드 옆에 입력 출처 배지를 표시한다.
        "db"   → 🗄️ DB
        "user" → ✏️ 입력

    포함 구조:
      1. 입력값 요약 (출처 포함)
      2. 계산 결과 한 줄 요약
      3. 적용 근거 (계산 엔진에서 반환된 basis 문자열)
    """
    from app.services.rwa_field_parser import format_amount

    _SRC_BADGE = {
        "db":   "🗄️ DB",
        "user": "✏️ 입력",
    }

    # ── 표시할 필드: 필수 + 값이 있는 선택 ─────────────────────────────────
    show_fields = list(schema.required_fields)
    show_fields += [f for f in schema.optional_fields if f.name in accumulated]

    # ── 입력값 표 구성 ───────────────────────────────────────────────────────
    input_lines = []
    for f in show_fields:
        raw = accumulated.get(f.name, "")
        if not raw:
            continue
        display = format_amount(raw) if f.name == "exposure" else raw
        if sources:
            badge = _SRC_BADGE.get(sources.get(f.name, "user"), "✏️ 입력")
            input_lines.append(f"| {f.label} | {display} | {badge} |")
        else:
            input_lines.append(f"| {f.label} | {display} |")

    if sources and input_lines:
        input_table = (
            "| 항목 | 값 | 출처 |\n"
            "|------|-----|------|\n"
            + "\n".join(input_lines)
        )
    elif input_lines:
        input_table = (
            "| 항목 | 값 |\n"
            "|------|----|\n"
            + "\n".join(input_lines)
        )
    else:
        input_table = ""

    # ── 계산 결과 ────────────────────────────────────────────────────────────
    rwa_str = format_amount(str(int(result.rwa)))
    exposure_display = format_amount(accumulated.get("exposure", "0"))

    return (
        f"## {schema.label} RWA 계산 결과\n\n"
        f"**입력값**\n\n"
        f"{input_table}\n\n"
        f"---\n\n"
        f"위험가중치 **{result.risk_weight_pct}** × 익스포져 {exposure_display} = **RWA {rwa_str}**\n\n"
        f"> **근거:** {result.basis}"
    )
