"""
SA 부동산 관련 익스포져 — 위험가중치 테이블 상수

근거: 은행업감독업무시행세칙 [별표 3] 제2장 제3절
    제41조   상업용부동산담보(CRE) 익스포져
    제41조의2 부동산개발금융(ADC) 익스포져
"""
from __future__ import annotations


# ── 제41조 가. — CRE 비-IPRE (대출상환 재원이 담보물 현금흐름에 의존하지 않을 경우) ──
# LTV ≤ 60% AND 40.가. 적격요건 충족 → min(60%, borrower_rw)
# LTV > 60% 또는 적격요건 미충족       → borrower_rw

CRE_NON_IPRE_CAP_RW: float = 0.60          # LTV ≤ 60% 구간 상한 위험가중치 (60%)
CRE_NON_IPRE_LTV_THRESHOLD: float = 0.60   # LTV 60% 분기점


# ── 제41조 나. — CRE IPRE (대출상환 재원이 담보물 현금흐름에 주로 의존할 경우) ──
# LTV ≤ 60%  → 70%
# LTV ≤ 80%  → 90%
# LTV > 80%  → 110%
# 40.가. 적격요건 미충족 → 150%

CRE_IPRE_LTV_60: float = 0.60    # LTV 1구간 상한
CRE_IPRE_LTV_80: float = 0.80    # LTV 2구간 상한

CRE_IPRE_RW_60: float  = 0.70    # LTV ≤ 60% → 70%
CRE_IPRE_RW_80: float  = 0.90    # LTV ≤ 80% → 90%
CRE_IPRE_RW_OVER: float = 1.10   # LTV > 80% → 110%
CRE_INELIGIBLE_RW: float = 1.50  # 적격요건 미충족 → 150%


# ── 제41조의2 — ADC (부동산개발금융) 익스포져 위험가중치 ─────────────────────────
# 원칙: 150%
# 주거용 예외 요건(1)(2) 충족 시: 100%

ADC_DEFAULT_RW: float     = 1.50   # 150% (기본)
ADC_RESIDENTIAL_RW: float = 1.00   # 100% (주거용 예외 충족 시)


# ── PF조합사업비 — 부동산개발금융과 동일 가중치, 시공사 연대보증 시 기업 RW 준용 ──
# 기본: 150% (ADC_DEFAULT_RW와 동일)
# 시공사 연대보증 + 적격외부신용등급 존재 시: 기업 익스포져 표준방법 RW를 그대로 사용

PF_CONSORTIUM_DEFAULT_RW: float = ADC_DEFAULT_RW  # 150%
