"""
SA 기업(Corporate) 익스포져 — 위험가중치 테이블 상수

근거: 은행업감독업무시행세칙 [별표 3] 제2장 제3절 (제37조, 제38조, 제38조의2)
"""
from __future__ import annotations

from enum import Enum
from typing import Optional


# ── 기업 익스포져 전용 표준신용등급 버킷 ───────────────────────────────────
# 은행 버킷(BB+~B-)과 달리 기업 익스포져는 BB- 기준으로 투기등급을 분리한다.

class CorpGradeBucket(Enum):
    """
    기업 익스포져 표준신용등급 버킷
    근거: 제37조 가. / 제38조의2. 다. 위험가중치 테이블
    ※ 은행 GradeBucket(BB+~B-)과 달리 BB+~BB- / BB-미만으로 분리됨
    """
    AAA_AA_MINUS   = "AAA~AA-"    # AAA, AA+, AA, AA-
    A_PLUS_A_MINUS = "A+~A-"      # A+, A, A-
    BBB            = "BBB+~BBB-"  # BBB+, BBB, BBB-
    BB_BB_MINUS    = "BB+~BB-"    # BB+, BB, BB-  (B+ 이하 미포함)
    BELOW_BB_MINUS = "BB-미만"    # B+, B, B-, CCC+ 이하
    UNRATED        = "무등급"


# ── 적격외부신용등급 → CorpGradeBucket ──────────────────────────────────────
_SP_TO_CORP_BUCKET: dict[str, CorpGradeBucket] = {
    "AAA":  CorpGradeBucket.AAA_AA_MINUS,
    "AA+":  CorpGradeBucket.AAA_AA_MINUS,
    "AA":   CorpGradeBucket.AAA_AA_MINUS,
    "AA-":  CorpGradeBucket.AAA_AA_MINUS,
    "A+":   CorpGradeBucket.A_PLUS_A_MINUS,
    "A":    CorpGradeBucket.A_PLUS_A_MINUS,
    "A-":   CorpGradeBucket.A_PLUS_A_MINUS,
    "BBB+": CorpGradeBucket.BBB,
    "BBB":  CorpGradeBucket.BBB,
    "BBB-": CorpGradeBucket.BBB,
    "BB+":  CorpGradeBucket.BB_BB_MINUS,
    "BB":   CorpGradeBucket.BB_BB_MINUS,
    "BB-":  CorpGradeBucket.BB_BB_MINUS,
    "B+":   CorpGradeBucket.BELOW_BB_MINUS,   # ← 은행 버킷(BB+~B-)과 구별
    "B":    CorpGradeBucket.BELOW_BB_MINUS,
    "B-":   CorpGradeBucket.BELOW_BB_MINUS,
    "CCC+": CorpGradeBucket.BELOW_BB_MINUS,
    "CCC":  CorpGradeBucket.BELOW_BB_MINUS,
    "CCC-": CorpGradeBucket.BELOW_BB_MINUS,
    "CC":   CorpGradeBucket.BELOW_BB_MINUS,
    "C":    CorpGradeBucket.BELOW_BB_MINUS,
    "D":    CorpGradeBucket.BELOW_BB_MINUS,
}


def resolve_corp_bucket(external_credit_rating: Optional[str]) -> CorpGradeBucket:
    """적격외부신용등급 → CorpGradeBucket 변환. None이면 UNRATED 반환."""
    if external_credit_rating is None:
        return CorpGradeBucket.UNRATED
    bucket = _SP_TO_CORP_BUCKET.get(external_credit_rating.upper().strip())
    if bucket is None:
        raise ValueError(f"인식할 수 없는 적격외부신용등급: {external_credit_rating!r}")
    return bucket


# ── 제37조 가. — 일반기업 장기등급 위험가중치 ────────────────────────────────
# ※ 무등급(UNRATED) 기본값 100%; 중소기업 무등급 85%는 calc_rw_corp()에서 처리
CORP_LONG_RW: dict[CorpGradeBucket, float] = {
    CorpGradeBucket.AAA_AA_MINUS:   0.20,   # 20%
    CorpGradeBucket.A_PLUS_A_MINUS: 0.50,   # 50%
    CorpGradeBucket.BBB:            0.75,   # 75%
    CorpGradeBucket.BB_BB_MINUS:    1.00,   # 100%
    CorpGradeBucket.BELOW_BB_MINUS: 1.50,   # 150%
    CorpGradeBucket.UNRATED:        1.00,   # 100% (무등급 기본; SME는 85%)
}

# ── 제38조 가. — 기업 단기 신용등급 위험가중치 ───────────────────────────────
# 원만기 3개월 이내의 단기 익스포져에 부여된 신용등급 기반 (기업어음 등)
CORP_SHORT_RW: dict[str, float] = {
    "A-1":   0.20,   # 20%
    "A-2":   0.50,   # 50%
    "A-3":   1.00,   # 100%
    "OTHER": 1.50,   # 150% — non-prime, B/C 등급 등 투기등급 포함
}

# 제38조 나. — 150% 단기등급 채무자의 무등급 장기·단기 익스포져 하한
CORP_SHORT_150_UNRATED_RW: float = 1.50    # 150%

# 제38조 다. — A-2(50%) 단기등급 채무자의 무등급 단기 익스포져 최소 위험가중치
CORP_SHORT_50_UNRATED_MIN_RW: float = 1.00  # 100% 이상

# ── 제38조의2. 다. — 특수금융(PF·OF·CF) 외부등급 위험가중치 ─────────────────
# 기업 익스포져와 동일 테이블, 무등급 행 제외 (무등급은 라.에서 처리)
SL_RATED_RW: dict[CorpGradeBucket, float] = {
    CorpGradeBucket.AAA_AA_MINUS:   0.20,   # 20%
    CorpGradeBucket.A_PLUS_A_MINUS: 0.50,   # 50%
    CorpGradeBucket.BBB:            0.75,   # 75%
    CorpGradeBucket.BB_BB_MINUS:    1.00,   # 100%
    CorpGradeBucket.BELOW_BB_MINUS: 1.50,   # 150%
}

# ── 제38조의2. 라. — 특수금융 무등급 위험가중치 ──────────────────────────────
# PF: 운영전 단계 130% / 운영 단계 100% / 우량 운영 단계 80%(5개 요건 충족 시)
# OF, CF: 100%
PF_PRE_OP_UNRATED_RW:          float = 1.30   # 130% — 운영전(pre-operational)
PF_OP_UNRATED_RW:              float = 1.00   # 100% — 운영(operational)
PF_OP_HIGH_QUALITY_UNRATED_RW: float = 0.80   # 80%  — 우량 운영(5개 요건 모두 충족)
OF_CF_UNRATED_RW:              float = 1.00   # 100%

# ── 특수금융 슬롯팅 기준 — IPRE / HVCRE ──────────────────────────────────
# 근거: 제120조 다. 표준등급분류기준(Slotting Criteria) 위험가중치
# SA에서 IPRE/HVCRE는 제38조의2 나.에 따라 제41조의2(부동산개발금융)를 참조하나,
# 슬롯팅 기준은 IRB 적용 은행 및 실무상 SA 산출 시 공통으로 인용된다.
#
# | 등급(Slotting)  | 우량(Strong) | 양호(Good) | 보통(Satisfactory) | 취약(Weak) | 부도(Default) |
# |----------------|------------|----------|-----------------|---------|------------|
# | PF/OF/CF/IPRE  | 70%        | 90%      | 115%            | 250%    | 0%         |
# | HVCRE          | 95%        | 120%     | 140%            | 250%    | 0%         |
#
# 우량(Strong)·양호(Good) 중 잔존만기 2년 6개월 이내 또는 해당 등급 기준보다
# 더 안전함을 입증한 경우 우대 위험가중치 적용 가능:
#   IPRE: 우량 50%, 양호 70%
#   HVCRE: 우량 70%, 양호 95%
#
# 형식: { 슬롯팅등급: (기본 RW, 우대 RW) }

IPRE_SLOTTING_RW: dict[str, tuple[float, float]] = {
    "STRONG":       (0.70, 0.50),   # 우량: 70% (잔존만기 단기·안전 입증 시 50%)
    "GOOD":         (0.90, 0.70),   # 양호: 90% (잔존만기 단기·안전 입증 시 70%)
    "SATISFACTORY": (1.15, 1.15),   # 보통: 115%
    "WEAK":         (2.50, 2.50),   # 취약: 250%
    "DEFAULT":      (0.00, 0.00),   # 부도: 0% (EL 산출용; 자본요구액 별도)
}

HVCRE_SLOTTING_RW: dict[str, tuple[float, float]] = {
    "STRONG":       (0.95, 0.70),   # 우량: 95% (잔존만기 단기·안전 입증 시 70%)
    "GOOD":         (1.20, 0.95),   # 양호: 120% (잔존만기 단기·안전 입증 시 95%)
    "SATISFACTORY": (1.40, 1.40),   # 보통: 140%
    "WEAK":         (2.50, 2.50),   # 취약: 250%
    "DEFAULT":      (0.00, 0.00),   # 부도: 0%
}

# ── 제37조 다. SME 기준 (연간 매출액 / 총자산) ───────────────────────────────
SME_REVENUE_THRESHOLD_EOK: float = 700.0    # 연간 매출액 700억원 이하
SME_ASSET_THRESHOLD_EOK:   float = 2300.0   # 총자산 2,300억원 이하 (매출액 기준 부적합 시)
SME_UNRATED_RW:            float = 0.85     # 중소기업 무등급 위험가중치 85%
