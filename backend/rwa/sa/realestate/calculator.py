"""
SA 부동산 관련 익스포져 RWA 계산기

근거: 은행업감독업무시행세칙 [별표 3] 제2장 제3절

mermaid 다이어그램 노드:
    SA_CRE    상업용부동산담보(CRE) 익스포져  (제41조)
    SA_ADC    부동산개발금융(ADC) 익스포져    (제41조의2)
    SA_PFC    PF조합사업비 익스포져            (제41조의2 준용)

위험가중치 체계 요약:

[CRE — 제41조]
    가. 비-IPRE (상환재원이 담보물 현금흐름에 의존 안 함):
        LTV ≤ 60% AND 적격요건 충족 → min(60%, 차주 RW)
        LTV > 60% 또는 적격요건 미충족 → 차주 RW

    나. IPRE (상환재원이 임대료·리스료·매각자금 등 담보물 현금흐름에 주로 의존):
        적격요건 미충족            → 150%
        LTV ≤ 60%                → 70%
        60% < LTV ≤ 80%         → 90%
        LTV > 80%                → 110%

[ADC — 제41조의2]
    기본                         → 150%
    주거용 예외 요건 (1)(2) 충족   → 100%

[PF조합사업비 — 제41조의2 준용]
    기본                         → 150%
    시공사 연대보증 + 적격외부등급  → 시공사 기업 익스포져 SA 위험가중치 적용
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from rwa.common.types import RwaResult
from .constants import (
    CRE_NON_IPRE_CAP_RW,
    CRE_NON_IPRE_LTV_THRESHOLD,
    CRE_IPRE_LTV_60,
    CRE_IPRE_LTV_80,
    CRE_IPRE_RW_60,
    CRE_IPRE_RW_80,
    CRE_IPRE_RW_OVER,
    CRE_INELIGIBLE_RW,
    ADC_DEFAULT_RW,
    ADC_RESIDENTIAL_RW,
    PF_CONSORTIUM_DEFAULT_RW,
)


# ── 열거형 ───────────────────────────────────────────────────────────────────

class RealEstateExposureType(Enum):
    """
    부동산 관련 익스포져 세부 유형

    CRE_NON_IPRE : 상업용부동산 — 비수익형 (상환재원이 담보물 현금흐름에 의존 안 함) [제41조 가.]
    CRE_IPRE     : 상업용부동산 — 수익형   (상환재원이 담보물 현금흐름에 주로 의존) [제41조 나.]
    ADC          : 부동산개발금융 (ADC)                                              [제41조의2]
    PF_CONSORTIUM: PF조합사업비 (부동산개발금융 준용, 시공사 연대보증 특례 포함)       [제41조의2 준용]
    """
    CRE_NON_IPRE  = "cre_non_ipre"
    CRE_IPRE      = "cre_ipre"
    ADC           = "adc"
    PF_CONSORTIUM = "pf_consortium"


# ── 입력 데이터클래스 ─────────────────────────────────────────────────────────

@dataclass
class RealEstateExposureInput:
    """
    부동산 관련 익스포져 RWA 산출 입력값

    Parameters
    ----------
    exposure : float
        익스포져 금액 (원화, 단위: 원)
    exposure_type : RealEstateExposureType
        부동산 익스포져 유형
    ltv : float, optional
        담보인정비율 (0.0 ~ 1.0). CRE 유형에서 필수.
        예: 0.65 = LTV 65%
    meets_eligibility : bool
        40.가. 부동산담보 적격요건 충족 여부.
        CRE_IPRE에서 False이면 즉시 150% 적용.
        CRE_NON_IPRE에서 False이면 LTV와 무관하게 차주 RW 적용.
        기본값 True.
    borrower_rw : float, optional
        차주의 위험가중치 (예: 1.00 = 100%).
        CRE_NON_IPRE 유형에서 필수.
    is_residential_exception : bool
        [ADC / PF_CONSORTIUM 전용]
        주거용 예외 요건 (1)(2)를 모두 충족하는지 여부.
        True이면 ADC 100% 적용 (기본 150% 대신).
        기본값 False.
    has_construction_guarantee : bool
        [PF_CONSORTIUM 전용]
        시공사 연대보증이 있는 경우 True.
        True이면 guarantor_corp_rwa를 통해 산출된 기업 RWA를 사용.
        기본값 False.
    guarantor_corp_rwa : RwaResult, optional
        [PF_CONSORTIUM 전용]
        시공사의 기업 익스포져 표준방법 RWA 산출 결과.
        has_construction_guarantee=True일 때 필요.
        제공되면 해당 risk_weight를 PF조합사업비에 그대로 적용.
    guarantor_exposure : float, optional
        [PF_CONSORTIUM 전용]
        시공사 연대보증금액 (원화, 단위: 원).
        PF조합사업비 익스포져보다 작으면 부분 보증으로 처리:
            · 연대보증금액 → 시공사 기업 SA RW 적용
            · 잔액 → 150% 적용 (PF조합사업비 기본)
        None 또는 0이거나 PF익스포져 이상이면 전액 보증으로 처리.
    entity_name : str, optional
        여신 또는 기관명 (참고·보고용)
    """
    exposure: float
    exposure_type: RealEstateExposureType
    ltv: Optional[float] = None
    meets_eligibility: bool = True
    borrower_rw: Optional[float] = None
    is_residential_exception: bool = False
    has_construction_guarantee: bool = False
    guarantor_corp_rwa: Optional[RwaResult] = None
    guarantor_exposure: Optional[float] = None
    entity_name: Optional[str] = None


# ── 메인 산출 클래스 ──────────────────────────────────────────────────────────

class RealEstateCalculator:
    """
    SA 부동산 관련 익스포져 위험가중치·RWA 계산기

    적용 범위:
        제41조 가.    CRE 비수익형 (LTV 기반, 차주 RW 연동)
        제41조 나.    CRE 수익형/IPRE (LTV 구간별 고정 RW)
        제41조의2     ADC 부동산개발금융 (기본 150%, 주거용 예외 100%)
        제41조의2 준용 PF조합사업비 (기본 150%, 시공사 보증 시 기업 RW)
    """

    # ── 공개 인터페이스 ──────────────────────────────────────────────────────

    def calc_rw_cre(
        self,
        ltv: float,
        is_ipre: bool,
        meets_eligibility: bool = True,
        borrower_rw: Optional[float] = None,
    ) -> float:
        """
        [SA_CRE] 상업용부동산담보 익스포져 위험가중치 반환

        근거: 제41조 (상업용부동산 익스포져)

        가. 비-IPRE (is_ipre=False) — LTV 기반, 차주 RW 연동:
        ┌────────────────────────────────────────────────┬──────────────────────┐
        │ 조건                                            │ 위험가중치            │
        ├────────────────────────────────────────────────┼──────────────────────┤
        │ LTV ≤ 60% AND 적격요건 충족                     │ min(60%, 차주 RW)    │
        │ LTV > 60% 또는 적격요건 미충족                  │ 차주 RW              │
        └────────────────────────────────────────────────┴──────────────────────┘

        나. IPRE (is_ipre=True) — 고정 구간별 RW:
        ┌─────────────────────┬─────────┐
        │ 조건                 │ 위험가중치│
        ├─────────────────────┼─────────┤
        │ 적격요건 미충족       │ 150%    │
        │ LTV ≤ 60%           │ 70%     │
        │ 60% < LTV ≤ 80%    │ 90%     │
        │ LTV > 80%           │ 110%    │
        └─────────────────────┴─────────┘

        Parameters
        ----------
        ltv : float
            담보인정비율 (0.0 ~ 1.0)
        is_ipre : bool
            True=IPRE(수익형, 나. 적용) / False=비수익형(가. 적용)
        meets_eligibility : bool
            40.가. 부동산담보 적격요건 충족 여부
        borrower_rw : float, optional
            차주 위험가중치. 비-IPRE(가.) 산출 시 필수.

        Returns
        -------
        float
            위험가중치 (예: 0.70 = 70%)

        Raises
        ------
        ValueError
            비-IPRE에서 borrower_rw 미제공 시
        """
        if is_ipre:
            return self._rw_cre_ipre(ltv, meets_eligibility)
        return self._rw_cre_non_ipre(ltv, meets_eligibility, borrower_rw)

    def calc_rw_adc(self, is_residential_exception: bool = False) -> float:
        """
        [SA_ADC] 부동산개발금융 익스포져 위험가중치 반환

        근거: 제41조의2 (부동산개발금융 익스포져)

        ┌─────────────────────────────────────────────────┬──────────┐
        │ 조건                                             │ 위험가중치│
        ├─────────────────────────────────────────────────┼──────────┤
        │ 기본 (원칙)                                      │ 150%     │
        │ 주거용 예외 요건 (1)(2) 모두 충족                 │ 100%     │
        └─────────────────────────────────────────────────┴──────────┘

        주거용 예외 요건 [제41조의2 단서]:
            (1) 40.가.(2)~(6)의 부동산담보 적격요건 모두 충족
            (2) 전체 계약 중 상당한 비중이 사전 매매·임대 계약 체결
                (문서화된 법적 구속력 있는 계약, 계약해지 시 몰수 가능한 계약금 포함)

        Parameters
        ----------
        is_residential_exception : bool
            주거용 예외 요건 (1)(2)를 모두 충족하면 True

        Returns
        -------
        float
            위험가중치 (1.00 또는 1.50)
        """
        return ADC_RESIDENTIAL_RW if is_residential_exception else ADC_DEFAULT_RW

    def calc_rw_pf_consortium(
        self,
        is_residential_exception: bool = False,
        has_construction_guarantee: bool = False,
        guarantor_corp_rwa: Optional[RwaResult] = None,
    ) -> float:
        """
        [SA_PFC] PF조합사업비 위험가중치 반환

        근거: 제41조의2 준용 (부동산개발금융과 동일 원칙)

        ┌──────────────────────────────────────────────────────┬────────────────────────┐
        │ 조건                                                  │ 위험가중치              │
        ├──────────────────────────────────────────────────────┼────────────────────────┤
        │ 기본 (원칙)                                           │ 150%                   │
        │ 주거용 예외 요건 충족 (is_residential_exception=True)  │ 100%                   │
        │ 시공사 연대보증 + 적격외부신용등급 (guarantor_corp_rwa) │ 시공사 기업 SA RW 적용  │
        └──────────────────────────────────────────────────────┴────────────────────────┘

        우선순위:
            1. 시공사 연대보증 + guarantor_corp_rwa 제공 → 시공사 기업 RW 사용
            2. 주거용 예외 요건 충족 → 100%
            3. 기본 → 150%

        Parameters
        ----------
        is_residential_exception : bool
            주거용 예외 요건 충족 여부 (ADC와 동일 기준)
        has_construction_guarantee : bool
            시공사 연대보증 존재 여부
        guarantor_corp_rwa : RwaResult, optional
            시공사의 기업 익스포져 표준방법 RWA 산출 결과.
            has_construction_guarantee=True일 때 제공.

        Returns
        -------
        float
            위험가중치
        """
        if has_construction_guarantee and guarantor_corp_rwa is not None:
            return guarantor_corp_rwa["risk_weight"]
        if is_residential_exception:
            return ADC_RESIDENTIAL_RW
        return PF_CONSORTIUM_DEFAULT_RW

    def calc_rwa(self, inp: RealEstateExposureInput) -> RwaResult:
        """
        RealEstateExposureInput을 받아 RW와 RWA를 산출하는 통합 진입점.

        Parameters
        ----------
        inp : RealEstateExposureInput

        Returns
        -------
        RwaResult
            entity_type, risk_weight, rwa, basis 포함

        Raises
        ------
        ValueError
            exposure_type이 처리되지 않은 경우
        """
        dispatch = {
            RealEstateExposureType.CRE_NON_IPRE:  self._handle_cre_non_ipre,
            RealEstateExposureType.CRE_IPRE:       self._handle_cre_ipre,
            RealEstateExposureType.ADC:            self._handle_adc,
            RealEstateExposureType.PF_CONSORTIUM:  self._handle_pf_consortium,
        }
        handler = dispatch.get(inp.exposure_type)
        if handler is None:
            raise ValueError(f"처리되지 않은 RealEstateExposureType: {inp.exposure_type}")
        rw, basis = handler(inp)
        return RwaResult(
            entity_type=inp.exposure_type.value,
            risk_weight=rw,
            rwa=inp.exposure * rw,
            basis=basis,
        )

    # ── 내부 위험가중치 로직 ─────────────────────────────────────────────────

    def _rw_cre_non_ipre(
        self,
        ltv: float,
        meets_eligibility: bool,
        borrower_rw: Optional[float],
    ) -> float:
        """제41조 가. — 비-IPRE CRE 위험가중치"""
        if borrower_rw is None:
            raise ValueError(
                "제41조 가. (CRE 비수익형): borrower_rw(차주 위험가중치)가 필요합니다."
            )
        if meets_eligibility and ltv <= CRE_NON_IPRE_LTV_THRESHOLD:
            return min(CRE_NON_IPRE_CAP_RW, borrower_rw)
        return borrower_rw

    def _rw_cre_ipre(self, ltv: float, meets_eligibility: bool) -> float:
        """제41조 나. — IPRE CRE 위험가중치"""
        if not meets_eligibility:
            return CRE_INELIGIBLE_RW
        if ltv <= CRE_IPRE_LTV_60:
            return CRE_IPRE_RW_60
        if ltv <= CRE_IPRE_LTV_80:
            return CRE_IPRE_RW_80
        return CRE_IPRE_RW_OVER

    # ── 내부 핸들러 ──────────────────────────────────────────────────────────

    def _handle_cre_non_ipre(
        self, inp: RealEstateExposureInput
    ) -> tuple[float, str]:
        ltv = self._require_ltv(inp)
        rw = self._rw_cre_non_ipre(ltv, inp.meets_eligibility, inp.borrower_rw)
        if inp.meets_eligibility and ltv <= CRE_NON_IPRE_LTV_THRESHOLD:
            basis = (
                f"제41조 가. (CRE 비수익형, LTV {ltv:.0%} ≤ 60%, 적격요건 충족 → "
                f"min(60%, 차주RW {inp.borrower_rw:.0%}) = {rw:.0%})"
            )
        else:
            reason = "LTV > 60%" if ltv > CRE_NON_IPRE_LTV_THRESHOLD else "적격요건 미충족"
            basis = (
                f"제41조 가. (CRE 비수익형, {reason} → 차주 RW {rw:.0%})"
            )
        return rw, basis

    def _handle_cre_ipre(
        self, inp: RealEstateExposureInput
    ) -> tuple[float, str]:
        ltv = self._require_ltv(inp)
        rw = self._rw_cre_ipre(ltv, inp.meets_eligibility)
        if not inp.meets_eligibility:
            basis = f"제41조 나. (CRE IPRE, 적격요건 미충족 → 150%)"
        elif ltv <= CRE_IPRE_LTV_60:
            basis = f"제41조 나. (CRE IPRE, LTV {ltv:.0%} ≤ 60% → 70%)"
        elif ltv <= CRE_IPRE_LTV_80:
            basis = f"제41조 나. (CRE IPRE, 60% < LTV {ltv:.0%} ≤ 80% → 90%)"
        else:
            basis = f"제41조 나. (CRE IPRE, LTV {ltv:.0%} > 80% → 110%)"
        return rw, basis

    def _handle_adc(
        self, inp: RealEstateExposureInput
    ) -> tuple[float, str]:
        rw = self.calc_rw_adc(inp.is_residential_exception)
        if inp.is_residential_exception:
            basis = "제41조의2 (ADC, 주거용 예외 요건 충족 → 100%)"
        else:
            basis = "제41조의2 (ADC 기본 → 150%)"
        return rw, basis

    def _handle_pf_consortium(
        self, inp: RealEstateExposureInput
    ) -> tuple[float, str]:
        if inp.has_construction_guarantee and inp.guarantor_corp_rwa is not None:
            g_rw    = inp.guarantor_corp_rwa["risk_weight"]
            g_basis = inp.guarantor_corp_rwa.get("basis", "기업 SA")
            g_exp   = inp.guarantor_exposure or 0.0
            pf_exp  = inp.exposure

            if g_exp <= 0 or g_exp >= pf_exp:
                # 전액 보증
                rw = g_rw
                basis = (
                    f"제41조의2 준용 (PF조합사업비, 시공사 연대보증 전액 적용 → "
                    f"시공사 기업 SA RW {g_rw:.0%}; 근거: {g_basis})"
                )
            else:
                # 부분 보증: 연대보증금액 × 시공사 RW + 잔액 × 150%
                remaining = pf_exp - g_exp
                total_rwa = g_exp * g_rw + remaining * PF_CONSORTIUM_DEFAULT_RW
                rw = total_rwa / pf_exp
                basis = (
                    f"제41조의2 준용 (PF조합사업비, 시공사 연대보증 부분 적용: "
                    f"연대보증 {g_exp/1e8:,.1f}억원 × {g_rw:.0%} + "
                    f"잔액 {remaining/1e8:,.1f}억원 × 150% → "
                    f"유효 RW {rw:.1%}; 시공사 근거: {g_basis})"
                )
        elif inp.is_residential_exception:
            rw    = ADC_RESIDENTIAL_RW
            basis = "제41조의2 준용 (PF조합사업비, 주거용 예외 요건 충족 → 100%)"
        else:
            rw    = PF_CONSORTIUM_DEFAULT_RW
            basis = "제41조의2 준용 (PF조합사업비 기본 → 150%)"
        return rw, basis

    # ── 유틸리티 ────────────────────────────────────────────────────────────

    @staticmethod
    def _require_ltv(inp: RealEstateExposureInput) -> float:
        if inp.ltv is None:
            raise ValueError(
                f"{inp.exposure_type.value}: ltv(담보인정비율)가 필요합니다."
            )
        return inp.ltv
