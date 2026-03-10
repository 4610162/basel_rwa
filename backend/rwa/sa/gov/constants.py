"""
SA 정부(Sovereign) 익스포져 — 위험가중치 테이블 상수

근거: 은행업감독업무시행세칙 [별표 3] 제29조~제34조
"""
from rwa.common.grade import GradeBucket

# ── 제29조 가.(1) — 중앙정부·중앙은행 위험가중치 ─────────────────────
GOV_RW: dict[GradeBucket, float] = {
    GradeBucket.AAA_AA_MINUS:   0.00,  # 0%
    GradeBucket.A_PLUS_A_MINUS: 0.20,  # 20%
    GradeBucket.BBB:            0.50,  # 50%
    GradeBucket.BB_B_MINUS:     1.00,  # 100%
    GradeBucket.BELOW_B_MINUS:  1.50,  # 150%
    GradeBucket.UNRATED:        1.00,  # 100%
}

# ── 제34조 가. — 일반 국제개발은행(MDB) 위험가중치 ──────────────────
MDB_RW: dict[GradeBucket, float] = {
    GradeBucket.AAA_AA_MINUS:   0.20,  # 20%
    GradeBucket.A_PLUS_A_MINUS: 0.30,  # 30%
    GradeBucket.BBB:            0.50,  # 50%
    GradeBucket.BB_B_MINUS:     1.00,  # 100%
    GradeBucket.BELOW_B_MINUS:  1.50,  # 150%
    GradeBucket.UNRATED:        0.50,  # 50%
}

# ── 제35조 가. — 은행 위험가중치 (PSE·외국 공공기관 준용) ───────────
# 무등급은 제35조 나.의 실사등급 체계를 별도 적용하므로 여기서 정의하지 않음
BANK_RW: dict[GradeBucket, float] = {
    GradeBucket.AAA_AA_MINUS:   0.20,  # 20%
    GradeBucket.A_PLUS_A_MINUS: 0.30,  # 30%
    GradeBucket.BBB:            0.50,  # 50%
    GradeBucket.BB_B_MINUS:     1.00,  # 100%
    GradeBucket.BELOW_B_MINUS:  1.50,  # 150%
}

# ── 제30조 — 무위험기관 목록 ─────────────────────────────────────────
# BIS, IMF, ECB, EU, ESM, EFSF → 위험가중치 0%
ZERO_RISK_ENTITIES: frozenset[str] = frozenset({
    "BIS", "IMF", "ECB", "EU", "ESM", "EFSF",
})

# 한글 기관명 → 영문 약어 alias (calc_rw_zero_risk_entity 에서 사용)
ZERO_RISK_ENTITY_ALIAS: dict[str, str] = {
    "국제결제은행":   "BIS",
    "국제통화기금":   "IMF",
    "유럽중앙은행":   "ECB",
    "유럽공동체":     "EU",
    "유럽재정안정기구": "ESM",
    "유럽재정안정기금": "EFSF",
}

# ── 제34조 나. — 0% 우량 MDB 목록 ────────────────────────────────────
# 다음 요건을 모두 충족하여 감독당국이 지정한 기관 → 위험가중치 0%
#   (1) 채무자 신용등급 AAA
#   (2) AA- 이상 중앙정부 상당 지분 보유 또는 레버리지 없는 납입자본 우세
#   (3) 충분한 납입자본금·capital call·지속 출자 약정 입증
#   (4) 건전한 자본적정성 및 유동성 보유
ZERO_RISK_MDBS: frozenset[str] = frozenset({
    "세계은행그룹(WBG)",
    "국제통화기금(IMF)",
    "국제결제은행(BIS)",
    "아시아개발은행(ADB)",
    "아프리카개발은행(AfDB)",
    "유럽부흥개발은행(EBRD)",
    "미주개발은행(IADB)",
    "유럽투자은행(EIB)",
    "유럽투자기금(EIF)",
    "북유럽투자은행(NIB)",
    "카리브개발은행(CDB)",
    "이슬람개발은행(IsDB)",
    "유럽평의회개발은행(CEB)",
    "국제금융공사(IFC)",
    "다자간투자보증기구(MIGA)",
})
