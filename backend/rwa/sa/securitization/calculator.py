"""
유동화 익스포져 표준방법(SEC-SA) RWA 계산기

근거: 바젤III 유동화 프레임워크 — SEC-SA (Securitisation Standard Approach)
       SSFA (Simplified Supervisory Formula Approach) 기반 위험가중치 산출

수식:
    K_A       = (1 - W) × K_SA + W × 0.5
    a         = -1 / (p × K_A)
    u         = D - K_A
    l         = max(A - K_A, 0)
    K_SSFA    = [exp(a×u) - exp(a×l)] / [a × (u - l)]
    RW (케이스1: A ≥ K_A)      = 12.5 × K_SSFA
    RW (케이스2: D ≤ K_A)      = 12.5  (1,250%)
    RW (케이스3: A < K_A < D)  = [(K_A-A)/(D-A)] × 12.5 + [(D-K_A)/(D-A)] × 12.5 × K_SSFA
    RWA = Exposure × RW
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from rwa.common.types import RwaResult


# ── 입력 데이터 클래스 ────────────────────────────────────────────────

@dataclass
class SecuritizationInput:
    """유동화 익스포져 SEC-SA 계산 입력값"""
    exposure: float                     # 익스포져 금액 (원)
    attachment_point: float             # A: 손실개시점 (0 ≤ A < D)
    detachment_point: float             # D: 손실종료점 (D > A)
    k_sa: float                         # 기초자산 풀 SA 자기자본비율 관련 값 (≥ 0)
    w: float                            # 연체·부실 자산 비율 (0 ≤ W ≤ 1)
    p: float = field(default=1.0)       # 감독승수 (> 0; 일반 유동화=1.0, 재유동화=별도)


# ── 메인 산출 클래스 ─────────────────────────────────────────────────

class SecuritizationCalculator:
    """
    유동화 익스포져 표준방법(SEC-SA) 위험가중치·RWA 계산기

    사용법:
        calc = SecuritizationCalculator()
        result = calc.calc_rwa(SecuritizationInput(...))
    """

    # ── 단계별 계산 메서드 (순수 함수, 테스트 가능) ────────────────────

    @staticmethod
    def calc_k_a(k_sa: float, w: float) -> float:
        """
        K_A = (1 - W) × K_SA + W × 0.5

        Args:
            k_sa: 기초자산 풀의 SA 기반 자기자본비율 관련 입력값
            w:    연체·부실 자산 비율 (0 ≤ W ≤ 1)

        Returns:
            K_A — 조정 자기자본비율
        """
        return (1.0 - w) * k_sa + w * 0.5

    @staticmethod
    def calc_k_ssfa(k_a: float, a: float, d: float, p: float) -> float:
        """
        K_SSFA(K_A) 계산

        a_coeff = -1 / (p × K_A)
        u = D - K_A
        l = max(A - K_A, 0)
        K_SSFA = [exp(a_coeff × u) - exp(a_coeff × l)] / [a_coeff × (u - l)]

        수치 예외: |u - l| < 1e-12 이면 exp(a_coeff × u) 반환

        Args:
            k_a: calc_k_a() 결과
            a:   Attachment Point
            d:   Detachment Point
            p:   감독승수 (> 0)

        Returns:
            K_SSFA 값 (0 ~ 1 범위)
        """
        a_coeff = -1.0 / (p * k_a)
        u = d - k_a
        l = max(a - k_a, 0.0)

        if abs(u - l) < 1e-12:
            return math.exp(a_coeff * u)

        return (math.exp(a_coeff * u) - math.exp(a_coeff * l)) / (a_coeff * (u - l))

    def calc_risk_weight(
        self,
        k_a: float,
        a: float,
        d: float,
        p: float,
    ) -> tuple[float, str]:
        """
        위험가중치(RW) 계산

        케이스 1: A ≥ K_A          → RW = 12.5 × K_SSFA(K_A)
        케이스 2: D ≤ K_A          → RW = 12.5  (= 1,250%)
        케이스 3: A < K_A < D      → RW = [(K_A-A)/(D-A)] × 12.5
                                          + [(D-K_A)/(D-A)] × 12.5 × K_SSFA(K_A)

        Returns:
            (risk_weight, case_label) 튜플
        """
        if a >= k_a:
            k_ssfa = self.calc_k_ssfa(k_a, a, d, p)
            rw = 12.5 * k_ssfa
            case_label = f"케이스1: A({a:.4f}) ≥ K_A({k_a:.4f}) — 상위 트랜치"
            return rw, case_label

        if d <= k_a:
            case_label = f"케이스2: D({d:.4f}) ≤ K_A({k_a:.4f}) — 하위 트랜치 (1,250%)"
            return 12.5, case_label

        # A < K_A < D
        k_ssfa = self.calc_k_ssfa(k_a, a, d, p)
        w_lower = (k_a - a) / (d - a)
        w_upper = (d - k_a) / (d - a)
        rw = w_lower * 12.5 + w_upper * 12.5 * k_ssfa
        case_label = f"케이스3: A({a:.4f}) < K_A({k_a:.4f}) < D({d:.4f}) — 중위 트랜치"
        return rw, case_label

    # ── 입력 유효성 검증 ───────────────────────────────────────────────

    @staticmethod
    def validate(inp: SecuritizationInput) -> None:
        """
        입력값 유효성 검증. 오류 시 ValueError 발생.

        검증 항목:
            - exposure >= 0
            - 0 <= A < D
            - K_SA >= 0
            - 0 <= W <= 1
            - p > 0
        """
        if inp.exposure < 0:
            raise ValueError("익스포져 금액은 0 이상이어야 합니다.")
        if inp.attachment_point < 0:
            raise ValueError("Attachment Point(A)는 0 이상이어야 합니다.")
        if inp.detachment_point <= inp.attachment_point:
            raise ValueError(
                f"Detachment Point(D={inp.detachment_point:.4f})는 "
                f"Attachment Point(A={inp.attachment_point:.4f})보다 커야 합니다."
            )
        if inp.k_sa < 0:
            raise ValueError("K_SA는 0 이상이어야 합니다.")
        if not (0.0 <= inp.w <= 1.0):
            raise ValueError(
                f"W는 0과 1 사이 값이어야 합니다. (입력값: {inp.w})"
            )
        if inp.p <= 0:
            raise ValueError(
                f"p는 0보다 커야 합니다. (입력값: {inp.p})"
            )

    # ── 통합 진입점 ────────────────────────────────────────────────────

    def calc_rwa(self, inp: SecuritizationInput) -> RwaResult:
        """
        SEC-SA 방식으로 유동화 익스포져 RWA를 산출하는 통합 진입점.

        Args:
            inp: SecuritizationInput 데이터클래스

        Returns:
            RwaResult — entity_type, risk_weight, rwa, basis 포함

        Raises:
            ValueError: 입력값 오류 또는 K_A ≤ 0, 계산 결과 비정상
        """
        self.validate(inp)

        k_a = self.calc_k_a(inp.k_sa, inp.w)

        if k_a <= 0:
            raise ValueError(
                f"K_A = {k_a:.6f} (≤ 0) — 계산 불가.\n"
                "K_A = (1 - W) × K_SA + W × 0.5 가 0보다 커야 합니다.\n"
                "K_SA와 W 값을 다시 확인하세요."
            )

        rw, case_label = self.calc_risk_weight(
            k_a,
            inp.attachment_point,
            inp.detachment_point,
            inp.p,
        )

        if not math.isfinite(rw):
            raise ValueError(
                f"계산 결과가 유효하지 않습니다 (RW={rw}). 입력값을 다시 확인하세요."
            )

        basis = (
            f"유동화 표준방법(SEC-SA) | "
            f"K_A = (1-{inp.w:.4f})×{inp.k_sa:.4f} + {inp.w:.4f}×0.5 = {k_a:.4f} | "
            f"{case_label}"
        )

        return RwaResult(
            entity_type="sec_sa",
            risk_weight=rw,
            rwa=inp.exposure * rw,
            basis=basis,
        )
