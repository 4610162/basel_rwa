"""
Reasoning Agent Node

역할:
- 검색 문서와 계산 결과를 그대로 답변하지 않고 중간 추론 레이어를 생성
- 질문 유형 분류, 핵심 개념, 적용 규정/산식, 논리 전개를 구조화
- answer_agent가 사용할 답변 아웃라인을 준비
"""
from __future__ import annotations

import json
import os
import re

from app.core.config import get_settings
from app.graph.state import GraphState
from app.graph.utils import format_conversation_history

REASONING_PROMPT = """\
당신은 Basel III 및 은행업감독업무시행세칙 전문가 추론 엔진입니다.

역할은 "검색된 문서를 바로 답변하는 것"이 아니라, 최종 답변 전에 필요한 추론 구조를 만드는 것입니다.
반드시 아래 단계를 순서대로 수행하세요.

1. 질문 유형 분류
2. 핵심 개념 추출
3. 필요한 규정/산식 선택
4. 논리 전개
5. 답변 생성용 아웃라인 작성

중요 규칙:
- retrieved docs는 참고 자료이며, 그대로 복사하지 마세요.
- 계산 결과가 있으면 논리에 반영하세요.
- 직접 대응 조문이 약하면 Basel III 일반 원칙으로 보완하세요.
- 반드시 JSON만 출력하세요.

출력 JSON 스키마:
{{
  "question_type": "regulation interpretation | calculation | conceptual explanation | scenario analysis",
  "key_concepts": ["..."],
  "selected_rules": ["..."],
  "selected_formulas": ["..."],
  "reasoning_steps": ["..."],
  "answer_outline": ["..."]
}}

## 사용자 질문
{question}

## 최근 대화 맥락
{history}

## 기존 분류 결과
- intent: {intent}
- exposure_type: {exposure_type}
- regulation_path: {regulation_path}

## 검색 문서
{context_blocks}

## 계산 결과
{calc_section}
"""


async def reasoning_node(state: GraphState) -> dict:
    """검색/계산 결과를 바탕으로 구조화된 reasoning layer를 생성한다."""
    from google import genai as google_genai

    settings = get_settings()
    api_key = settings.google_api_key or os.getenv("GOOGLE_API_KEY", "")
    client = google_genai.Client(api_key=api_key)
    question = state.get("normalized_question") or state["user_question"]

    prompt = REASONING_PROMPT.format(
        question=question,
        history=format_conversation_history(state.get("conversation_history", [])),
        intent=state.get("intent", ""),
        exposure_type=state.get("exposure_type", ""),
        regulation_path=", ".join(state.get("regulation_path", [])) or "없음",
        context_blocks=_format_context(state.get("retrieved_docs", [])),
        calc_section=_format_calc_section(state),
    )

    raw_json: dict = {}
    error_messages: list[str] = []
    for model_name in (settings.primary_model, settings.fallback_model):
        try:
            response = await client.aio.models.generate_content(
                model=model_name,
                contents=prompt,
            )
            raw_json = _parse_json_response(response.text or "")
            break
        except Exception as exc:
            error_messages.append(f"{model_name}: {exc}")

    if not raw_json:
        return _fallback_reasoning(state, error=" / ".join(error_messages))

    return {
        "question_type": _safe_str(
            raw_json.get("question_type"),
            default=_infer_question_type(state),
        ),
        "key_concepts": _safe_list(raw_json.get("key_concepts")),
        "selected_rules": _safe_list(raw_json.get("selected_rules")) or state.get("cited_rules", []),
        "selected_formulas": _safe_list(raw_json.get("selected_formulas")),
        "reasoning_steps": _safe_list(raw_json.get("reasoning_steps")),
        "answer_outline": _safe_list(raw_json.get("answer_outline")),
    }


def _parse_json_response(text: str) -> dict:
    text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        return json.loads(match.group())
    return json.loads(text)


def _format_context(docs: list[dict]) -> str:
    if not docs:
        return "검색 문서 없음"
    return "\n\n---\n\n".join(
        f"[참조 {idx + 1}]\n{doc.get('content', '')}"
        for idx, doc in enumerate(docs[:5])
    )


def _format_calc_section(state: GraphState) -> str:
    calc_result = state.get("calc_result")
    validation_errors = state.get("validation_errors", [])
    intermediate_steps = state.get("intermediate_steps", [])
    assumptions = state.get("assumptions", [])

    if calc_result:
        step_lines = "\n".join(
            f"- {step.get('step', '')}: {step.get('result', '')}"
            for step in intermediate_steps
        ) or "- 계산 단계 없음"
        assumption_lines = "\n".join(f"- {item}" for item in assumptions) or "- 없음"
        return (
            f"- exposure_type: {calc_result.get('entity_type', 'N/A')}\n"
            f"- risk_weight_pct: {calc_result.get('risk_weight_pct', 'N/A')}\n"
            f"- rwa: {calc_result.get('rwa', 'N/A')}\n"
            f"- basis: {calc_result.get('basis', 'N/A')}\n"
            f"- steps:\n{step_lines}\n"
            f"- assumptions:\n{assumption_lines}"
        )

    if validation_errors:
        return "\n".join(f"- {error}" for error in validation_errors)

    return "계산 결과 없음"


def _fallback_reasoning(state: GraphState, error: str = "") -> dict:
    question_type = _infer_question_type(state)
    reasoning_steps = [
        f"질문 유형을 {question_type}로 분류했습니다.",
        "질문에서 핵심 리스크와 변수, 규제 프레임워크를 식별했습니다.",
    ]

    if state.get("retrieved_docs"):
        reasoning_steps.append("검색된 규정 문서 중 직접 관련성이 높은 근거를 우선 검토했습니다.")
    if state.get("calc_result"):
        reasoning_steps.append("계산 결과를 규제 해석과 함께 검증했습니다.")
    else:
        reasoning_steps.append("계산 정보가 부족하거나 계산이 필요 없는 질문으로 처리했습니다.")

    return {
        "question_type": question_type,
        "key_concepts": _derive_key_concepts(state),
        "selected_rules": state.get("cited_rules", []),
        "selected_formulas": _derive_formula_hints(state),
        "reasoning_steps": reasoning_steps,
        "answer_outline": [
            "핵심 결론 요약",
            "Basel III 및 세칙 기준 해설",
            "필요 시 계산 또는 예시 제시",
            "관련 조문 또는 일반 원칙 정리",
        ],
        "error": state.get("error") or (f"reasoning fallback 사용: {error}" if error else None),
    }


def _infer_question_type(state: GraphState) -> str:
    intent = state.get("intent", "")
    if intent == "calculation_only":
        return "calculation"
    if intent == "regulation_plus_calculation":
        return "scenario analysis"
    if intent == "clarification_needed":
        return "calculation"
    return "regulation interpretation"


def _derive_key_concepts(state: GraphState) -> list[str]:
    concepts: list[str] = []
    if state.get("exposure_type"):
        concepts.append(state["exposure_type"])
    if state.get("entities", {}).get("rating"):
        concepts.append(f"rating:{state['entities']['rating']}")
    if state.get("calc_result", {}).get("risk_weight_pct") is not None:
        concepts.append(f"risk_weight:{state['calc_result']['risk_weight_pct']}")
    return concepts


def _derive_formula_hints(state: GraphState) -> list[str]:
    if state.get("calc_result"):
        return ["RWA = Exposure x Risk Weight"]
    return []


def _safe_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _safe_str(value, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default
