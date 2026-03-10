"""
공통 등급 체계 — 표준신용등급 버킷 및 매핑 테이블

근거: 은행업감독업무시행세칙 [별표 3] 제27조·제28조 (매핑기준)
     및 제29조 가. 주석 (표준신용등급 정의)
"""
from __future__ import annotations
from enum import Enum
from typing import Optional


class GradeBucket(Enum):
    """표준신용등급 버킷 (장기 적격외부신용등급 기준)"""
    AAA_AA_MINUS   = "AAA~AA-"   # AAA, AA+, AA, AA-
    A_PLUS_A_MINUS = "A+~A-"     # A+, A, A-
    BBB            = "BBB+~BBB-" # BBB+, BBB, BBB-
    BB_B_MINUS     = "BB+~B-"    # BB+, BB, BB-, B+, B, B-
    BELOW_B_MINUS  = "B-미만"    # CCC+ 이하
    UNRATED        = "무등급"


# ── 적격외부신용등급 → GradeBucket ────────────────────────────────────────
# 근거: 제29조 가.(1) — 적격외부신용평가기관 신용등급 기준
# ※ 실제 운용 시 27./28.조 기관별 매핑테이블을 별도 적용할 것
_SP_TO_BUCKET: dict[str, GradeBucket] = {
    "AAA":  GradeBucket.AAA_AA_MINUS,
    "AA+":  GradeBucket.AAA_AA_MINUS,
    "AA":   GradeBucket.AAA_AA_MINUS,
    "AA-":  GradeBucket.AAA_AA_MINUS,
    "A+":   GradeBucket.A_PLUS_A_MINUS,
    "A":    GradeBucket.A_PLUS_A_MINUS,
    "A-":   GradeBucket.A_PLUS_A_MINUS,
    "BBB+": GradeBucket.BBB,
    "BBB":  GradeBucket.BBB,
    "BBB-": GradeBucket.BBB,
    "BB+":  GradeBucket.BB_B_MINUS,
    "BB":   GradeBucket.BB_B_MINUS,
    "BB-":  GradeBucket.BB_B_MINUS,
    "B+":   GradeBucket.BB_B_MINUS,
    "B":    GradeBucket.BB_B_MINUS,
    "B-":   GradeBucket.BB_B_MINUS,
    "CCC+": GradeBucket.BELOW_B_MINUS,
    "CCC":  GradeBucket.BELOW_B_MINUS,
    "CCC-": GradeBucket.BELOW_B_MINUS,
    "CC":   GradeBucket.BELOW_B_MINUS,
    "C":    GradeBucket.BELOW_B_MINUS,
    "D":    GradeBucket.BELOW_B_MINUS,
}

# ── OECD 국가신용도등급 → GradeBucket ────────────────────────────────
# 근거: 제29조 가.(2) — OECD 국가신용도등급 기준
_OECD_TO_BUCKET: dict[int, GradeBucket] = {
    0: GradeBucket.AAA_AA_MINUS,   # 0~1 → 0%
    1: GradeBucket.AAA_AA_MINUS,
    2: GradeBucket.A_PLUS_A_MINUS, # 2   → 20%
    3: GradeBucket.BBB,            # 3   → 50%
    4: GradeBucket.BB_B_MINUS,     # 4~6 → 100%
    5: GradeBucket.BB_B_MINUS,
    6: GradeBucket.BB_B_MINUS,
    7: GradeBucket.BELOW_B_MINUS,  # 7   → 150%
}


def resolve_bucket(
    external_credit_rating: Optional[str],
    oecd_grade: Optional[int],
) -> GradeBucket:
    """
    적격외부신용등급 표준신용등급 또는 OECD 국가신용도등급을 GradeBucket으로 변환.
    적격외부신용등급 등급이 있으면 우선 적용하고, 없으면 OECD 등급을 사용한다.
    둘 다 없으면 무등급(UNRATED) 반환.

    근거: 제29조 가. (1)(2) — 두 등급체계 병존 허용

    Args:
        external_credit_rating:   적격외부신용등급 장기 표준신용등급 문자열 (예: "AA-"), None=미입력
        oecd_grade: OECD 국가신용도등급 정수 (0~7), None=미입력

    Raises:
        ValueError: 인식 불가 등급값 입력 시
    """
    if external_credit_rating is not None:
        bucket = _SP_TO_BUCKET.get(external_credit_rating.upper().strip())
        if bucket is None:
            raise ValueError(f"인식할 수 없는 적격외부신용등급 등급: {external_credit_rating!r}")
        return bucket
    if oecd_grade is not None:
        bucket = _OECD_TO_BUCKET.get(oecd_grade)
        if bucket is None:
            raise ValueError(f"OECD 국가신용도등급 범위 초과: {oecd_grade} (0~7 허용)")
        return bucket
    return GradeBucket.UNRATED
