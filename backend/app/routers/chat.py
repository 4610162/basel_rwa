"""
채팅 라우터 — Basel III 세칙 RAG Q&A

엔드포인트:
  POST /stream   모드 기반 통합 스트리밍
                 mode = "agent"        : AI 규정·계산 (LangGraph 전체 파이프라인 — 규정검색·해석·계산 통합)
                 mode = "data_analysis": AI 데이터분석 (식별자 기반 시계열 조회 + 시각화)

마이그레이션 노트:
  - "regulation" 모드는 제거됨. agent 모드가 regulation_only intent를 포함하여 처리.
  - "calculation" 모드는 제거됨. agent 모드가 calculation intent를 포함하여 처리.
  - 하위 호환: 구 mode 값("regulation", "calculation")은 model_validator에서 "agent"로 자동 변환.
"""
from __future__ import annotations

import json

from fastapi import APIRouter
from pydantic import BaseModel, Field, model_validator

from app.routers.sse import create_sse_response, sse_data, sse_done

router = APIRouter()

# ── 요청 모델 ──────────────────────────────────────────────────────────────────

VALID_MODES = {"agent", "data_analysis"}


class UnifiedChatRequest(BaseModel):
    query: str = ""
    question: str = ""          # agent mode 호환 (기존 프론트 payload)
    history: list[dict] = []
    mode: str = "agent"         # "agent" | "data_analysis"

    @model_validator(mode="after")
    def normalize(self) -> "UnifiedChatRequest":
        self.query = (self.question or self.query).strip()
        if not self.query:
            raise ValueError("query 또는 question 필드가 필요합니다.")
        # 구 모드 값("regulation", "calculation")은 "agent"로 안전하게 변환
        if self.mode not in VALID_MODES:
            self.mode = "agent"
        return self


# ── 통합 엔드포인트 ───────────────────────────────────────────────────────────

@router.post("/stream")
async def chat_stream(req: UnifiedChatRequest):
    """
    모드에 따라 실행 정책을 선택한다.

    agent       → AI 규정·계산: LangGraph (분류 → 규정/계산 → 추론 → 답변) + DB 조회 지원
    data_analysis → AI 데이터분석: AI Call#1 파싱 → 코드 SQL → AI Call#2 + 위젯 응답
    """
    if req.mode == "data_analysis":
        return await _handle_data_analysis_stream(req.query, req.history)
    return await _handle_agent_stream(req.query, req.history)


# ── AI 데이터분석 모드 ────────────────────────────────────────────────────────

async def _handle_data_analysis_stream(query: str, history: list[dict]):
    """
    AI 데이터분석 핸들러.

    1. AI Call #1: 자연어 → DataQuerySpec (structured)
    2. chart_type에 따라 분기:
       - "line" (추이 분석): 기간별 시계열 조회 → line_chart + data_table
       - "bar"  (비교 분석): 상품별 집계 조회  → bar_chart  + data_table
    3. 요약 통계 생성
    4. AI Call #2: 요약 통계 → 자연어 답변 스트리밍
    5. 위젯 SSE 이벤트로 페이로드 전송
    """
    from app.services.data_analysis_service import (
        PARSE_FAILURE_GUIDANCE,
        ai_generate_answer,
        ai_generate_comparison_answer,
        ai_parse_query,
        build_bar_chart_widget,
        build_chart_widget,
        build_comparison_stats,
        build_comparison_table_widget,
        build_summary_stats,
        build_table_widget,
        execute_comparison_query,
        execute_query,
    )

    async def event_generator():
        # ── AI Call #1 ─────────────────────────────────────────────────────────
        spec = await ai_parse_query(query)

        if spec is None:
            yield sse_data({"type": "chunk", "text": PARSE_FAILURE_GUIDANCE})
            yield sse_done()
            return

        yield sse_data({"type": "status", "text": "데이터를 조회하는 중입니다..."})

        is_comparison = spec.chart_type == "bar" or spec.identifier_type == "all_products"

        # ── DB 조회 ────────────────────────────────────────────────────────────
        try:
            if is_comparison:
                rows = execute_comparison_query(spec)
            else:
                rows = execute_query(spec)
        except Exception as e:
            yield sse_data({"type": "chunk", "text": f"❌ 데이터 조회 중 오류: {e}"})
            yield sse_done()
            return

        yield sse_data({"type": "status", "text": "분석 결과를 정리하는 중입니다..."})

        # ── 요약 통계 + AI Call #2 ─────────────────────────────────────────────
        try:
            if is_comparison:
                stats = build_comparison_stats(rows, spec)
                async for text_chunk in ai_generate_comparison_answer(spec, stats):
                    yield sse_data({"type": "chunk", "text": text_chunk})
            else:
                stats = build_summary_stats(rows, spec)
                async for text_chunk in ai_generate_answer(spec, stats):
                    yield sse_data({"type": "chunk", "text": text_chunk})
        except Exception as e:
            yield sse_data({"type": "chunk", "text": f"\n❌ 답변 생성 오류: {e}"})

        # ── 위젯 페이로드 (데이터가 있을 때만) ────────────────────────────────
        if rows:
            if is_comparison:
                widgets = [
                    build_comparison_table_widget(rows, spec),
                    build_bar_chart_widget(rows, spec),
                ]
            else:
                widgets = [
                    build_table_widget(rows, spec),
                    build_chart_widget(rows, spec),
                ]
            yield sse_data({"type": "widgets", "widgets": widgets})

        yield sse_done()

    return create_sse_response(event_generator())


# ── Agent 모드 (AI 규정·계산) ──────────────────────────────────────────────────

async def _handle_agent_stream(question: str, history: list[dict]):
    """
    LangGraph 전체 파이프라인 핸들러 (AI 규정·계산 모드).

    - 규정검색, 규정+계산, 순수계산, 명확화 요청 모두 처리
    - 자연어 DB 조회 우선 처리 (단일 월 기준 — 시계열은 AI 데이터분석 모드 사용)
    - pre-answer 그래프(분류 → 규정/계산 → 추론)를 ainvoke
    - Gemini 스트리밍으로 최종 답변 실시간 전송
    """
    from app.core.rag_engine import retrieve_docs, stream_answer
    from app.graph.builder import get_pre_answer_graph
    from app.graph.nodes.answer_agent import stream_final_answer
    from app.services.db_nl_query_service import (
        build_db_query_help_text,
        detect_db_query_intent,
        format_db_query_response,
        run_natural_language_db_query,
    )

    # DB 조회 우선 처리 (단순 단일 월 조회)
    if detect_db_query_intent(question):
        db_result, used_latest = run_natural_language_db_query(question)
        response_text = (
            format_db_query_response(db_result, used_latest)
            if db_result is not None
            else build_db_query_help_text()
        )

        async def db_query_generator():
            meta = {"type": "meta", "intent": "db_query", "exposure_type": ""}
            yield sse_data(meta)
            yield sse_data({"type": "sources", "sources": []})
            yield sse_data({"type": "chunk", "text": response_text or ""})
            yield sse_done()

        return create_sse_response(db_query_generator())

    graph = get_pre_answer_graph()
    initial_state = _make_initial_state(question, history)

    async def event_generator():
        try:
            yield sse_data({"type": "status", "text": "질문을 분석하고 관련 규정을 찾는 중입니다..."})

            result = await graph.ainvoke(initial_state)

            # 메타 정보
            uncertainty_notes: list[str] = []
            if result.get("assumptions"):
                uncertainty_notes.extend(f"가정: {a}" for a in result["assumptions"])
            if result.get("validation_errors"):
                uncertainty_notes.extend(f"계산 오류: {e}" for e in result["validation_errors"])
            missing_fields = result.get("missing_fields", [])
            if missing_fields and result.get("intent") != "clarification_needed":
                uncertainty_notes.append(f"미확인 파라미터: {', '.join(missing_fields)}")

            meta = {
                "type": "meta",
                "intent": result.get("intent", ""),
                "exposure_type": result.get("exposure_type", ""),
                "calc_result": result.get("calc_result"),
                "citations": result.get("cited_rules", []),
                "reasoning": _extract_reasoning_payload(result),
                "uncertainty_notes": uncertainty_notes,
            }
            yield sse_data(meta)

            # 소스 문서
            retrieved_docs = result.get("retrieved_docs", [])
            sources = [
                {"content": d["content"][:300], "metadata": d.get("metadata", {})}
                for d in retrieved_docs
            ]
            yield sse_data({"type": "sources", "sources": sources})

            # 최종 답변 스트리밍
            yield sse_data({"type": "status", "text": "추론 결과를 바탕으로 답변을 정리하는 중입니다..."})

            async for text_chunk in stream_final_answer(result):
                yield sse_data({"type": "chunk", "text": text_chunk})

            yield sse_done()

        except Exception as e:
            yield sse_data({"type": "chunk", "text": f"\n❌ Agent 스트리밍 오류: {e}"})
            yield sse_done()

    return create_sse_response(event_generator())


# ── 내부 헬퍼 ─────────────────────────────────────────────────────────────────

def _make_initial_state(question: str, history: list[dict] | None = None) -> dict:
    return {
        "user_question": question,
        "normalized_question": "",
        "conversation_history": _trim_agent_history(history),
        "intent": "",
        "exposure_type": "",
        "entities": {},
        "required_fields": [],
        "missing_fields": [],
        "regulation_path": [],
        "extracted_params": {},
        "english_query": "",
        "retrieved_docs": [],
        "cited_rules": [],
        "applicable_tables": [],
        "exceptions": [],
        "calc_result": None,
        "intermediate_steps": [],
        "validation_errors": [],
        "assumptions": [],
        "question_type": "",
        "key_concepts": [],
        "selected_rules": [],
        "selected_formulas": [],
        "reasoning_steps": [],
        "answer_outline": [],
        "final_answer": "",
        "uncertainty_notes": [],
        "error": None,
    }


def _trim_agent_history(history: list[dict] | None, max_turns: int = 5) -> list[dict[str, str]]:
    if not history:
        return []
    trimmed = history[-(max_turns * 2):]
    cleaned: list[dict[str, str]] = []
    for item in trimmed:
        role = item.get("role")
        content = str(item.get("content", "")).strip()
        if role not in {"user", "assistant"} or not content:
            continue
        cleaned.append({"role": role, "content": content})
    return cleaned


def _extract_reasoning_payload(result: dict) -> dict:
    return {
        "question_type": result.get("question_type", ""),
        "key_concepts": result.get("key_concepts", []),
        "selected_rules": result.get("selected_rules", []),
        "selected_formulas": result.get("selected_formulas", []),
        "reasoning_steps": result.get("reasoning_steps", []),
        "answer_outline": result.get("answer_outline", []),
    }
