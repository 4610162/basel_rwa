"""
SA 집합투자증권(CIU) 익스포져 RWA 계산기 [스텁 구현]

근거: 은행업감독업무시행세칙 [별표 3] 제2장 제3절 제44조

mermaid 다이어그램 노드:
    SA_CIU_LTA   기초자산접근법 (Look-Through Approach)
    SA_CIU_MBA   약정서기반접근법 (Mandate-Based Approach)
    SA_CIU_FBA   자본차감법 (Fall-Back Approach)

구현 상태:
    LTA / MBA : 스텁(Stub) — 기초자산별 위험가중치 등록 로직은 미구현.
                사용자가 직접 가중평균 위험가중치를 입력하거나,
                제3자 산출 위험가중치를 제공하면 RWA를 계산해준다.
                실제 기초자산 데이터 등록 시 이 인터페이스를 확장한다.

    FBA       : 완전 구현 — 1,250% 위험가중치 적용.

방법별 적용 조건 [제44조]:
    LTA: 기초자산 정보를 적시에 상세하게 입수 가능하고 독립 제3자 검증 가능 시 [가.]
    MBA: LTA 적용 불가 시, 투자약정서 등 공시 정보 활용 [나.]
    FBA: LTA·MBA 모두 불가 시 의무 적용 [다.]
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from rwa.common.types import RwaResult
from .constants import (
    FBA_RW,
    CIU_LEVERAGE_RW_CAP,
    THIRD_PARTY_MULTIPLIER,
)


# ── 열거형 ───────────────────────────────────────────────────────────────────

class CIUApproach(Enum):
    """
    집합투자증권(CIU) 위험가중자산 산출 방법 [제44조 가.~다.]

    LTA : 기초자산접근법 (Look-Through Approach)      [제44조 가.]
    MBA : 약정서기반접근법 (Mandate-Based Approach)   [제44조 나.]
    FBA : 자본차감법 (Fall-Back Approach)             [제44조 다.]
    """
    LTA = "lta"
    MBA = "mba"
    FBA = "fba"


# ── 입력 데이터클래스 ─────────────────────────────────────────────────────────

@dataclass
class CIUInput:
    """
    집합투자증권(CIU) 익스포져 RWA 산출 입력값

    Parameters
    ----------
    exposure : float
        은행 보유 CIU 익스포져 금액 (지분증권·수익증권·미실행 출자약정 환산액 포함)
    approach : CIUApproach
        적용 방법 (LTA / MBA / FBA)

    [LTA / MBA 공통 — 스텁 파라미터]
    weighted_avg_rw : float, optional
        사용자가 직접 산출·입력한 기초자산 가중평균 위험가중치.
        LTA/MBA 스텁 모드에서 이 값을 그대로 사용한다.
        예: 0.75 = 75%
    is_third_party_rw : bool
        True이면 weighted_avg_rw가 제3자 산출 위험가중치임을 의미.
        제44조 가.(4)에 따라 1.2 승수를 자동 적용한다.
        기본값 False.

    [레버리지 조정 — 제44조 사.]
    leverage_ratio : float
        집합투자증권의 레버리지 배율 (총자산/총자본).
        1.0 = 레버리지 없음 (기본값).
        1.0 초과 시 weighted_avg_rw × leverage_ratio로 조정 후 1,250% 상한 적용.

    fund_name : str, optional
        펀드명 (참고·보고용)
    """
    exposure: float
    approach: CIUApproach = CIUApproach.FBA     # 정보 없으면 보수적으로 FBA
    weighted_avg_rw: Optional[float] = None
    is_third_party_rw: bool = False
    leverage_ratio: float = 1.0
    fund_name: Optional[str] = None


# ── 메인 산출 클래스 ──────────────────────────────────────────────────────────

class CIUCalculator:
    """
    SA 집합투자증권(CIU) 익스포져 위험가중치·RWA 계산기

    LTA / MBA는 스텁 인터페이스로 구현되어 있으며,
    사용자가 가중평균 위험가중치(weighted_avg_rw)를 제공해야 산출이 완료된다.
    기초자산별 자동 탐색·등록 로직은 향후 구현 예정.

    FBA는 완전히 구현되어 있으며, 1,250% 위험가중치를 적용한다.
    """

    # ── 공개 인터페이스 ──────────────────────────────────────────────────────

    def calc_rw_lta(
        self,
        weighted_avg_rw: Optional[float] = None,
        is_third_party_rw: bool = False,
        leverage_ratio: float = 1.0,
    ) -> float:
        """
        [SA_CIU_LTA] 기초자산접근법(LTA) 위험가중치 반환 — 스텁

        근거: 제44조 가. (기초자산접근법)

        현재 구현 상태 (스텁):
            - 기초자산 정보를 직접 조회·등록하는 로직은 미구현.
            - weighted_avg_rw를 사용자가 직접 입력해야 한다.
            - is_third_party_rw=True이면 1.2 승수 적용 [가.(4)].
            - leverage_ratio > 1이면 레버리지 조정 후 1,250% 상한 적용 [사.].

        Parameters
        ----------
        weighted_avg_rw : float, optional
            사용자 입력 가중평균 위험가중치. None이면 FBA(1,250%) 반환.
        is_third_party_rw : bool
            제3자 산출 위험가중치 여부 → True이면 × 1.2 [제44조 가.(4)]
        leverage_ratio : float
            레버리지 배율 (총자산/총자본). 기본값 1.0.

        Returns
        -------
        float
            위험가중치

        Warns
        -----
        UserWarning
            weighted_avg_rw 미제공 시 FBA로 대체됨을 경고
        """
        return self._stub_rw(
            approach_name="LTA",
            weighted_avg_rw=weighted_avg_rw,
            is_third_party_rw=is_third_party_rw,
            leverage_ratio=leverage_ratio,
        )

    def calc_rw_mba(
        self,
        weighted_avg_rw: Optional[float] = None,
        is_third_party_rw: bool = False,
        leverage_ratio: float = 1.0,
    ) -> float:
        """
        [SA_CIU_MBA] 약정서기반접근법(MBA) 위험가중치 반환 — 스텁

        근거: 제44조 나. (약정서기반접근법)

        현재 구현 상태 (스텁):
            - 약정서/규정/공시 기반 기초자산 위험가중치 자동 산출 로직 미구현.
            - weighted_avg_rw를 사용자가 직접 입력해야 한다.
            - is_third_party_rw=True이면 1.2 승수 적용 [가.(4) 준용].
            - leverage_ratio > 1이면 레버리지 조정 후 1,250% 상한 적용 [사.].

        Parameters
        ----------
        weighted_avg_rw : float, optional
            사용자 입력 가중평균 위험가중치. None이면 FBA(1,250%) 반환.
        is_third_party_rw : bool
            제3자 산출 위험가중치 여부
        leverage_ratio : float
            레버리지 배율 (총자산/총자본). 기본값 1.0.

        Returns
        -------
        float
            위험가중치

        Warns
        -----
        UserWarning
            weighted_avg_rw 미제공 시 FBA로 대체됨을 경고
        """
        return self._stub_rw(
            approach_name="MBA",
            weighted_avg_rw=weighted_avg_rw,
            is_third_party_rw=is_third_party_rw,
            leverage_ratio=leverage_ratio,
        )

    def calc_rw_fba(self) -> float:
        """
        [SA_CIU_FBA] 자본차감법(FBA) 위험가중치 반환 — 완전 구현

        근거: 제44조 다. (자본차감법)

        LTA·MBA 적용이 모두 불가능한 경우 의무 적용.
        집합투자증권 익스포져에 1,250%의 위험가중치를 적용한다.

        Returns
        -------
        float
            1,250% (= 12.50)
        """
        return FBA_RW

    def calc_rwa(self, inp: CIUInput) -> RwaResult:
        """
        CIUInput을 받아 RW와 RWA를 산출하는 통합 진입점.

        Parameters
        ----------
        inp : CIUInput

        Returns
        -------
        RwaResult
            entity_type, risk_weight, rwa, basis 포함
        """
        if inp.approach == CIUApproach.FBA:
            rw, basis = self._handle_fba(inp)
        elif inp.approach == CIUApproach.LTA:
            rw, basis = self._handle_lta(inp)
        elif inp.approach == CIUApproach.MBA:
            rw, basis = self._handle_mba(inp)
        else:
            raise ValueError(f"처리되지 않은 CIUApproach: {inp.approach}")

        return RwaResult(
            entity_type=f"ciu_{inp.approach.value}",
            risk_weight=rw,
            rwa=inp.exposure * rw,
            basis=basis,
        )

    # ── 스텁 공통 로직 ───────────────────────────────────────────────────────

    def _stub_rw(
        self,
        approach_name: str,
        weighted_avg_rw: Optional[float],
        is_third_party_rw: bool,
        leverage_ratio: float,
    ) -> float:
        """LTA / MBA 공통 스텁 위험가중치 산출"""
        if weighted_avg_rw is None:
            warnings.warn(
                f"[CIU {approach_name} 스텁] 기초자산 정보 필요: weighted_avg_rw가 "
                "제공되지 않아 자본차감법(FBA) 위험가중치 1,250%를 보수적으로 반환합니다.",
                UserWarning,
                stacklevel=3,
            )
            return FBA_RW

        rw = weighted_avg_rw

        # 제44조 가.(4): 제3자 산출 위험가중치 → 1.2 승수
        if is_third_party_rw:
            rw = rw * THIRD_PARTY_MULTIPLIER

        # 제44조 사.: 레버리지 조정 및 1,250% 상한
        if leverage_ratio != 1.0:
            rw = rw * leverage_ratio

        return min(rw, CIU_LEVERAGE_RW_CAP)

    # ── 내부 핸들러 ──────────────────────────────────────────────────────────

    def _handle_fba(self, inp: CIUInput) -> tuple[float, str]:
        rw = self.calc_rw_fba()
        basis = "제44조 다. (자본차감법 FBA → 1,250%)"
        return rw, basis

    def _handle_lta(self, inp: CIUInput) -> tuple[float, str]:
        rw = self.calc_rw_lta(
            weighted_avg_rw=inp.weighted_avg_rw,
            is_third_party_rw=inp.is_third_party_rw,
            leverage_ratio=inp.leverage_ratio,
        )
        if inp.weighted_avg_rw is None:
            basis = (
                "제44조 가. (기초자산접근법 LTA — 스텁: 기초자산 정보 필요, "
                "weighted_avg_rw 미제공 → FBA 1,250% 보수적 적용)"
            )
        else:
            parts = [f"제44조 가. (기초자산접근법 LTA — 스텁: 입력 가중평균 RW {inp.weighted_avg_rw:.0%}"]
            if inp.is_third_party_rw:
                parts.append(f"× 1.2 승수 [가.(4)]")
            if inp.leverage_ratio != 1.0:
                parts.append(f"× 레버리지 {inp.leverage_ratio:.2f}배 [사.]")
            parts.append(f"→ 최종 RW {rw:.0%})")
            basis = " ".join(parts)
        return rw, basis

    def _handle_mba(self, inp: CIUInput) -> tuple[float, str]:
        rw = self.calc_rw_mba(
            weighted_avg_rw=inp.weighted_avg_rw,
            is_third_party_rw=inp.is_third_party_rw,
            leverage_ratio=inp.leverage_ratio,
        )
        if inp.weighted_avg_rw is None:
            basis = (
                "제44조 나. (약정서기반접근법 MBA — 스텁: 기초자산 정보 필요, "
                "weighted_avg_rw 미제공 → FBA 1,250% 보수적 적용)"
            )
        else:
            parts = [f"제44조 나. (약정서기반접근법 MBA — 스텁: 입력 가중평균 RW {inp.weighted_avg_rw:.0%}"]
            if inp.is_third_party_rw:
                parts.append(f"× 1.2 승수 [가.(4) 준용]")
            if inp.leverage_ratio != 1.0:
                parts.append(f"× 레버리지 {inp.leverage_ratio:.2f}배 [사.]")
            parts.append(f"→ 최종 RW {rw:.0%})")
            basis = " ".join(parts)
        return rw, basis
