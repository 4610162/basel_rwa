"""
Answer Agent Node

역할:
- Regulation Agent + Calculation Agent 결과를 결합
- Gemini를 사용하여 사용자 친화적 최종 답변 생성
- 불확실성(가정 사항, 누락 정보) 명시
- clarification_needed인 경우 재질문 생성

기존 rag_engine.stream_answer()의 프롬프트 스타일을 유지하여 일관된 답변 품질 보장.
"""
from __future__ import annotations

import os

from app.core.config import get_settings
from app.graph.state import GraphState

ANSWER_PROMPT_TEMPLATE = """\
당신은 금융감독원 은행업감독업무시행세칙 전문가입니다.
아래 세칙 원문 발췌본과 계산 결과를 바탕으로 질문에 답변하세요.

**답변 규칙:**
1. 반드시 관련 조항(예: **제29조 제1항**)을 명시하세요.
2. 세칙에 없는 내용은 "현재 세칙에서 해당 내용을 찾을 수 없습니다."라고만 답하세요.
3. 근거 없는 추측이나 창작을 절대 하지 마세요.
4. 답변은 마크다운 형식으로 작성하세요.
5. 여러 조항이 관련된 경우 항목별로 구분해 설명하세요.
6. 수학 수식은 반드시 LaTeX 형식을 사용하세요:
   - 인라인 수식: `$...$`
   - 블록 수식: `$$...$$`
   - 여러 줄 정렬 수식: `$$\\begin{{aligned}}\\n수식\\n\\end{{aligned}}$$`
   - `\\begin{{split}}` 환경은 사용하지 마세요. 반드시 `\\begin{{aligned}}`를 사용하세요.
{calc_section}
## 세칙 원문 발췌

{context_blocks}

## 질문

{question}

## 답변
"""

CLARIFICATION_PROMPT_TEMPLATE = """\
당신은 금융감독원 은행업감독업무시행세칙 전문가입니다.
사용자가 RWA 계산을 요청했지만 아래 필수 정보가 부족합니다.

**누락된 정보:**
{missing_list}

아래 세칙 원문을 참고하여:
1. 어떤 정보가 왜 필요한지 친절하게 설명하세요.
2. 각 정보의 예시 값을 제시하세요.
3. 마크다운 형식으로 작성하세요.

## 세칙 원문 발췌 (참고용)

{context_blocks}

## 사용자 질문

{question}

## 답변
"""


async def answer_node(state: GraphState) -> dict:
    """
    LangGraph Node: 최종 답변 생성.
    Gemini generate_content (non-streaming) 를 사용한다.
    /chat/stream 엔드포인트는 이 결과를 SSE로 후처리한다.
    """
    from google import genai as google_genai

    settings = get_settings()
    api_key = settings.google_api_key or os.getenv("GOOGLE_API_KEY", "")
    client = google_genai.Client(api_key=api_key)

    intent = state.get("intent", "regulation_only")
    missing_fields = state.get("missing_fields", [])

    # ── clarification_needed: 재질문 생성 ─────────────────────────────────────
    if intent == "clarification_needed":
        prompt = _build_clarification_prompt(state)
    else:
        prompt = _build_answer_prompt(state)

    final_answer = await _generate(client, settings, prompt)

    # ── uncertainty_notes 구성 ─────────────────────────────────────────────────
    uncertainty_notes: list[str] = []
    if state.get("assumptions"):
        uncertainty_notes.extend(f"가정: {a}" for a in state["assumptions"])
    if state.get("validation_errors"):
        uncertainty_notes.extend(f"계산 오류: {e}" for e in state["validation_errors"])
    if missing_fields and intent != "clarification_needed":
        uncertainty_notes.append(f"미확인 파라미터: {', '.join(missing_fields)}")

    return {
        "final_answer": final_answer,
        "uncertainty_notes": uncertainty_notes,
    }


# ── 프롬프트 빌더 ──────────────────────────────────────────────────────────────

def _build_answer_prompt(state: GraphState) -> str:
    """regulation_only / calculation_only / regulation_plus_calculation 용 프롬프트."""
    retrieved_docs = state.get("retrieved_docs", [])
    calc_result = state.get("calc_result")
    intermediate_steps = state.get("intermediate_steps", [])
    assumptions = state.get("assumptions", [])
    validation_errors = state.get("validation_errors", [])

    context_blocks = _format_context(retrieved_docs)

    # ── 계산 결과 섹션 구성 ──────────────────────────────────────────────────
    calc_section = ""
    if calc_result:
        steps_str = "\n".join(
            f"  - {s['step']}: {s['result']}" for s in intermediate_steps
        )
        assumptions_str = (
            "\n- **적용 가정:** " + ", ".join(assumptions) if assumptions else ""
        )
        calc_section = f"""
7. 계산 결과가 있으면 계산 과정을 단계별로 설명하고, 최종 RWA를 강조해서 표시하세요.

## 계산 결과 (참고)

- **익스포져 유형:** {calc_result.get('entity_type', 'N/A')}
- **위험가중치:** {calc_result.get('risk_weight_pct', 'N/A')}
- **RWA:** {calc_result.get('rwa', 0):,.0f}원
- **적용 근거:** {calc_result.get('basis', 'N/A')}
- **계산 단계:**
{steps_str}{assumptions_str}
"""
    elif validation_errors:
        errors_str = "\n".join(f"  - {e}" for e in validation_errors)
        calc_section = f"""
## 계산 오류

다음 오류로 인해 RWA를 계산할 수 없었습니다:
{errors_str}

규정 설명만 제공합니다.
"""

    return ANSWER_PROMPT_TEMPLATE.format(
        calc_section=calc_section,
        context_blocks=context_blocks or "관련 조문 검색 결과 없음",
        question=state["user_question"],
    )


def _build_clarification_prompt(state: GraphState) -> str:
    """clarification_needed 용 재질문 프롬프트."""
    missing_fields = state.get("missing_fields", [])
    retrieved_docs = state.get("retrieved_docs", [])

    # 누락 필드 → 한국어 설명 매핑
    field_descriptions = {
        "exposure": "익스포져 금액 (예: 100억원)",
        "exposure_category": "익스포져 카테고리 (gov/bank/corp/realestate/equity/ciu/securitization)",
        "entity_type": "엔티티 세부 유형 (예: general, central_gov 등)",
        "external_credit_rating": "적격외부신용등급 (예: AAA, AA+, BBB-)",
        "ltv_ratio": "담보인정비율 LTV (예: 60%, 0.6)",
        "re_exposure_type": "부동산 익스포져 유형 (cre_non_ipre/cre_ipre/adc/pf_consortium)",
        "attachment_point": "Attachment Point A (유동화 익스포져)",
        "detachment_point": "Detachment Point D (유동화 익스포져)",
        "k_sa": "기초자산 풀 SA 자기자본비율 K_SA (유동화)",
        "w": "연체·부실 자산 비율 W (유동화)",
        "ciu_approach": "CIU 접근법 (lta/mba/fba)",
    }

    missing_list = "\n".join(
        f"- **{f}**: {field_descriptions.get(f, f)}"
        for f in missing_fields
    ) or "- 추가 정보 필요"

    context_blocks = _format_context(retrieved_docs[:3])

    return CLARIFICATION_PROMPT_TEMPLATE.format(
        missing_list=missing_list,
        context_blocks=context_blocks or "관련 조문 없음",
        question=state["user_question"],
    )


def _format_context(docs: list[dict]) -> str:
    """retrieved_docs를 컨텍스트 블록 문자열로 변환."""
    if not docs:
        return ""
    return "\n\n---\n\n".join(
        f"[참조 {i + 1}]\n{doc['content']}"
        for i, doc in enumerate(docs[:5])
    )


async def _generate(client, settings, prompt: str) -> str:
    """Gemini generate_content 호출. 쿼터 초과 시 fallback 모델로 재시도."""
    from google.genai import errors as genai_errors

    try:
        response = await client.aio.models.generate_content(
            model=settings.primary_model,
            contents=prompt,
        )
        return response.text or ""
    except Exception as e:
        is_quota = isinstance(e, genai_errors.ClientError) and e.code == 429
        if is_quota:
            try:
                response = await client.aio.models.generate_content(
                    model=settings.fallback_model,
                    contents=prompt,
                )
                return response.text or ""
            except Exception as e2:
                return f"답변 생성 중 오류가 발생했습니다: {e2}"
        return f"답변 생성 중 오류가 발생했습니다: {e}"
