"""
SA 주식(Equity) 익스포져 RWA 계산기

근거: 은행업감독업무시행세칙 [별표 3] 제2장 제4절 (제38조의3)

mermaid 다이어그램 노드:
    SA_EQ  주식 익스포져

위험가중치 체계 (제38조의3):
    바.  일반 주식            : 250%  (비상장 장기보유·출자전환 포함)
    바.  투기적 비상장 주식    : 400%  (VC·자본이득 목적)
    사.  정부보조 프로그램 주식 : 100%  (자기자본 10% 한도)
    아.  후순위채권·기타 자본   : 150%
    자.  비금융자회사 대규모 출자: 1,250% (15%/60% 초과분)
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from rwa.common.types import RwaResult


# ── 상수 ─────────────────────────────────────────────────────────────────

RW_GENERAL: float = 2.50          # 제38조의3 바. 일반 주식 (250%)
RW_SPECULATIVE: float = 4.00      # 제38조의3 바. 투기적 비상장 (400%)
RW_GOVT_SPONSORED: float = 1.00   # 제38조의3 사. 정부보조 프로그램 (100%)
RW_SUBORDINATED: float = 1.50     # 제38조의3 아. 후순위채권·기타 자본 (150%)
RW_LARGE_EQUITY: float = 12.50    # 제38조의3 자. 비금융자회사 대규모 출자 (1,250%)

GOVT_CAP_RATIO: float = 0.10      # 제38조의3 사. 정부보조 한도: 자기자본의 10%
LARGE_INDIV_THRESHOLD: float = 0.15   # 제38조의3 자.(1) 개별 초과 기준: 15%
LARGE_AGGREGATE_THRESHOLD: float = 0.60  # 제38조의3 자.(2) 합산 초과 기준: 60%


# ── 열거형 ────────────────────────────────────────────────────────────────

class EquityType(Enum):
    """
    주식 익스포져 세부 유형 (제38조의3)

    GENERAL_LISTED          : 상장 주식 → RW 250% [바.]
    UNLISTED_LONG_TERM      : 비상장 장기보유·출자전환 주식 → RW 250% [바.]
    UNLISTED_SPECULATIVE    : 투기적 비상장 주식(VC·자본이득) → RW 400% [바.]
    GOVT_SPONSORED          : 정부보조 프로그램 주식 → RW 100% (한도 내) [사.]
    SUBORDINATED_DEBT       : 후순위채권 → RW 150% [아.]
    OTHER_CAPITAL_INSTRUMENT: 주식 이외 기타 자본조달수단 → RW 150% [아.]
    NON_FINANCIAL_LARGE     : 비금융자회사 대규모 출자 초과분 → RW 1,250% [자.]
    """
    GENERAL_LISTED           = "general_listed"
    UNLISTED_LONG_TERM       = "unlisted_long_term"
    UNLISTED_SPECULATIVE     = "unlisted_speculative"
    GOVT_SPONSORED           = "govt_sponsored"
    SUBORDINATED_DEBT        = "subordinated_debt"
    OTHER_CAPITAL_INSTRUMENT = "other_capital_instrument"
    NON_FINANCIAL_LARGE      = "non_financial_large"


# ── 기본 위험가중치 매핑 ───────────────────────────────────────────────────

_BASE_RW: dict[EquityType, float] = {
    EquityType.GENERAL_LISTED:           RW_GENERAL,
    EquityType.UNLISTED_LONG_TERM:       RW_GENERAL,
    EquityType.UNLISTED_SPECULATIVE:     RW_SPECULATIVE,
    EquityType.GOVT_SPONSORED:           RW_GOVT_SPONSORED,
    EquityType.SUBORDINATED_DEBT:        RW_SUBORDINATED,
    EquityType.OTHER_CAPITAL_INSTRUMENT: RW_SUBORDINATED,
    EquityType.NON_FINANCIAL_LARGE:      RW_LARGE_EQUITY,
}

_BASIS_TEXT: dict[EquityType, str] = {
    EquityType.GENERAL_LISTED:           "제38조의3 바. (상장주식 250%)",
    EquityType.UNLISTED_LONG_TERM:       "제38조의3 바. (비상장 장기보유·출자전환 250%)",
    EquityType.UNLISTED_SPECULATIVE:     "제38조의3 바. (투기적 비상장 400%)",
    EquityType.GOVT_SPONSORED:           "제38조의3 사. (정부보조 프로그램 100%)",
    EquityType.SUBORDINATED_DEBT:        "제38조의3 아. (후순위채권 150%)",
    EquityType.OTHER_CAPITAL_INSTRUMENT: "제38조의3 아. (기타 자본조달수단 150%)",
    EquityType.NON_FINANCIAL_LARGE:      "제38조의3 자. (비금융자회사 대규모 출자 1,250%)",
}


# ── 입력 데이터클래스 ─────────────────────────────────────────────────────

@dataclass
class EquityInput:
    """
    주식 익스포져 RWA 산출 입력값

    Parameters
    ----------
    exposure : float
        익스포져 금액 (원화, 단위: 원)
    equity_type : EquityType
        주식 유형. 기본값은 보수적인 UNLISTED_SPECULATIVE (400%)
    own_funds : float, optional
        자기자본 금액 (공제항목 공제 후). 정부보조(사.) 및 대규모출자(자.) 한도 계산에 필요
    govt_sponsored_existing : float, optional
        이미 100% 적용 중인 정부보조 주식 누적금액 (한도 선점분). 사. 한도 계산에 사용
    non_fin_indiv_total : float, optional
        동일 비금융자회사에 대한 총 출자금액 (자.(1) 기준)
    non_fin_aggregate_total : float, optional
        비금융자회사 전체에 대한 출자금액 합계 (자.(2) 기준)
    entity_name : str, optional
        기관명 (보고·감사용)
    """
    exposure: float
    equity_type: EquityType = EquityType.UNLISTED_SPECULATIVE  # 기본값: 가장 보수적
    own_funds: Optional[float] = None
    govt_sponsored_existing: float = 0.0
    non_fin_indiv_total: Optional[float] = None
    non_fin_aggregate_total: Optional[float] = None
    entity_name: Optional[str] = None


# ── 계산기 ────────────────────────────────────────────────────────────────

class EquityCalculator:
    """
    SA 주식 익스포져 RWA 계산기
    근거: 제38조의3 (주식 익스포져)
    """

    def calc_rw_equity(self, inp: EquityInput) -> float:
        """
        [SA_EQ] 주식 익스포져 위험가중치 반환
        근거: 제38조의3 바.~자.

        Returns
        -------
        float
            위험가중치 (예: 2.50 = 250%)
        """
        if inp.equity_type == EquityType.GOVT_SPONSORED:
            return self._rw_govt_sponsored(inp)
        return _BASE_RW[inp.equity_type]

    def calc_rwa(self, inp: EquityInput) -> RwaResult:
        """
        [SA_EQ] 주식 익스포져 RWA 산출

        정부보조(사.) 유형은 자기자본 10% 한도를 적용하여
        한도 초과분은 일반 RW(250%)로 분리 처리한 후 합산한다.

        대규모 출자(자.)는 호출 전 이미 초과금액만을 inp.exposure에
        담아 전달하는 것을 전제로 한다 (호출자가 전체/초과 분리 책임).

        Returns
        -------
        RwaResult
            entity_type, risk_weight, rwa, basis
        """
        if inp.equity_type == EquityType.GOVT_SPONSORED:
            return self._calc_rwa_govt_sponsored(inp)

        rw = _BASE_RW[inp.equity_type]
        return RwaResult(
            entity_type=inp.equity_type.value,
            risk_weight=rw,
            rwa=inp.exposure * rw,
            basis=_BASIS_TEXT[inp.equity_type],
        )

    # ── 내부 헬퍼 ─────────────────────────────────────────────────────────

    def _rw_govt_sponsored(self, inp: EquityInput) -> float:
        """제38조의3 사.: 정부보조 프로그램 주식 위험가중치 결정"""
        if inp.own_funds is None:
            # own_funds 미제공 시 보수적으로 일반 RW 적용
            return RW_GENERAL
        cap = inp.own_funds * GOVT_CAP_RATIO
        remaining_cap = max(cap - inp.govt_sponsored_existing, 0.0)
        if remaining_cap <= 0:
            return RW_GENERAL  # 한도 소진 → 일반 250%
        # 한도 내 비율 (0.0~1.0): 혼합 가중치가 필요하면 calc_rwa 사용
        return RW_GOVT_SPONSORED

    def _calc_rwa_govt_sponsored(self, inp: EquityInput) -> RwaResult:
        """
        제38조의3 사.: 정부보조 한도 내/초과분 분리 산출

        한도 내   → 100%
        한도 초과분 → 250% (일반 주식 RW)
        """
        if inp.own_funds is None:
            # own_funds 미제공 → 전액 250% (보수적)
            return RwaResult(
                entity_type=inp.equity_type.value,
                risk_weight=RW_GENERAL,
                rwa=inp.exposure * RW_GENERAL,
                basis="제38조의3 사. (own_funds 미제공 → 250% 보수적 적용)",
            )

        cap = inp.own_funds * GOVT_CAP_RATIO
        remaining_cap = max(cap - inp.govt_sponsored_existing, 0.0)
        within_cap = min(inp.exposure, remaining_cap)
        over_cap = max(inp.exposure - remaining_cap, 0.0)

        rwa_within = within_cap * RW_GOVT_SPONSORED
        rwa_over = over_cap * RW_GENERAL
        total_rwa = rwa_within + rwa_over

        # 보고용 실효 위험가중치
        effective_rw = total_rwa / inp.exposure if inp.exposure > 0 else RW_GENERAL

        basis = "제38조의3 사. (정부보조 100%)"
        if over_cap > 0:
            basis += f" / 한도초과 {over_cap:,.0f}원 → 250% (제38조의3 바.)"

        return RwaResult(
            entity_type=inp.equity_type.value,
            risk_weight=round(effective_rw, 6),
            rwa=total_rwa,
            basis=basis,
        )

    # ── 대규모 출자 유틸리티 ───────────────────────────────────────────────

    @staticmethod
    def split_non_financial_large(
        indiv_exposure: float,
        non_fin_indiv_total: float,
        non_fin_aggregate_total: float,
        own_funds: float,
    ) -> tuple[float, float]:
        """
        제38조의3 자.: 비금융자회사 대규모 출자 초과금액 산출

        Parameters
        ----------
        indiv_exposure : float
            이번 건 출자금액
        non_fin_indiv_total : float
            동일 비금융자회사에 대한 총 출자금액 (이번 건 포함)
        non_fin_aggregate_total : float
            비금융자회사 전체 출자금액 합계 (이번 건 포함)
        own_funds : float
            자기자본 (공제항목 공제 후)

        Returns
        -------
        (normal_exposure, large_exposure) : tuple[float, float]
            normal_exposure : 일반 RW(250%) 적용 금액
            large_exposure  : 1,250% 적용 초과 금액
        """
        indiv_limit = own_funds * LARGE_INDIV_THRESHOLD
        agg_limit = own_funds * LARGE_AGGREGATE_THRESHOLD

        # 자.(1): 개별 초과분
        indiv_excess = max(non_fin_indiv_total - indiv_limit, 0.0)
        # 자.(2): 합산 초과분
        agg_excess = max(non_fin_aggregate_total - agg_limit, 0.0)

        large_exposure = min(indiv_exposure, max(indiv_excess, agg_excess))
        large_exposure = max(large_exposure, 0.0)
        normal_exposure = indiv_exposure - large_exposure

        return normal_exposure, large_exposure
