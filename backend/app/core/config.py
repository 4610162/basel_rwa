"""
Application configuration via environment variables.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    google_api_key: str = ""
    chroma_db_path: str = "./chroma_db"
    data_dir: str = "./data"
    collection_name: str = "basel3"
    chunk_size: int = 700
    chunk_overlap: int = 100
    top_k: int = 5                          # global default (calculation mode fallback 등)
    primary_model: str = "gemini-2.5-flash"
    fallback_model: str = "gemini-2.0-flash"
    cors_origins: list[str] = ["http://localhost:3000"]

    # ── Reranker 설정 ──────────────────────────────────────────────────────────
    # 계산 모드에는 적용하지 않음
    reranker_enabled: bool = True

    # 규정검색 모드: 넓게 검색 후 좁혀서 precision 향상
    regulation_retriever_top_k: int = 8     # ChromaDB에서 뽑을 후보 수
    regulation_reranker_top_n: int = 3      # reranker 이후 최종 선택 수

    # agent 모드: 더 넓게 recall하여 복합 질의 커버
    agent_retriever_top_k: int = 12         # ChromaDB에서 뽑을 후보 수
    agent_reranker_top_n: int = 5           # reranker 이후 최종 선택 수

    # ── ONNX Reranker 설정 ───────────────────────────────────────────────────
    reranker_model_name: str = "onnx-community/bge-reranker-v2-m3-ONNX"
    reranker_onnx_filename: str = "onnx/model_quantized.onnx"
    reranker_batch_size: int = 8
    reranker_max_length: int = 512

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache(maxsize=1)
def get_gemini_client():
    """Gemini Client 싱글턴 반환. API 키는 get_settings()에서 읽는다."""
    import os
    from google import genai as google_genai

    settings = get_settings()
    api_key = settings.google_api_key or os.getenv("GOOGLE_API_KEY", "")
    return google_genai.Client(api_key=api_key)
