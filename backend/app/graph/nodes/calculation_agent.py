"""
Calculation Agent Node

역할:
- GraphState의 extracted_params를 RwaCalculationRequest로 변환
- 기존 calculate_rwa() 서비스를 그대로 재사용
- 파라미터 검증 오류 및 계산 가정 사항을 state에 기록
"""
from __future__ import annotations

from app.graph.state import GraphState


def calculation_node(state: GraphState) -> dict:
    """
    LangGraph Node: RWA 계산 실행.
    기존 calculate_rwa() 함수를 그대로 재사용한다.
    """
    from app.schemas.rwa import RwaCalculationRequest
    from app.services.rwa_service import calculate_rwa

    params = state.get("extracted_params", {})

    # 계산 파라미터가 비어있으면 즉시 반환
    if not params:
        return {
            "calc_result": None,
            "intermediate_steps": [],
            "validation_errors": ["계산 파라미터가 추출되지 않았습니다."],
            "assumptions": [],
        }

    # None 값 제거 (Pydantic 기본값 우선)
    clean_params = {k: v for k, v in params.items() if v is not None}

    assumptions: list[str] = []
    validation_errors: list[str] = []

    # 신용등급 미제공 가정 기록
    if not clean_params.get("external_credit_rating"):
        assumptions.append("신용등급 미제공 → 무등급(unrated) 기준 적용")

    try:
        req = RwaCalculationRequest(**clean_params)
    except Exception as e:
        return {
            "calc_result": None,
            "intermediate_steps": [],
            "validation_errors": [f"파라미터 검증 오류: {e}"],
            "assumptions": assumptions,
        }

    try:
        result = calculate_rwa(req)
    except ValueError as e:
        validation_errors.append(str(e))
        return {
            "calc_result": None,
            "intermediate_steps": [],
            "validation_errors": validation_errors,
            "assumptions": assumptions,
        }
    except NotImplementedError as e:
        validation_errors.append(f"미지원 계산 유형: {e}")
        return {
            "calc_result": None,
            "intermediate_steps": [],
            "validation_errors": validation_errors,
            "assumptions": assumptions,
        }
    except Exception as e:
        validation_errors.append(f"계산 내부 오류: {e}")
        return {
            "calc_result": None,
            "intermediate_steps": [],
            "validation_errors": validation_errors,
            "assumptions": assumptions,
        }

    intermediate_steps = [
        {"step": "익스포져 유형", "result": result.entity_type},
        {"step": "위험가중치", "result": result.risk_weight_pct},
        {"step": "RWA", "result": f"{result.rwa:,.0f}원"},
        {"step": "적용 근거", "result": result.basis},
    ]

    return {
        "calc_result": result.model_dump(),
        "intermediate_steps": intermediate_steps,
        "validation_errors": validation_errors,
        "assumptions": assumptions,
    }
