"""
채팅 라우터 — Basel III 세칙 RAG Q&A

엔드포인트:
  POST /stream         기존 RAG 직접 스트리밍 (하위 호환 유지)
  POST /               기존 RAG 단일 응답 (하위 호환 유지)
  POST /agent          LangGraph orchestration — JSON 응답
  POST /agent/stream   LangGraph orchestration — SSE 스트리밍
"""
from __future__ import annotations

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, model_validator

from app.schemas.chat import ChatRequest, ChatResponse, SourceDoc
from app.core.rag_engine import retrieve_docs, stream_answer

router = APIRouter()


# ── 기존 엔드포인트 (하위 호환 — 변경 없음) ───────────────────────────────────

@router.post("/stream")
async def chat_stream(req: ChatRequest):
    """기존: Server-Sent Events 방식으로 LLM 응답을 실시간 스트리밍."""
    from app.services.rwa_intent import (
        detect_calc_intent,
        build_calc_guidance,
        is_in_collection_flow,
        get_flow_exposure_type,
        accumulate_field_values,
        get_missing_required_fields,
        build_collection_response,
        is_cancel_command,
    )
    from app.services.exposure_schema import get_schema
    from app.services.db_nl_query_service import (
        build_db_query_help_text,
        detect_db_query_intent,
        format_db_query_response,
        run_natural_language_db_query,
    )

    # ── 0. 취소/초기화 명령 — 세션 상태와 무관하게 최우선 처리 ──────────────
    # (수집 중, 계산 완료 후, idle 어느 상태에서도 동작)
    if is_cancel_command(req.query):
        reset_text = (
            "✅ 현재 계산 세션을 초기화했습니다.\n\n"
            "새로 질문하거나 다시 계산을 시작할 수 있습니다.\n"
            "예: \"기업 익스포져 RWA 계산하고 싶어\""
        )

        async def reset_event_generator():
            payload = json.dumps(
                {"type": "chunk", "text": reset_text}, ensure_ascii=False
            )
            yield f"data: {payload}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            reset_event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # ── 1. 수집 흐름 진행 중인지 먼저 확인 ───────────────────────────────────
    # (이전 assistant 메시지가 입력 안내이면 수집 흐름으로 처리)
    if is_in_collection_flow(req.history):
        from app.services.rwa_intent import classify_collection_message

        exposure_type = get_flow_exposure_type(req.history)
        schema = get_schema(exposure_type) if exposure_type else None

        if schema:
            # ── 1-a. 메시지 분류: 일반질문 / 계산입력
            # (cancel은 step 0에서 이미 처리됨)
            msg_class = classify_collection_message(req.query, schema)

            # ── 1-b. 일반 규정 질문 → RAG 처리 + 세션 유지 노트 ─────────────
            if msg_class == "general_question":
                docs = retrieve_docs(req.query)

                # 현재 수집 상태 파악 (현재 메시지는 필드 입력이 아니므로 history만 사용)
                accumulated = accumulate_field_values(req.history, schema)
                missing = get_missing_required_fields(accumulated, schema)

                if missing:
                    missing_labels = ", ".join(f.label for f in missing)
                    # "입력 현황" 마커 포함 → 다음 메시지에서도 collection flow 유지
                    session_note = (
                        f"\n\n---\n"
                        f"💡 **{schema.label} 입력 현황** | "
                        f"남은 입력: **{missing_labels}**"
                    )
                else:
                    session_note = (
                        f"\n\n---\n"
                        f"💡 **{schema.label} 입력 현황** | 모든 입력값 수집 완료"
                    )

                async def rag_with_session_note_generator():
                    try:
                        sources = [
                            {"content": doc.page_content[:300], "metadata": dict(doc.metadata)}
                            for doc in docs
                        ]
                        yield f"data: {json.dumps({'type': 'sources', 'sources': sources}, ensure_ascii=False, default=str)}\n\n"

                        async for text_chunk in stream_answer(req.query, docs):
                            payload = json.dumps(
                                {"type": "chunk", "text": text_chunk}, ensure_ascii=False
                            )
                            yield f"data: {payload}\n\n"

                        # 세션 유지 노트 전송 (마커 포함)
                        note_payload = json.dumps(
                            {"type": "chunk", "text": session_note}, ensure_ascii=False
                        )
                        yield f"data: {note_payload}\n\n"
                        yield "data: [DONE]\n\n"

                    except Exception as e:
                        err_payload = json.dumps(
                            {"type": "chunk", "text": f"\n❌ 스트리밍 오류: {e}"},
                            ensure_ascii=False,
                        )
                        yield f"data: {err_payload}\n\n"
                        yield "data: [DONE]\n\n"

                return StreamingResponse(
                    rag_with_session_note_generator(),
                    media_type="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
                )

            # ── 1-c. 계산 입력값 → 기존 슬롯필링 로직 ───────────────────────
            else:  # msg_class == "calc_input"
                full_history = req.history + [{"role": "user", "content": req.query}]
                accumulated = accumulate_field_values(full_history, schema)
                missing = get_missing_required_fields(accumulated, schema)

                if missing:
                    response_text = build_collection_response(accumulated, missing, schema)
                else:
                    response_text = _run_chat_calculation(accumulated, schema, full_history)

                async def collection_event_generator():
                    payload = json.dumps(
                        {"type": "chunk", "text": response_text}, ensure_ascii=False
                    )
                    yield f"data: {payload}\n\n"
                    yield "data: [DONE]\n\n"

                return StreamingResponse(
                    collection_event_generator(),
                    media_type="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
                )

    # ── 2. 자연어 DB조회 요청 감지 ───────────────────────────────────────────
    if detect_db_query_intent(req.query):
        db_result, used_latest = run_natural_language_db_query(req.query)
        response_text = (
            format_db_query_response(db_result, used_latest)
            if db_result is not None
            else build_db_query_help_text()
        )

        async def db_query_event_generator():
            payload = json.dumps({"type": "chunk", "text": response_text}, ensure_ascii=False)
            yield f"data: {payload}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            db_query_event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # ── 3. RWA 계산 의도 감지: 해당 시 안내 응답 즉시 반환 ──────────────────
    if detect_calc_intent(req.query):
        from app.services.db_lookup_service import (
            detect_identifier,
            lookup_exposure_from_db,
            build_prefill_marker,
        )
        from app.services.rwa_field_parser import format_amount

        # ── 2-a. 거래 식별자 감지 → DB 자동 조회 ─────────────────────────────
        prefill_suffix = ""
        identifier = detect_identifier(req.query)
        if identifier:
            id_type, id_value = identifier
            id_label = "대출번호" if id_type == "loan_no" else "상품코드"
            db_result = lookup_exposure_from_db(id_type, id_value)

            if db_result and db_result["record_count"] == 1:
                # 단일 레코드 — 익스포져 금액 자동 보완
                exposure_display = format_amount(db_result["exposure"])
                nm = db_result.get("product_code_nm", "")
                nm_note = f", {nm}" if nm else ""
                prefill_suffix = (
                    f"\n\n> 📌 **DB 자동 조회 완료**"
                    f" ({id_label} {id_value}, 기준월 {db_result['base_ym']}{nm_note})\n"
                    f"> 익스포져 금액 **{exposure_display}**이 자동 적용됩니다."
                    f" 아래 항목 중 익스포져 금액은 건너뛰고 나머지만 입력해주세요.\n"
                    f"{build_prefill_marker(db_result)}"
                )
            elif db_result and db_result["record_count"] > 1:
                # 복수 레코드 — 자동 보완 불가
                prefill_suffix = (
                    f"\n\n> ⚠️ {id_label} **{id_value}**에 해당하는 레코드가"
                    f" {db_result['record_count']}건으로 익스포져 금액을 특정할 수 없습니다."
                    f" 대출번호를 함께 입력하거나 익스포져 금액을 직접 입력해주세요.\n"
                )
            else:
                # 조회 결과 없음 또는 CSV 없음
                prefill_suffix = (
                    f"\n\n> ⚠️ {id_label} **{id_value}**에 해당하는 데이터를"
                    f" DB에서 찾을 수 없습니다. 익스포져 금액을 직접 입력해주세요.\n"
                )

        guidance = build_calc_guidance(req.query) + prefill_suffix

        async def calc_event_generator():
            payload = json.dumps({"type": "chunk", "text": guidance}, ensure_ascii=False)
            yield f"data: {payload}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            calc_event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # ── 4. 기존 RAG 흐름 ──────────────────────────────────────────────────────
    docs = retrieve_docs(req.query)

    async def event_generator():
        try:
            sources = [
                {"content": doc.page_content[:300], "metadata": dict(doc.metadata)}
                for doc in docs
            ]
            yield f"data: {json.dumps({'type': 'sources', 'sources': sources}, ensure_ascii=False, default=str)}\n\n"

            async for text_chunk in stream_answer(req.query, docs):
                payload = json.dumps({"type": "chunk", "text": text_chunk}, ensure_ascii=False)
                yield f"data: {payload}\n\n"

            yield "data: [DONE]\n\n"
        except Exception as e:
            err_payload = json.dumps(
                {"type": "chunk", "text": f"\n❌ 스트리밍 오류: {e}"}, ensure_ascii=False
            )
            yield f"data: {err_payload}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """기존: 단일 요청-응답 (스트리밍 불필요한 경우)."""
    docs = retrieve_docs(req.query)
    full_answer = ""
    async for chunk in stream_answer(req.query, docs):
        full_answer += chunk

    sources = [
        SourceDoc(content=doc.page_content[:300], metadata=doc.metadata)
        for doc in docs
    ]
    return ChatResponse(answer=full_answer, sources=sources)


# ── LangGraph Agent 응답 스키마 ────────────────────────────────────────────────

class AgentRequest(BaseModel):
    question: str = ""
    query: str = ""
    history: list[dict] = []

    @model_validator(mode="after")
    def validate_question(self) -> "AgentRequest":
        # Frontend legacy payload uses `query`; agent endpoints use `question`.
        # Accept both so the API remains backward compatible.
        self.question = (self.question or self.query).strip()
        if not self.question:
            raise ValueError("question 또는 query 필드가 필요합니다.")
        return self


class AgentResponse(BaseModel):
    final_answer: str
    intent: str = ""
    exposure_type: str = ""
    calc_result: dict | None = None
    citations: list[str] = []
    uncertainty_notes: list[str] = []
    error: str | None = None


def _run_agent_db_query(question: str) -> tuple[str | None, bool]:
    """Agent Mode용 자연어 DB조회 응답을 생성한다."""
    from app.services.db_nl_query_service import (
        build_db_query_help_text,
        detect_db_query_intent,
        format_db_query_response,
        run_natural_language_db_query,
    )

    if not detect_db_query_intent(question):
        return None, False

    db_result, used_latest = run_natural_language_db_query(question)
    response_text = (
        format_db_query_response(db_result, used_latest)
        if db_result is not None
        else build_db_query_help_text()
    )
    return response_text, True


# ── LangGraph Agent 엔드포인트 ─────────────────────────────────────────────────

@router.post("/agent", response_model=AgentResponse)
async def chat_agent(req: AgentRequest):
    """
    LangGraph orchestration — JSON 응답.

    graph.ainvoke()로 전체 워크플로를 실행하고 구조화된 결과를 반환한다.
    classification → regulation/calculation → answer 순으로 실행.
    """
    from app.graph.builder import get_graph

    db_response_text, handled = _run_agent_db_query(req.question)
    if handled:
        return AgentResponse(
            final_answer=db_response_text or "",
            intent="db_query",
        )

    graph = get_graph()
    initial_state = _make_initial_state(req.question, req.history)

    try:
        result = await graph.ainvoke(initial_state)
    except Exception as e:
        return AgentResponse(
            final_answer=f"워크플로 실행 중 오류가 발생했습니다: {e}",
            error=str(e),
        )

    return AgentResponse(
        final_answer=result.get("final_answer", ""),
        intent=result.get("intent", ""),
        exposure_type=result.get("exposure_type", ""),
        calc_result=result.get("calc_result"),
        citations=result.get("cited_rules", []),
        uncertainty_notes=result.get("uncertainty_notes", []),
        error=result.get("error"),
    )


@router.post("/agent/stream")
async def chat_agent_stream(req: AgentRequest):
    """
    LangGraph orchestration — SSE 스트리밍 응답.

    워크플로(classify → regulate → calculate → answer)를 ainvoke로 실행한 후,
    기존 stream_answer()를 사용하여 최종 답변을 실시간 스트리밍한다.
    """
    from app.graph.builder import get_graph

    db_response_text, handled = _run_agent_db_query(req.question)
    if handled:
        async def db_query_event_generator():
            meta = {"type": "meta", "intent": "db_query", "exposure_type": ""}
            yield f"data: {json.dumps(meta, ensure_ascii=False, default=str)}\n\n"
            yield f"data: {json.dumps({'type': 'sources', 'sources': []}, ensure_ascii=False, default=str)}\n\n"
            payload = json.dumps({"type": "chunk", "text": db_response_text or ""}, ensure_ascii=False)
            yield f"data: {payload}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            db_query_event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    graph = get_graph()
    initial_state = _make_initial_state(req.question, req.history)

    async def event_generator():
        try:
            # ── 1단계: 전체 graph 실행 (classify + regulate + calculate + answer) ─
            result = await graph.ainvoke(initial_state)

            # ── 2단계: 메타 정보 전송 ────────────────────────────────────────────
            meta = {
                "type": "meta",
                "intent": result.get("intent", ""),
                "exposure_type": result.get("exposure_type", ""),
                "calc_result": result.get("calc_result"),
                "citations": result.get("cited_rules", []),
                "uncertainty_notes": result.get("uncertainty_notes", []),
            }
            yield f"data: {json.dumps(meta, ensure_ascii=False, default=str)}\n\n"

            # ── 3단계: 소스 문서 전송 ────────────────────────────────────────────
            retrieved_docs = result.get("retrieved_docs", [])
            sources = [
                {"content": d["content"][:300], "metadata": d.get("metadata", {})}
                for d in retrieved_docs
            ]
            yield f"data: {json.dumps({'type': 'sources', 'sources': sources}, ensure_ascii=False, default=str)}\n\n"

            # ── 4단계: 답변 스트리밍 ─────────────────────────────────────────────
            intent = result.get("intent", "")
            final_answer = result.get("final_answer", "")

            if intent == "clarification_needed" or not retrieved_docs:
                # clarification 또는 검색 결과 없음 → 이미 생성된 답변 전송
                payload = json.dumps({"type": "chunk", "text": final_answer}, ensure_ascii=False)
                yield f"data: {payload}\n\n"
            else:
                # 계산 결과를 반영한 강화 쿼리로 stream_answer 재실행
                enriched_query = _build_enriched_query(req.question, result)
                doc_objects = _dicts_to_fake_docs(retrieved_docs)

                async for text_chunk in stream_answer(enriched_query, doc_objects):
                    payload = json.dumps({"type": "chunk", "text": text_chunk}, ensure_ascii=False)
                    yield f"data: {payload}\n\n"

            yield "data: [DONE]\n\n"

        except Exception as e:
            err_payload = json.dumps(
                {"type": "chunk", "text": f"\n❌ Agent 스트리밍 오류: {e}"}, ensure_ascii=False
            )
            yield f"data: {err_payload}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── 내부 헬퍼 ─────────────────────────────────────────────────────────────────

def _make_initial_state(question: str, history: list[dict] | None = None) -> dict:
    """graph.ainvoke()에 전달할 초기 상태를 생성한다."""
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
        "retrieved_docs": [],
        "cited_rules": [],
        "applicable_tables": [],
        "exceptions": [],
        "calc_result": None,
        "intermediate_steps": [],
        "validation_errors": [],
        "assumptions": [],
        "final_answer": "",
        "uncertainty_notes": [],
        "error": None,
    }


def _trim_agent_history(history: list[dict] | None, max_turns: int = 5) -> list[dict[str, str]]:
    """최근 대화 max_turns개(사용자/어시스턴트 쌍)를 GraphState용으로 정리한다."""
    if not history:
        return []

    max_messages = max_turns * 2
    trimmed = history[-max_messages:]
    cleaned: list[dict[str, str]] = []

    for item in trimmed:
        role = item.get("role")
        content = str(item.get("content", "")).strip()
        if role not in {"user", "assistant"} or not content:
            continue
        cleaned.append({"role": role, "content": content})

    return cleaned


def _build_enriched_query(original_question: str, result: dict) -> str:
    """
    계산 결과를 포함한 강화된 쿼리 생성.
    stream_answer()에 전달하여 계산 결과를 답변에 반영한다.
    """
    history_section = _format_history_for_query(result.get("conversation_history", []))
    calc_result = result.get("calc_result")
    if not calc_result:
        return f"{history_section}\n\n[현재 질문]\n{original_question}" if history_section else original_question

    calc_summary = (
        f"\n\n[계산 결과]\n"
        f"- 익스포져 유형: {calc_result.get('entity_type', 'N/A')}\n"
        f"- 위험가중치: {calc_result.get('risk_weight_pct', 'N/A')}\n"
        f"- RWA: {calc_result.get('rwa', 0):,.0f}원\n"
        f"- 적용 근거: {calc_result.get('basis', 'N/A')}"
    )
    question_block = f"[현재 질문]\n{original_question}"
    if history_section:
        return f"{history_section}\n\n{question_block}{calc_summary}"
    return question_block + calc_summary


def _format_history_for_query(history: list[dict[str, str]]) -> str:
    """stream_answer()용 최근 대화 맥락 문자열 생성."""
    if not history:
        return ""
    lines = []
    for item in history:
        role = "사용자" if item.get("role") == "user" else "어시스턴트"
        content = item.get("content", "").strip()
        if content:
            lines.append(f"- {role}: {content}")
    if not lines:
        return ""
    return "[최근 대화 맥락]\n" + "\n".join(lines)


class _FakeDoc:
    """stream_answer()가 기대하는 .page_content 속성을 가진 경량 객체."""
    def __init__(self, content: str):
        self.page_content = content


def _dicts_to_fake_docs(docs: list[dict]) -> list[_FakeDoc]:
    """retrieved_docs dict 리스트 → stream_answer 호환 객체 변환."""
    return [_FakeDoc(d["content"]) for d in docs]


def _run_chat_calculation(
    accumulated: dict[str, str],
    schema,
    history: list[dict] | None = None,
) -> str:
    """
    수집된 필드값으로 RWA 계산을 실행하고 결과 마크다운을 반환한다.

    계산기 재구현 없이 기존 calculate_rwa()를 재사용한다.
    history가 전달되면 각 필드의 입력 출처(db/user)를 결과에 표시한다.
    계산 불가(retail 등) 또는 오류 시 명확한 안내 문자열을 반환한다.
    """
    from app.services.chat_rwa_mapper import map_to_rwa_request, format_calc_result
    from app.services.rwa_service import calculate_rwa

    # retail은 계산기 미구현
    if schema.category_id is None:
        return (
            f"### {schema.label} 입력 현황\n\n"
            "> ✅ 입력 완료: 필수 입력값이 모두 수집되었습니다.\n\n"
            f"⚠️ **{schema.label}** 유형은 현재 자동 계산 기능이 구현되어 있지 않습니다.\n"
            "수집된 입력값을 계산기 탭에서 직접 확인해주세요."
        )

    # 입력 출처 딕셔너리 구성 (history 있을 때만)
    sources: dict[str, str] = {}
    if history:
        from app.services.rwa_intent import build_field_sources
        sources = build_field_sources(history, schema, accumulated)

    try:
        rwa_req = map_to_rwa_request(accumulated, schema)
        result = calculate_rwa(rwa_req)
        return format_calc_result(result, accumulated, schema, sources=sources)

    except (ValueError, KeyError) as e:
        return (
            f"### {schema.label} 계산 오류\n\n"
            f"❌ 입력값 처리 중 오류가 발생했습니다: {e}\n\n"
            "입력값을 다시 확인하고 수정 후 재입력해주세요."
        )
    except NotImplementedError as e:
        return (
            f"### {schema.label} 계산 불가\n\n"
            f"⚠️ 해당 계산 경로는 아직 구현되지 않았습니다: {e}"
        )
    except Exception as e:
        return (
            f"### {schema.label} 계산 오류\n\n"
            f"❌ 예상치 못한 오류: {e}"
        )
