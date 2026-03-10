"""
공통 데이터 타입 — 익스포져 입력값 및 RWA 산출 결과

모든 SA/IRB 계산기가 공유하는 입력·출력 구조를 정의한다.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, TypedDict


# ── RWA 산출 결과 ────────────────────────────────────────────────────

class RwaResult(TypedDict):
    """calc_rwa() 공통 반환 타입"""
    entity_type: str    # EntityType.value 문자열
    risk_weight: float  # 위험가중치 (예: 0.20 = 20%)
    rwa: float          # 위험가중자산 = exposure × risk_weight
    basis: str          # 적용 근거 조항 (예: "제29조 나.")


# ── 기본 익스포져 입력 ────────────────────────────────────────────────

@dataclass
class BaseExposureInput:
    """모든 SA 계산기의 공통 입력 필드"""
    exposure: float                        # 익스포져 금액 (원화, 단위: 원)
    external_credit_rating: Optional[str] = None         # 적격외부신용등급 장기 표준신용등급 (예: "AA-"), None=무등급
    oecd_grade: Optional[int] = None       # OECD 국가신용도등급 (0~7), None=무등급
    is_local_currency: bool = False        # 자국통화(원화/현지통화) 표시·조달 여부
    entity_name: Optional[str] = None     # 기관명 (무위험기관·MDB 판별 등에 활용)
