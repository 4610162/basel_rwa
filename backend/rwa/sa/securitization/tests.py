"""
유동화 SEC-SA 계산기 단위 테스트 / 샘플 입출력 검증 스크립트

실행:
    cd backend
    python -m rwa.sa.securitization.tests

테스트 항목:
    1. 정상 케이스 1: A >= K_A  (상위 트랜치)
    2. 정상 케이스 2: D <= K_A  (하위 트랜치, 1,250%)
    3. 정상 케이스 3: A < K_A < D (중위 트랜치, 가중평균)
    4. W 범위 오류 (W > 1)
    5. D <= A 오류
    6. p <= 0 오류
    7. u - l ≈ 0 수치 예외 처리
"""

from __future__ import annotations

import math
import traceback
from typing import Any

from rwa.sa.securitization.calculator import SecuritizationCalculator, SecuritizationInput


def run_test(name: str, inp: SecuritizationInput, expect_error: bool = False) -> dict[str, Any]:
    calc = SecuritizationCalculator()
    print(f"\n{'='*60}")
    print(f"  테스트: {name}")
    print(f"  입력 — exposure={inp.exposure:,.0f}, A={inp.attachment_point}, D={inp.detachment_point}")
    print(f"         K_SA={inp.k_sa}, W={inp.w}, p={inp.p}")
    try:
        result = calc.calc_rwa(inp)
        rw_pct = result["risk_weight"] * 100
        rwa = result["rwa"]
        print(f"  K_A   = {SecuritizationCalculator.calc_k_a(inp.k_sa, inp.w):.6f}")
        print(f"  RW    = {result['risk_weight']:.6f}  ({rw_pct:.2f}%)")
        print(f"  RWA   = {rwa:,.2f}")
        print(f"  basis = {result['basis']}")
        if expect_error:
            print("  ❌  오류가 발생해야 했는데 정상 처리됨!")
            return {"status": "FAIL", "result": result}
        print("  ✅  정상")
        return {"status": "PASS", "result": result}
    except ValueError as e:
        if expect_error:
            print(f"  ✅  예상된 오류 발생: {e}")
            return {"status": "PASS", "error": str(e)}
        else:
            print(f"  ❌  예상치 못한 오류: {e}")
            traceback.print_exc()
            return {"status": "FAIL", "error": str(e)}


def main() -> None:
    results = []

    # ── 케이스 1: A >= K_A (상위 트랜치) ─────────────────────────────
    # K_A = (1-0.05)*0.08 + 0.05*0.5 = 0.076 + 0.025 = 0.101
    # A=0.15 >= K_A=0.101 → 케이스1
    results.append(run_test(
        "케이스1: A(0.15) >= K_A — 상위 트랜치",
        SecuritizationInput(
            exposure=10_000_000_000,
            attachment_point=0.15,
            detachment_point=1.00,
            k_sa=0.08,
            w=0.05,
            p=1.0,
        ),
    ))

    # ── 케이스 2: D <= K_A (하위 트랜치, 1,250%) ─────────────────────
    # K_A = (1-0.05)*0.08 + 0.05*0.5 = 0.101
    # D=0.05 <= K_A=0.101 → 케이스2 → RW=12.5 (1,250%)
    results.append(run_test(
        "케이스2: D(0.05) <= K_A — 하위 트랜치 (1,250%)",
        SecuritizationInput(
            exposure=1_000_000_000,
            attachment_point=0.00,
            detachment_point=0.05,
            k_sa=0.08,
            w=0.05,
            p=1.0,
        ),
    ))

    # ── 케이스 3: A < K_A < D (중위 트랜치) ──────────────────────────
    # K_A = 0.101  →  A=0.05 < 0.101 < D=0.15
    results.append(run_test(
        "케이스3: A(0.05) < K_A < D(0.15) — 중위 트랜치 (가중평균)",
        SecuritizationInput(
            exposure=5_000_000_000,
            attachment_point=0.05,
            detachment_point=0.15,
            k_sa=0.08,
            w=0.05,
            p=1.0,
        ),
    ))

    # ── 재유동화: p=1.5 ───────────────────────────────────────────────
    results.append(run_test(
        "재유동화: p=1.5 (감독승수 변경)",
        SecuritizationInput(
            exposure=2_000_000_000,
            attachment_point=0.05,
            detachment_point=0.15,
            k_sa=0.08,
            w=0.05,
            p=1.5,
        ),
    ))

    # ── 오류: W > 1 ───────────────────────────────────────────────────
    results.append(run_test(
        "오류: W=1.2 (W > 1)",
        SecuritizationInput(
            exposure=1_000_000_000,
            attachment_point=0.05,
            detachment_point=0.15,
            k_sa=0.08,
            w=1.2,
            p=1.0,
        ),
        expect_error=True,
    ))

    # ── 오류: D <= A ──────────────────────────────────────────────────
    results.append(run_test(
        "오류: D(0.05) <= A(0.10) — D는 A보다 커야 함",
        SecuritizationInput(
            exposure=1_000_000_000,
            attachment_point=0.10,
            detachment_point=0.05,
            k_sa=0.08,
            w=0.05,
            p=1.0,
        ),
        expect_error=True,
    ))

    # ── 오류: p <= 0 ──────────────────────────────────────────────────
    results.append(run_test(
        "오류: p=0 (p > 0 이어야 함)",
        SecuritizationInput(
            exposure=1_000_000_000,
            attachment_point=0.05,
            detachment_point=0.15,
            k_sa=0.08,
            w=0.05,
            p=0.0,
        ),
        expect_error=True,
    ))

    # ── 수치 예외: u - l ≈ 0 ──────────────────────────────────────────
    # u=D-K_A, l=max(A-K_A,0)
    # K_A=0.101, A=K_A=0.101, D=K_A+1e-15 → u-l ≈ 1e-15 < 1e-12
    k_a_approx = 0.101
    results.append(run_test(
        "수치 예외: u-l ≈ 0 (A ≈ D ≈ K_A)",
        SecuritizationInput(
            exposure=1_000_000_000,
            attachment_point=k_a_approx,
            detachment_point=k_a_approx + 1e-15,
            k_sa=0.08,
            w=0.05,
            p=1.0,
        ),
    ))

    # ── 요약 ─────────────────────────────────────────────────────────
    passed = sum(1 for r in results if r["status"] == "PASS")
    total = len(results)
    print(f"\n{'='*60}")
    print(f"  결과: {passed}/{total} 통과")
    if passed == total:
        print("  🎉  전체 테스트 통과!")
    else:
        print("  ⚠️  실패한 테스트가 있습니다.")


if __name__ == "__main__":
    main()
