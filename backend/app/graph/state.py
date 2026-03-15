"""
LangGraph 상태 정의 — Basel III RAG + RWA 계산기 Agent Workflow
"""
from __future__ import annotations

from typing import Any, Optional

from typing_extensions import TypedDict


class GraphState(TypedDict):
    """
    LangGraph 워크플로 전체 상태.

    각 Agent Node가 해당 섹션을 채우며, 이후 노드에서 참조한다.
    """

    # ── 입력 ──────────────────────────────────────────────────────────────────
    user_question: str
    normalized_question: str

    # ── Classification Agent 출력 ─────────────────────────────────────────────
    intent: str
    # regulation_only | calculation_only | regulation_plus_calculation | clarification_needed

    exposure_type: str
    # sovereign | bank | corporate | real_estate | securitization | equity | ciu | other | unknown

    entities: dict[str, Any]
    # 질문에서 추출한 개체 (회사명, 등급, 금액 등)

    required_fields: list[str]
    # 익스포져 유형별 계산에 필요한 파라미터 목록

    missing_fields: list[str]
    # 질문에서 확인되지 않는 필수 파라미터

    regulation_path: list[str]
    # 예상 적용 조문 후보 (예: ["제37조", "제38조"])

    extracted_params: dict[str, Any]
    # RwaCalculationRequest로 직접 전달 가능한 파라미터 dict

    # ── Regulation Agent 출력 ─────────────────────────────────────────────────
    retrieved_docs: list[dict[str, Any]]
    # [{"content": str, "metadata": dict}, ...]

    cited_rules: list[str]
    applicable_tables: list[str]
    exceptions: list[str]

    # ── Calculation Agent 출력 ────────────────────────────────────────────────
    calc_result: Optional[dict[str, Any]]
    # RwaResult.model_dump() 결과

    intermediate_steps: list[dict[str, Any]]
    # [{"step": str, "result": str}, ...]

    validation_errors: list[str]
    assumptions: list[str]

    # ── Answer Agent 출력 ─────────────────────────────────────────────────────
    final_answer: str
    uncertainty_notes: list[str]

    # ── 메타 ──────────────────────────────────────────────────────────────────
    error: Optional[str]
