"""
Basel III RWA Calculator — FastAPI Backend
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.routers import chat, calculate

settings = get_settings()

app = FastAPI(
    title="Basel III RWA Calculator API",
    version="1.0.0",
    description="은행업감독업무시행세칙 기반 신용위험 RWA 산출 API (표준방법, SA)",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router, prefix="/api/chat", tags=["Chat (RAG)"])
app.include_router(calculate.router, prefix="/api/calculate", tags=["RWA Calculate"])


@app.get("/api/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": "Basel III RWA API"}


@app.on_event("startup")
async def startup_event():
    """앱 시작 시 벡터스토어를 미리 초기화."""
    from app.core.rag_engine import get_vectorstore
    try:
        get_vectorstore()
        print("[Startup] 벡터스토어 초기화 완료.")
    except Exception as e:
        print(f"[Startup] 벡터스토어 초기화 실패 (채팅 기능 불가): {e}")
