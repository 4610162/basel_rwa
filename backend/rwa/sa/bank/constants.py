"""
SA 은행(Bank) 익스포져 — 위험가중치 테이블 상수

근거: 은행업감독업무시행세칙 [별표 3] 제35조, 제35조의2, 제36조
"""
from rwa.common.grade import GradeBucket

# ── 제35조 가. — 은행 익스포져, 외부신용등급 기반 위험가중치 ─────────────────
# 정부소유 정책은행 제외; 정부 암묵적 지원 반영 불가
BANK_EXT_RW: dict[GradeBucket, float] = {
    GradeBucket.AAA_AA_MINUS:   0.20,  # 20%
    GradeBucket.A_PLUS_A_MINUS: 0.30,  # 30%
    GradeBucket.BBB:            0.50,  # 50%
    GradeBucket.BB_B_MINUS:     1.00,  # 100%
    GradeBucket.BELOW_B_MINUS:  1.50,  # 150%
}

# ── 제35조 나. — 실사(Due Diligence) 등급 기반 위험가중치 ──────────────────
# 무등급 은행에 대해 거래은행이 자체 산정한 실사등급 적용
BANK_DD_RW: dict[str, float] = {
    "A": 0.40,   # 40%  (단, CET1비율 ≥14% + 단순기본자본비율 ≥5% 충족 시 30%)
    "B": 0.75,   # 75%
    "C": 1.50,   # 150%
}

# 제35조 나. A등급 중 우량(CET1 ≥14% & 단순기본자본비율 ≥5%) → 30%
BANK_DD_A_HIGH_QUALITY_RW: float = 0.30

# ── 제35조 라. (1) — 단기 원화 익스포져, 외부신용등급 기반 위험가중치 ─────────
# 원화 표시·조달, 원만기 3개월 이내 or 6개월 이내 무역거래에 적용
# (채권이 계속 연장·대환되어 3개월 초과 시 제외)
BANK_SHORT_EXT_RW: dict[GradeBucket, float] = {
    GradeBucket.AAA_AA_MINUS:   0.20,  # 20%
    GradeBucket.A_PLUS_A_MINUS: 0.20,  # 20%
    GradeBucket.BBB:            0.20,  # 20%
    GradeBucket.BB_B_MINUS:     0.50,  # 50%
    GradeBucket.BELOW_B_MINUS:  1.50,  # 150%
}

# ── 제35조 라. (2) — 단기 원화 익스포져, 실사등급 기반 위험가중치 ─────────────
BANK_SHORT_DD_RW: dict[str, float] = {
    "A": 0.20,   # 20%
    "B": 0.50,   # 50%
    "C": 1.50,   # 150%
}

# ── 제35의2. 가. — 커버드본드(이중상환청구권부채권), 외부신용등급 기반 위험가중치
COVERED_BOND_EXT_RW: dict[GradeBucket, float] = {
    GradeBucket.AAA_AA_MINUS:   0.10,  # 10%
    GradeBucket.A_PLUS_A_MINUS: 0.20,  # 20%
    GradeBucket.BBB:            0.20,  # 20%
    GradeBucket.BB_B_MINUS:     0.50,  # 50%
    GradeBucket.BELOW_B_MINUS:  1.00,  # 100%
}

# ── 제35의2. 나. — 커버드본드(무등급), 발행은행 위험가중치 → 커버드본드 위험가중치
COVERED_BOND_UNRATED_RW: dict[float, float] = {
    0.20: 0.10,   # 발행은행 20% → 커버드본드 10%
    0.30: 0.15,   # 발행은행 30% → 커버드본드 15%
    0.40: 0.20,   # 발행은행 40% → 커버드본드 20%
    0.50: 0.25,   # 발행은행 50% → 커버드본드 25%
    0.75: 0.35,   # 발행은행 75% → 커버드본드 35%
    1.00: 0.50,   # 발행은행 100% → 커버드본드 50%
    1.50: 1.00,   # 발행은행 150% → 커버드본드 100%
}
