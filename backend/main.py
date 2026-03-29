"""
Basel III RWA Calculator — FastAPI Backend
"""
import logging
import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.rag_engine import get_rag_status, warm_vectorstore
from app.routers import chat, calculate, db_query

settings = get_settings()


def _configure_logging() -> None:
    """애플리케이션 로그가 uvicorn 콘솔에도 보이도록 기본 로깅을 설정한다."""
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    if not root_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(levelname)s:%(name)s:%(message)s")
        )
        root_logger.addHandler(handler)


_configure_logging()

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
app.include_router(db_query.router, prefix="/api/db-query", tags=["DB Query"])


@app.get("/", tags=["Root"])
async def root():
    return {
        "service": "Basel III RWA Calculator API",
        "status": "ok",
        "docs": "/docs",
        "health": "/api/health",
    }


@app.get("/api/health", tags=["Health"])
async def health():
    return {
        "status": "ok",
        "service": "Basel III RWA API",
        "rag": get_rag_status(),
    }


def _warm_rag_in_background():
    try:
        warm_vectorstore()
        print("[Startup] 벡터스토어 백그라운드 초기화 완료.")
    except Exception as e:
        print(f"[Startup] 벡터스토어 백그라운드 초기화 실패 (채팅 기능 지연 가능): {e}")


@app.on_event("startup")
async def startup_event():
    """앱 시작 시 RAG 초기화를 백그라운드에서 시작한다."""
    if not settings.rag_warmup_on_startup:
        print("[Startup] RAG startup warmup is disabled.")
        return

    app.state.rag_warmup_thread = threading.Thread(
        target=_warm_rag_in_background,
        name="rag-warmup",
        daemon=True,
    )
    app.state.rag_warmup_thread.start()
