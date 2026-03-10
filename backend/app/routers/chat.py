"""
채팅 라우터 — Basel III 세칙 RAG Q&A (스트리밍 SSE)
"""
import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.schemas.chat import ChatRequest, ChatResponse, SourceDoc
from app.core.rag_engine import retrieve_docs, stream_answer

router = APIRouter()


@router.post("/stream")
async def chat_stream(req: ChatRequest):
    """Server-Sent Events 방식으로 LLM 응답을 실시간 스트리밍."""
    docs = retrieve_docs(req.query)

    async def event_generator():
        # 먼저 소스 문서를 첫 번째 이벤트로 전송
        sources = [
            {"content": doc.page_content[:300], "metadata": doc.metadata}
            for doc in docs
        ]
        yield f"data: {json.dumps({'type': 'sources', 'sources': sources}, ensure_ascii=False)}\n\n"

        # 스트리밍 답변 전송
        async for text_chunk in stream_answer(req.query, docs):
            payload = json.dumps({"type": "chunk", "text": text_chunk}, ensure_ascii=False)
            yield f"data: {payload}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """단일 요청-응답 (스트리밍 불필요한 경우)."""
    docs = retrieve_docs(req.query)
    full_answer = ""
    async for chunk in stream_answer(req.query, docs):
        full_answer += chunk

    sources = [
        SourceDoc(content=doc.page_content[:300], metadata=doc.metadata)
        for doc in docs
    ]
    return ChatResponse(answer=full_answer, sources=sources)
