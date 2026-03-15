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
from pydantic import BaseModel

from app.schemas.chat import ChatRequest, ChatResponse, SourceDoc
from app.core.rag_engine import retrieve_docs, stream_answer

router = APIRouter()


# ── 기존 엔드포인트 (하위 호환 — 변경 없음) ───────────────────────────────────

@router.post("/stream")
async def chat_stream(req: ChatRequest):
    """기존: Server-Sent Events 방식으로 LLM 응답을 실시간 스트리밍."""
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
    question: str


class AgentResponse(BaseModel):
    final_answer: str
    intent: str = ""
    exposure_type: str = ""
    calc_result: dict | None = None
    citations: list[str] = []
    uncertainty_notes: list[str] = []
    error: str | None = None


# ── LangGraph Agent 엔드포인트 ─────────────────────────────────────────────────

@router.post("/agent", response_model=AgentResponse)
async def chat_agent(req: AgentRequest):
    """
    LangGraph orchestration — JSON 응답.

    graph.ainvoke()로 전체 워크플로를 실행하고 구조화된 결과를 반환한다.
    classification → regulation/calculation → answer 순으로 실행.
    """
    from app.graph.builder import get_graph

    graph = get_graph()
    initial_state = _make_initial_state(req.question)

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

    graph = get_graph()
    initial_state = _make_initial_state(req.question)

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

def _make_initial_state(question: str) -> dict:
    """graph.ainvoke()에 전달할 초기 상태를 생성한다."""
    return {
        "user_question": question,
        "normalized_question": "",
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


def _build_enriched_query(original_question: str, result: dict) -> str:
    """
    계산 결과를 포함한 강화된 쿼리 생성.
    stream_answer()에 전달하여 계산 결과를 답변에 반영한다.
    """
    calc_result = result.get("calc_result")
    if not calc_result:
        return original_question

    calc_summary = (
        f"\n\n[계산 결과]\n"
        f"- 익스포져 유형: {calc_result.get('entity_type', 'N/A')}\n"
        f"- 위험가중치: {calc_result.get('risk_weight_pct', 'N/A')}\n"
        f"- RWA: {calc_result.get('rwa', 0):,.0f}원\n"
        f"- 적용 근거: {calc_result.get('basis', 'N/A')}"
    )
    return original_question + calc_summary


class _FakeDoc:
    """stream_answer()가 기대하는 .page_content 속성을 가진 경량 객체."""
    def __init__(self, content: str):
        self.page_content = content


def _dicts_to_fake_docs(docs: list[dict]) -> list[_FakeDoc]:
    """retrieved_docs dict 리스트 → stream_answer 호환 객체 변환."""
    return [_FakeDoc(d["content"]) for d in docs]
