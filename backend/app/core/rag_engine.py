"""
RAG Engine — Basel III 세칙 검색 및 스트리밍 답변 생성 모듈.

Streamlit 의존성을 제거하고 FastAPI/순수 Python 환경에 맞게 재작성.
"""
from __future__ import annotations

import os
import time
from functools import lru_cache
from pathlib import Path
from typing import AsyncGenerator

import chromadb
from google.api_core import exceptions
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import get_settings

BATCH_SIZE = 5
BATCH_SLEEP = 3  # seconds between embedding batches


# ── 임베딩 모델 ────────────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def get_embedding_model():
    from langchain_google_genai import GoogleGenerativeAIEmbeddings

    settings = get_settings()
    api_key = settings.google_api_key or os.getenv("GOOGLE_API_KEY", "")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")
    return GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-001",
        google_api_key=api_key,
    )


# ── ChromaDB 클라이언트 ─────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def get_chroma_client():
    settings = get_settings()
    return chromadb.PersistentClient(path=settings.chroma_db_path)


# ── 벡터스토어 ─────────────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def get_vectorstore():
    """ChromaDB 벡터스토어 반환. 미구축 시 MD 파일로 인덱싱."""
    from langchain_chroma import Chroma

    settings = get_settings()
    chroma_client = get_chroma_client()
    embedding_fn = get_embedding_model()

    # DB가 비어있으면 빌드
    if _is_vectorstore_empty():
        _build_vectorstore(chroma_client, embedding_fn)
    else:
        try:
            existing = chroma_client.get_collection(settings.collection_name)
            if existing.count() == 0:
                _build_vectorstore(chroma_client, embedding_fn)
        except Exception:
            _build_vectorstore(chroma_client, embedding_fn)

    return Chroma(
        client=chroma_client,
        collection_name=settings.collection_name,
        embedding_function=embedding_fn,
    )


def _is_vectorstore_empty() -> bool:
    settings = get_settings()
    db_path = Path(settings.chroma_db_path)
    if not db_path.exists():
        return True
    return not any(db_path.iterdir())


def _build_vectorstore(chroma_client, embedding_fn) -> None:
    """MD 파일 청킹 → 임베딩 → ChromaDB 저장."""
    from langchain_community.document_loaders import UnstructuredMarkdownLoader
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    settings = get_settings()
    md_path = Path(settings.data_dir) / "basel3.md"
    if not md_path.exists():
        raise FileNotFoundError(f"basel3.md 파일을 찾을 수 없습니다: {md_path.resolve()}")

    print(f"[RAG] {md_path} 로딩 및 청킹 시작...")
    loader = UnstructuredMarkdownLoader(str(md_path))
    docs = loader.load()

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=["\n\n", "\n", ".", " ", ""],
    )
    chunks = splitter.split_documents(docs)

    all_texts = [c.page_content for c in chunks]
    all_metadatas = [c.metadata for c in chunks]
    total_batches = (len(all_texts) + BATCH_SIZE - 1) // BATCH_SIZE

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def _embed_batch(texts: list[str]) -> list[list[float]]:
        return embedding_fn.embed_documents(texts)

    all_embeddings: list[list[float]] = []
    for batch_idx, i in enumerate(range(0, len(all_texts), BATCH_SIZE), start=1):
        batch_texts = all_texts[i : i + BATCH_SIZE]
        print(f"[RAG] 임베딩 중: 배치 {batch_idx}/{total_batches}")
        embeddings = _embed_batch(batch_texts)
        all_embeddings.extend(embeddings)
        if i + BATCH_SIZE < len(all_texts):
            time.sleep(BATCH_SLEEP)

    try:
        chroma_client.delete_collection(settings.collection_name)
    except Exception:
        pass

    collection = chroma_client.create_collection(settings.collection_name)
    ids = [f"chunk_{i}" for i in range(len(all_texts))]
    collection.add(
        ids=ids,
        embeddings=all_embeddings,
        documents=all_texts,
        metadatas=all_metadatas,
    )
    print(f"[RAG] 벡터 DB 구축 완료! 총 {len(all_texts)}개 청크 저장.")


# ── 검색 ───────────────────────────────────────────────────────────────────────
def retrieve_docs(query: str, k: int | None = None) -> list:
    """쿼리와 유사도 높은 상위 k개 문서 반환."""
    settings = get_settings()
    vectorstore = get_vectorstore()
    return vectorstore.similarity_search(query, k=k or settings.top_k)


# ── 스트리밍 답변 생성 ─────────────────────────────────────────────────────────
async def stream_answer(query: str, context_docs: list) -> AsyncGenerator[str, None]:
    """검색 컨텍스트 기반 Gemini 스트리밍 답변 생성기."""
    from google import genai as google_genai

    settings = get_settings()
    api_key = settings.google_api_key or os.getenv("GOOGLE_API_KEY", "")
    genai_client = google_genai.Client(api_key=api_key)

    context_blocks = "\n\n---\n\n".join(
        f"[참조 {i + 1}]\n{doc.page_content}"
        for i, doc in enumerate(context_docs)
    )

    prompt = f"""당신은 금융감독원 은행업감독업무시행세칙 전문가입니다.
아래 세칙 원문 발췌본을 근거로 질문에 답변하세요.

**답변 규칙:**
1. 반드시 관련 조항(예: **제29조 제1항**)을 명시하세요.
2. 세칙에 없는 내용은 "현재 세칙에서 해당 내용을 찾을 수 없습니다."라고만 답하세요.
3. 근거 없는 추측이나 창작을 절대 하지 마세요.
4. 답변은 마크다운 형식으로 작성하세요.
5. 여러 조항이 관련된 경우 항목별로 구분해 설명하세요.
6. 수학 수식은 반드시 LaTeX 형식을 사용하세요:
   - 인라인 수식: `$...$`
   - 블록 수식: `$$...$$`
   - 여러 줄 정렬 수식: `$$\n\\begin{aligned}\n수식\n\\end{aligned}\n$$` 형태로 작성하세요.
   - `\\begin{split}` 환경은 절대 사용하지 마세요. 반드시 `\\begin{aligned}`를 사용하세요.
   - 수식 블록은 반드시 `$$`로 감싸야 합니다.

## 세칙 원문 발췌

{context_blocks}

## 질문

{query}

## 답변
"""

    def _try_stream(model: str):
        return genai_client.models.generate_content_stream(
            model=model,
            contents=prompt,
        )

    try:
        stream = _try_stream(settings.primary_model)
        for chunk in stream:
            if chunk.text:
                yield chunk.text
    except exceptions.ResourceExhausted:
        yield f"\n\n> ⚠️ {settings.primary_model} 할당량 초과. {settings.fallback_model}로 전환합니다.\n\n"
        try:
            stream = _try_stream(settings.fallback_model)
            for chunk in stream:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            yield f"\n❌ 모델 전환 호출 실패: {e}"
    except Exception as e:
        yield f"\n❌ 답변 생성 중 오류 발생: {e}"
