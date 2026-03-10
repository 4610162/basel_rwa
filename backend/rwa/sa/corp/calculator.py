"""
SA 기업(Corporate) 익스포져 RWA 계산기

근거: 은행업감독업무시행세칙 [별표 3] 제2장 제3절

mermaid 다이어그램 노드:
    SA_CORP_1  기업           (제37조)
    SA_CORP_2  기업간주증권회사 (제36조 준용 → 제37조)
    SA_CORP_3  PF/OF/CF      (제38조의2)
    SA_CORP_4  IPRE           (제38조의2 나. → 제41조의2 / 슬롯팅 기준)
    SA_CORP_5  HVCRE          (제38조의2 나. → 제41조의2 / 슬롯팅 기준)
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from rwa.common.types import RwaResult
from .constants import (
    CorpGradeBucket,
    resolve_corp_bucket,
    CORP_LONG_RW,
    CORP_SHORT_RW,
    CORP_SHORT_150_UNRATED_RW,
    CORP_SHORT_50_UNRATED_MIN_RW,
    SL_RATED_RW,
    PF_PRE_OP_UNRATED_RW,
    PF_OP_UNRATED_RW,
    PF_OP_HIGH_QUALITY_UNRATED_RW,
    OF_CF_UNRATED_RW,
    IPRE_SLOTTING_RW,
    HVCRE_SLOTTING_RW,
    SME_REVENUE_THRESHOLD_EOK,
    SME_ASSET_THRESHOLD_EOK,
    SME_UNRATED_RW,
)


# ── 열거형 ──────────────────────────────────────────────────────────────

class CorpEntityType(Enum):
    """기업 익스포져 유형"""
    GENERAL       = "general"        # SA_CORP_1: 일반기업 장기등급 [제37조]
    GENERAL_SHORT = "general_short"  # SA_CORP_1: 일반기업 단기등급 [제38조]
    SL_PF         = "sl_pf"          # SA_CORP_3: 프로젝트금융 [제38조의2]
    SL_OF         = "sl_of"          # SA_CORP_3: 오브젝트금융 [제38조의2]
    SL_CF         = "sl_cf"          # SA_CORP_3: 상품금융 [제38조의2]
    IPRE          = "ipre"           # SA_CORP_4: 수익창출 부동산금융 [슬롯팅]
    HVCRE         = "hvcre"          # SA_CORP_5: 고변동성 상업용 부동산금융 [슬롯팅]


class PFStage(Enum):
    """
    프로젝트금융(PF) 운영 단계 — 무등급 위험가중치 분기 기준 [제38조의2 라.·마.]

    운영 단계로 분류하기 위해서는:
    - 잔존 계약 의무를 충당할 충분한 양(+)의 현금흐름 발생
    - 장기부채가 감소 추세
    """
    PRE_OPERATIONAL      = "pre_op"        # 운영전: 130%
    OPERATIONAL          = "operational"   # 운영 중: 100%
    OPERATIONAL_HIGH_QUALITY = "op_hq"    # 우량 운영(5개 요건 모두 충족): 80%


class SlottingGrade(Enum):
    """
    특수금융 표준등급분류기준(Slotting Criteria) — IPRE·HVCRE 적용
    근거: 제120조 다. 〈표 2〉 표준등급분류기준
    """
    STRONG       = "STRONG"        # 우량
    GOOD         = "GOOD"          # 양호
    SATISFACTORY = "SATISFACTORY"  # 보통
    WEAK         = "WEAK"          # 취약
    DEFAULT      = "DEFAULT"       # 부도


# ── 입력 데이터 클래스 ─────────────────────────────────────────────────

@dataclass
class CorporateExposureInput:
    """
    기업 익스포져 RWA 산출 입력값

    Fields:
        exposure:               익스포져 금액 (원화, 단위: 원)
        entity_type:            기업 유형 (CorpEntityType)
        external_credit_rating:               적격외부신용등급 (예: "BBB+"), None=무등급
        short_grade:            단기 신용등급 (A-1/A-2/A-3/OTHER), GENERAL_SHORT 시 사용
        is_sme_legal:           「중소기업기본법」상 중소기업 여부 (True이면 85% 적용 가능)
        annual_revenue_eok:     연간 매출액 (억원). 양수 입력 시 700억 이하 자동 판정
        total_assets_eok:       총자산 (억원). 매출액 기준 부적합 시 2,300억 이하 판정
        country_floor_rw:       제37조 나. 무등급 하한 — 설립국 중앙정부 위험가중치
        debtor_short_rw:        제38조 나.·다. — 동일 채무자에 부여된 단기등급 위험가중치
                                (150% 시 무등급 장기도 150%; 50% 시 무등급 단기 최소 100%)
        pf_stage:               PF 운영 단계 (PFStage), SL_PF 무등급 시 사용
        pf_op_high_quality:     PF 우량 운영 여부 — 제38조의2 마. 5개 요건 충족 시 True
        slotting_grade:         슬롯팅 등급 (SlottingGrade), IPRE·HVCRE 시 사용
        slotting_short_or_safe: 잔존만기 2년6개월 이내 또는 안전성 입증 여부
                                (True 시 IPRE·HVCRE 우량·양호 우대 가중치 적용)
        entity_name:            기관명 또는 여신명 (참고용)
    """
    exposure:               float
    entity_type:            CorpEntityType
    external_credit_rating:               Optional[str]   = None
    short_grade:            Optional[str]   = None
    is_sme_legal:           bool            = False
    annual_revenue_eok:     float           = 0.0
    total_assets_eok:       float           = 0.0
    country_floor_rw:       Optional[float] = None
    debtor_short_rw:        Optional[float] = None
    pf_stage:               PFStage         = PFStage.OPERATIONAL
    pf_op_high_quality:     bool            = False
    slotting_grade:         Optional[SlottingGrade] = None
    slotting_short_or_safe: bool            = False
    entity_name:            Optional[str]   = None


# ── 메인 산출 클래스 ───────────────────────────────────────────────────

class CorporateCalculator:
    """
    신용 RWA 표준방법(SA) — 기업(Corporate) 익스포져 위험가중치·RWA 계산기

    적용 범위:
        제37조 가.    기업 익스포져, 장기 외부신용등급 기반
        제37조 나.    무등급 기업, 설립국 위험가중치 하한
        제37조 다.    중소기업(SME) 무등급 익스포져 85% 우대
        제38조        기업 단기 신용등급 위험가중치
        제38조의2 다. 특수금융(PF·OF·CF) 외부등급 위험가중치
        제38조의2 라. 특수금융(PF·OF·CF) 무등급 위험가중치
        제38조의2 마. PF 우량 운영 단계 80% 우대
        슬롯팅 기준   IPRE·HVCRE (제120조 다. 준용)
    """

    # ── 제37조: 일반기업 장기등급 ────────────────────────────────────────

    def calc_rw_corp(
        self,
        external_credit_rating:           Optional[str]   = None,
        is_sme_legal:       bool            = False,
        annual_revenue_eok: float           = 0.0,
        total_assets_eok:   float           = 0.0,
        country_floor_rw:   Optional[float] = None,
    ) -> float:
        """
        [SA_CORP_1] 일반기업 익스포져 위험가중치 — 장기 외부신용등급 기반

        근거: 제37조 (기업 익스포져)

        장기등급 위험가중치 테이블 [제37조 가.]:
        | 표준신용등급 | AAA~AA- | A+~A- | BBB+~BBB- | BB+~BB- | BB-미만 | 무등급 |
        |-----------|---------|-------|-----------|---------|--------|------|
        | 위험가중치 |   20%   |  50%  |    75%    |  100%   |  150%  | 100% |

        무등급 특칙:
        - 제37조 나.: 설립국 위험가중치보다 낮을 수 없음 (country_floor_rw 입력 시 적용)
        - 제37조 다.: 중소기업(SME) 무등급은 85% 적용 가능

        SME 판정 우선순위:
        1. is_sme_legal=True → 법적 중소기업 (「중소기업기본법」)
        2. annual_revenue_eok > 0 → 연간 매출액 700억원 이하 여부로 판정
        3. total_assets_eok > 0  → 총자산 2,300억원 이하 (매출액 기준 부적합 시)

        Args:
            external_credit_rating:           적격외부신용등급 (예: "BBB+"), None=무등급
            is_sme_legal:       「중소기업기본법」상 중소기업 여부
            annual_revenue_eok: 연간 매출액 (억원). 양수 입력 시 700억원 이하 자동 판정
            total_assets_eok:   총자산 (억원). 매출액 미입력 시 2,300억원 이하 판정
            country_floor_rw:   설립국 중앙정부 위험가중치 (제37조 나. 하한)

        Returns:
            위험가중치 (0.0~1.5)
        """
        bucket = resolve_corp_bucket(external_credit_rating)
        rw = CORP_LONG_RW[bucket]

        if bucket == CorpGradeBucket.UNRATED:
            # ▶ 제37조 다.: SME 무등급 → 85%
            if self._is_sme(is_sme_legal, annual_revenue_eok, total_assets_eok):
                rw = SME_UNRATED_RW   # 85%

            # ▶ 제37조 나.: 설립국 위험가중치 하한
            if country_floor_rw is not None:
                rw = max(rw, country_floor_rw)

        return rw

    # ── 제38조: 기업 단기 신용등급 ───────────────────────────────────────

    def calc_rw_corp_short(
        self,
        short_grade:     str,
        debtor_short_rw: Optional[float] = None,
        is_unrated:      bool            = False,
    ) -> float:
        """
        [SA_CORP_1] 기업 단기 익스포져 위험가중치 — 단기 외부신용등급 기반

        근거: 제38조 (장기/단기 신용등급)

        단기등급 위험가중치 테이블 [제38조 가.]:
        | 표준신용등급 | A-1 | A-2 | A-3  | 기타(non-prime/B/C) |
        |-----------|-----|-----|------|-------------------|
        | 위험가중치  | 20% | 50% | 100% |       150%        |

        무등급 단기 익스포져 특칙 [제38조 나.·다.]:
        - 동일 채무자에 150%(OTHER) 단기등급 적용 시: 무등급 익스포져도 150%
        - 동일 채무자에 50%(A-2) 단기등급 적용 시: 무등급 단기 최소 100%

        Args:
            short_grade:      단기 신용등급 ("A-1", "A-2", "A-3", "OTHER")
            debtor_short_rw:  동일 채무자의 다른 단기등급 위험가중치 (나.·다. 적용 시)
            is_unrated:       True이면 해당 익스포져가 무등급 단기인 경우 (다. 적용 시)

        Returns:
            위험가중치 (0.0~1.5)

        Raises:
            ValueError: 허용되지 않는 단기등급 값
        """
        grade = short_grade.strip().upper()
        rw = CORP_SHORT_RW.get(grade)
        if rw is None:
            raise ValueError(
                f"제38조 가.: 허용되지 않는 단기 신용등급 {short_grade!r}. "
                "허용값: 'A-1', 'A-2', 'A-3', 'OTHER'"
            )

        # ▶ 제38조 나.: 150% 단기등급 채무자의 무등급 익스포져 → 150%
        if debtor_short_rw is not None and debtor_short_rw >= CORP_SHORT_150_UNRATED_RW:
            rw = max(rw, CORP_SHORT_150_UNRATED_RW)

        # ▶ 제38조 다.: A-2(50%) 단기등급 채무자의 무등급 단기 익스포져 → 최소 100%
        if is_unrated and debtor_short_rw is not None and debtor_short_rw == 0.50:
            rw = max(rw, CORP_SHORT_50_UNRATED_MIN_RW)

        return rw

    # ── 제38조의2: 특수금융(PF·OF·CF) ────────────────────────────────────

    def calc_rw_specialised_lending(
        self,
        sl_type:            str,
        external_credit_rating:           Optional[str] = None,
        pf_stage:           PFStage       = PFStage.OPERATIONAL,
        pf_op_high_quality: bool          = False,
    ) -> float:
        """
        [SA_CORP_3] 특수금융(PF·OF·CF) 익스포져 위험가중치

        근거: 제38조의2 (특수금융 익스포져)

        외부등급 있는 경우 [제38조의2 다.]:
        | 표준신용등급 | AAA~AA- | A+~A- | BBB+~BBB- | BB+~BB- | BB-미만 |
        |-----------|---------|-------|-----------|---------|--------|
        | 위험가중치 |   20%   |  50%  |    75%    |  100%   |  150%  |

        외부등급 없는 경우 [제38조의2 라.·마.]:
        - PF 운영전(pre-op):       130%
        - PF 운영(operational):    100%
        - PF 우량 운영(5개 요건): 80%  [제38조의2 마. (1)~(8) 전부 충족]
        - OF·CF:                   100%

        Args:
            sl_type:            특수금융 유형 ("PF", "OF", "CF")
            external_credit_rating:           적격외부신용등급, None=무등급
            pf_stage:           PF 운영 단계 (무등급 PF에 한해 적용)
            pf_op_high_quality: PF 우량 운영 여부 (제38조의2 마. 5개 요건 충족)

        Returns:
            위험가중치 (0.0~1.5)

        Raises:
            ValueError: 허용되지 않는 sl_type 값
        """
        sl_type_upper = sl_type.strip().upper()
        if sl_type_upper not in ("PF", "OF", "CF"):
            raise ValueError(
                f"제38조의2: 허용되지 않는 특수금융 유형 {sl_type!r}. "
                "허용값: 'PF', 'OF', 'CF'. IPRE/HVCRE는 calc_rw_ipre()/calc_rw_hvcre() 사용."
            )

        if external_credit_rating is not None:
            # ▶ 제38조의2 다.: 외부등급 있는 경우
            bucket = resolve_corp_bucket(external_credit_rating)
            rw = SL_RATED_RW.get(bucket)
            if rw is None:
                raise ValueError(
                    f"제38조의2 다.: 무등급 버킷({bucket.value})은 외부등급 테이블에 없습니다. "
                    "external_credit_rating=None으로 호출하거나 외부등급을 입력하세요."
                )
            return rw

        # ▶ 제38조의2 라.·마.: 무등급
        if sl_type_upper == "PF":
            if pf_stage == PFStage.PRE_OPERATIONAL:
                return PF_PRE_OP_UNRATED_RW              # 130%
            if pf_op_high_quality:
                return PF_OP_HIGH_QUALITY_UNRATED_RW     # 80%
            return PF_OP_UNRATED_RW                      # 100%

        return OF_CF_UNRATED_RW  # OF, CF: 100%

    # ── IPRE: 수익창출 부동산금융 슬롯팅 ─────────────────────────────────

    def calc_rw_ipre(
        self,
        slotting_grade:  SlottingGrade,
        short_or_safe:   bool = False,
    ) -> float:
        """
        [SA_CORP_4] IPRE (수익창출 부동산금융) 슬롯팅 기준 위험가중치

        근거: 제120조 다. 표준등급분류기준 (Slotting Criteria)
             (SA에서 IPRE는 제38조의2 나.에 따라 제41조의2 참조;
              슬롯팅 기준은 IRB 적용 은행 및 실무상 SA 산출 시 공통 인용)

        슬롯팅 위험가중치 테이블:
        | 등급(Slotting)  | 우량(Strong) | 양호(Good) | 보통(Satisfactory) | 취약(Weak) | 부도(Default) |
        |----------------|------------|----------|-----------------|---------|------------|
        | 기본 RW         |    70%     |   90%    |     115%        |   250%  |     0%     |
        | 단기/안전 RW    |    50%     |   70%    |     115%        |   250%  |     0%     |

        Args:
            slotting_grade:  슬롯팅 등급 (SlottingGrade)
            short_or_safe:   잔존만기 2년6개월 이내 또는 해당 등급 기준보다 안전함 입증 시 True
                             → 우량·양호에 한해 우대 위험가중치 적용

        Returns:
            위험가중치 (0.0~2.5)
        """
        standard_rw, preferred_rw = IPRE_SLOTTING_RW[slotting_grade.value]
        return preferred_rw if short_or_safe else standard_rw

    # ── HVCRE: 고변동성 상업용 부동산금융 슬롯팅 ──────────────────────────

    def calc_rw_hvcre(
        self,
        slotting_grade: SlottingGrade,
        short_or_safe:  bool = False,
    ) -> float:
        """
        [SA_CORP_5] HVCRE (고변동성 상업용 부동산금융) 슬롯팅 기준 위험가중치

        근거: 제120조 다. 표준등급분류기준 (Slotting Criteria)

        슬롯팅 위험가중치 테이블:
        | 등급(Slotting)  | 우량(Strong) | 양호(Good) | 보통(Satisfactory) | 취약(Weak) | 부도(Default) |
        |----------------|------------|----------|-----------------|---------|------------|
        | 기본 RW         |    95%     |  120%    |     140%        |   250%  |     0%     |
        | 단기/안전 RW    |    70%     |   95%    |     140%        |   250%  |     0%     |

        Args:
            slotting_grade: 슬롯팅 등급 (SlottingGrade)
            short_or_safe:  잔존만기 2년6개월 이내 또는 안전성 입증 시 True

        Returns:
            위험가중치 (0.0~2.5)
        """
        standard_rw, preferred_rw = HVCRE_SLOTTING_RW[slotting_grade.value]
        return preferred_rw if short_or_safe else standard_rw

    # ── 통합 진입점 ────────────────────────────────────────────────────

    def calc_rwa(self, inp: CorporateExposureInput) -> RwaResult:
        """
        CorporateExposureInput을 받아 RW와 RWA를 산출하는 통합 진입점.
        entity_type에 따라 각 calc_rw_*() 메서드를 호출한다.

        Args:
            inp: CorporateExposureInput 데이터클래스

        Returns:
            RwaResult — entity_type, risk_weight, rwa, basis 포함
        """
        dispatch = {
            CorpEntityType.GENERAL:       self._handle_general,
            CorpEntityType.GENERAL_SHORT: self._handle_general_short,
            CorpEntityType.SL_PF:         self._handle_sl_pf,
            CorpEntityType.SL_OF:         self._handle_sl_of,
            CorpEntityType.SL_CF:         self._handle_sl_cf,
            CorpEntityType.IPRE:          self._handle_ipre,
            CorpEntityType.HVCRE:         self._handle_hvcre,
        }
        handler = dispatch.get(inp.entity_type)
        if handler is None:
            raise ValueError(f"처리되지 않은 CorpEntityType: {inp.entity_type}")
        rw, basis = handler(inp)
        return RwaResult(
            entity_type=inp.entity_type.value,
            risk_weight=rw,
            rwa=inp.exposure * rw,
            basis=basis,
        )

    # ── 내부 핸들러 ───────────────────────────────────────────────────

    def _handle_general(self, inp: CorporateExposureInput) -> tuple[float, str]:
        rw = self.calc_rw_corp(
            external_credit_rating=inp.external_credit_rating,
            is_sme_legal=inp.is_sme_legal,
            annual_revenue_eok=inp.annual_revenue_eok,
            total_assets_eok=inp.total_assets_eok,
            country_floor_rw=inp.country_floor_rw,
        )
        bucket = resolve_corp_bucket(inp.external_credit_rating)
        if bucket == CorpGradeBucket.UNRATED:
            sme = self._is_sme(inp.is_sme_legal, inp.annual_revenue_eok, inp.total_assets_eok)
            basis = "제37조 다. (중소기업 무등급 85%)" if sme else "제37조 가. (무등급 100%)"
            if inp.country_floor_rw is not None:
                basis += ", 제37조 나. (설립국 하한 적용)"
        else:
            basis = f"제37조 가. (장기등급 {bucket.value} → {rw:.0%})"
        return rw, basis

    def _handle_general_short(self, inp: CorporateExposureInput) -> tuple[float, str]:
        if inp.short_grade is None:
            raise ValueError("CorpEntityType.GENERAL_SHORT: short_grade가 필요합니다.")
        rw = self.calc_rw_corp_short(
            short_grade=inp.short_grade,
            debtor_short_rw=inp.debtor_short_rw,
        )
        return rw, f"제38조 가. (단기등급 {inp.short_grade} → {rw:.0%})"

    def _handle_sl_pf(self, inp: CorporateExposureInput) -> tuple[float, str]:
        rw = self.calc_rw_specialised_lending(
            sl_type="PF",
            external_credit_rating=inp.external_credit_rating,
            pf_stage=inp.pf_stage,
            pf_op_high_quality=inp.pf_op_high_quality,
        )
        if inp.external_credit_rating is not None:
            basis = f"제38조의2 다. (PF 외부등급 {inp.external_credit_rating} → {rw:.0%})"
        elif inp.pf_op_high_quality:
            basis = "제38조의2 마. (PF 우량 운영, 무등급 → 80%)"
        elif inp.pf_stage == PFStage.PRE_OPERATIONAL:
            basis = "제38조의2 라. (PF 운영전, 무등급 → 130%)"
        else:
            basis = "제38조의2 라. (PF 운영 중, 무등급 → 100%)"
        return rw, basis

    def _handle_sl_of(self, inp: CorporateExposureInput) -> tuple[float, str]:
        rw = self.calc_rw_specialised_lending(
            sl_type="OF",
            external_credit_rating=inp.external_credit_rating,
        )
        if inp.external_credit_rating is not None:
            basis = f"제38조의2 다. (OF 외부등급 {inp.external_credit_rating} → {rw:.0%})"
        else:
            basis = "제38조의2 라. (OF 무등급 → 100%)"
        return rw, basis

    def _handle_sl_cf(self, inp: CorporateExposureInput) -> tuple[float, str]:
        rw = self.calc_rw_specialised_lending(
            sl_type="CF",
            external_credit_rating=inp.external_credit_rating,
        )
        if inp.external_credit_rating is not None:
            basis = f"제38조의2 다. (CF 외부등급 {inp.external_credit_rating} → {rw:.0%})"
        else:
            basis = "제38조의2 라. (CF 무등급 → 100%)"
        return rw, basis

    def _handle_ipre(self, inp: CorporateExposureInput) -> tuple[float, str]:
        if inp.slotting_grade is None:
            raise ValueError("CorpEntityType.IPRE: slotting_grade가 필요합니다.")
        rw = self.calc_rw_ipre(inp.slotting_grade, inp.slotting_short_or_safe)
        suffix = " (단기/안전 우대)" if inp.slotting_short_or_safe else ""
        basis = f"슬롯팅 기준 (IPRE {inp.slotting_grade.value}{suffix} → {rw:.0%})"
        return rw, basis

    def _handle_hvcre(self, inp: CorporateExposureInput) -> tuple[float, str]:
        if inp.slotting_grade is None:
            raise ValueError("CorpEntityType.HVCRE: slotting_grade가 필요합니다.")
        rw = self.calc_rw_hvcre(inp.slotting_grade, inp.slotting_short_or_safe)
        suffix = " (단기/안전 우대)" if inp.slotting_short_or_safe else ""
        basis = f"슬롯팅 기준 (HVCRE {inp.slotting_grade.value}{suffix} → {rw:.0%})"
        return rw, basis

    # ── 내부 유틸리티 ─────────────────────────────────────────────────

    def _is_sme(
        self,
        is_sme_legal:       bool,
        annual_revenue_eok: float,
        total_assets_eok:   float,
    ) -> bool:
        """
        제37조 다. SME(중소기업) 해당 여부 판정.

        판정 우선순위:
        1. is_sme_legal=True → 「중소기업기본법」상 중소기업
        2. annual_revenue_eok > 0 → 연간 매출액 700억원 이하
        3. total_assets_eok > 0  → 총자산 2,300억원 이하
           (매출액이 규모 판단 기준으로 부적합한 경우에 한해 적용)
        """
        if is_sme_legal:
            return True
        if annual_revenue_eok > 0:
            return annual_revenue_eok <= SME_REVENUE_THRESHOLD_EOK
        if total_assets_eok > 0:
            return total_assets_eok <= SME_ASSET_THRESHOLD_EOK
        return False
