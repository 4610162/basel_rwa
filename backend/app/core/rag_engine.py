"""
RAG Engine — Basel III 세칙 검색 및 스트리밍 답변 생성 모듈.

Streamlit 의존성을 제거하고 FastAPI/순수 Python 환경에 맞게 재작성.
"""
from __future__ import annotations

import os
import re
import threading
import time
from functools import lru_cache
from pathlib import Path
from typing import AsyncGenerator

import chromadb
from google.genai import errors as genai_errors
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import get_settings

_warmup_lock = threading.Lock()
_warmup_state = {
    "started": False,
    "ready": False,
    "error": None,
}


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
    db_path = settings.resolved_chroma_db_path
    Path(db_path).mkdir(parents=True, exist_ok=True)
    print(f"[RAG] ChromaDB path: {db_path}")
    return chromadb.PersistentClient(path=db_path)


# ── 벡터스토어 ─────────────────────────────────────────────────────────────────
def get_vectorstore():
    """ChromaDB 벡터스토어 반환. data/*.md 기준으로 증분 동기화한다."""
    from langchain_chroma import Chroma

    settings = get_settings()
    chroma_client = get_chroma_client()
    embedding_fn = get_embedding_model()

    _sync_vectorstore(chroma_client, embedding_fn)

    return Chroma(
        client=chroma_client,
        collection_name=settings.collection_name,
        embedding_function=embedding_fn,
    )


def warm_vectorstore() -> None:
    """벡터스토어를 한 번만 초기화하고 상태를 기록한다."""
    if _warmup_state["ready"]:
        return

    with _warmup_lock:
        if _warmup_state["ready"]:
            return

        _warmup_state["started"] = True
        _warmup_state["error"] = None

        try:
            get_vectorstore()
        except Exception as exc:
            _warmup_state["error"] = str(exc)
            raise
        else:
            _warmup_state["ready"] = True


def get_rag_status() -> dict[str, str | bool | None]:
    """RAG 초기화 상태를 헬스체크에서 조회할 수 있게 반환한다."""
    status = "ready" if _warmup_state["ready"] else "initializing" if _warmup_state["started"] else "idle"
    return {
        "status": status,
        "ready": _warmup_state["ready"],
        "error": _warmup_state["error"],
    }


def _is_vectorstore_empty() -> bool:
    settings = get_settings()
    db_path = Path(settings.resolved_chroma_db_path)
    if not db_path.exists():
        return True
    return not any(db_path.iterdir())


def _list_markdown_files() -> list[Path]:
    settings = get_settings()
    data_dir = Path(settings.resolved_data_dir)
    if not data_dir.exists():
        raise FileNotFoundError(f"data 디렉터리를 찾을 수 없습니다: {data_dir.resolve()}")

    md_files = sorted(p for p in data_dir.glob("*.md") if p.is_file())
    if not md_files:
        raise FileNotFoundError(f"임베딩할 Markdown 파일이 없습니다: {data_dir.resolve()}/*.md")
    return md_files


def _get_or_create_collection(chroma_client):
    settings = get_settings()
    try:
        return chroma_client.get_collection(settings.collection_name)
    except Exception:
        return chroma_client.create_collection(settings.collection_name)


def _collection_has_legacy_docs(collection) -> bool:
    """기존 단일 문서 인덱스처럼 source_path 메타데이터가 없는 경우를 감지한다."""
    if collection.count() == 0:
        return False

    payload = collection.get(include=["metadatas"])
    metadatas = payload.get("metadatas") or []
    return any(not metadata or "source_path" not in metadata for metadata in metadatas)


def _collection_needs_rechunk(collection) -> bool:
    """현재 설정과 다른 chunk 기준으로 만들어진 인덱스면 재구축이 필요하다."""
    settings = get_settings()
    if collection.count() == 0:
        return False

    payload = collection.get(include=["metadatas"])
    metadatas = payload.get("metadatas") or []
    for metadata in metadatas:
        if not metadata:
            continue
        if metadata.get("chunk_size") != settings.chunk_size:
            return True
        if metadata.get("chunk_overlap") != settings.chunk_overlap:
            return True
    return False


def _sync_vectorstore(chroma_client, embedding_fn) -> None:
    """data/*.md 전체를 기준으로 신규 파일만 컬렉션에 추가한다."""
    settings = get_settings()
    md_files = _list_markdown_files()

    if _is_vectorstore_empty():
        _build_vectorstore(chroma_client, embedding_fn, md_files)
        return

    collection = _get_or_create_collection(chroma_client)
    if collection.count() == 0:
        _build_vectorstore(chroma_client, embedding_fn, md_files)
        return

    if _collection_has_legacy_docs(collection):
        print("[RAG] 기존 단일 문서 인덱스를 감지하여 전체 Markdown 파일로 재구축합니다.")
        _build_vectorstore(chroma_client, embedding_fn, md_files)
        return

    if _collection_needs_rechunk(collection):
        print(
            f"[RAG] chunk 설정 변경 감지 (size={settings.chunk_size}, overlap={settings.chunk_overlap}). "
            "전체 Markdown 파일로 재구축합니다.",
            flush=True,
        )
        _build_vectorstore(chroma_client, embedding_fn, md_files)
        return

    payload = collection.get(include=["metadatas"])
    metadatas = payload.get("metadatas") or []
    indexed_paths = {
        metadata["source_path"]
        for metadata in metadatas
        if metadata and metadata.get("source_path")
    }

    new_files = [md_path for md_path in md_files if str(md_path.resolve()) not in indexed_paths]
    if not new_files:
        return

    print(f"[RAG] 신규 Markdown {len(new_files)}개 감지. 증분 임베딩을 시작합니다.")
    _add_files_to_collection(collection, embedding_fn, new_files)


def _build_vectorstore(chroma_client, embedding_fn, md_files: list[Path] | None = None) -> None:
    """Markdown 전체 청킹 → 임베딩 → ChromaDB 재구축."""
    settings = get_settings()
    md_files = md_files or _list_markdown_files()

    try:
        chroma_client.delete_collection(settings.collection_name)
    except Exception:
        pass

    collection = chroma_client.create_collection(settings.collection_name)
    _add_files_to_collection(collection, embedding_fn, md_files)


def _add_files_to_collection(collection, embedding_fn, md_files: list[Path]) -> None:
    """주어진 Markdown 파일들만 청킹하여 기존 컬렉션에 추가한다."""
    from langchain_community.document_loaders import UnstructuredMarkdownLoader
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    settings = get_settings()

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=["\n\n", "\n", ".", " ", ""],
    )

    all_texts: list[str] = []
    all_metadatas: list[dict] = []
    ids: list[str] = []

    for md_path in md_files:
        resolved_path = str(md_path.resolve())
        print(f"[RAG] {md_path} 로딩 및 청킹 시작...", flush=True)
        loader = UnstructuredMarkdownLoader(str(md_path))
        docs = loader.load()
        chunks = splitter.split_documents(docs)
        print(f"[RAG] {md_path.name} 청킹 완료: {len(chunks)}개 청크", flush=True)

        source_key = md_path.stem.replace(" ", "_")
        for chunk_idx, chunk in enumerate(chunks):
            all_texts.append(chunk.page_content)
            metadata = dict(chunk.metadata or {})
            metadata["source_path"] = resolved_path
            metadata["source_file"] = md_path.name
            metadata["chunk_size"] = settings.chunk_size
            metadata["chunk_overlap"] = settings.chunk_overlap
            all_metadatas.append(metadata)
            ids.append(f"{source_key}:chunk_{chunk_idx}")

    if not all_texts:
        raise ValueError("청킹 결과가 비어 있습니다. Markdown 파일 내용을 확인하세요.")

    batch_size = max(1, settings.embedding_batch_size)
    batch_sleep = max(0, settings.embedding_batch_sleep_seconds)
    total_batches = (len(all_texts) + batch_size - 1) // batch_size

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=3, min=10, max=120),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def _embed_batch(texts: list[str]) -> list[list[float]]:
        return embedding_fn.embed_documents(texts)

    all_embeddings: list[list[float]] = []
    for batch_idx, i in enumerate(range(0, len(all_texts), batch_size), start=1):
        batch_texts = all_texts[i : i + batch_size]
        print(
            f"[RAG] 임베딩 중: 배치 {batch_idx}/{total_batches} "
            f"(청크 {i + 1}-{min(i + batch_size, len(all_texts))}/{len(all_texts)})",
            flush=True,
        )
        embeddings = _embed_batch(batch_texts)
        all_embeddings.extend(embeddings)
        print(f"[RAG] 임베딩 완료: 배치 {batch_idx}/{total_batches}", flush=True)
        if i + batch_size < len(all_texts):
            print(f"[RAG] 다음 배치 전 {batch_sleep}초 대기", flush=True)
            time.sleep(batch_sleep)

    print("[RAG] ChromaDB 저장 시작...", flush=True)
    collection.add(
        ids=ids,
        embeddings=all_embeddings,
        documents=all_texts,
        metadatas=all_metadatas,
    )
    print(
        f"[RAG] 임베딩 반영 완료! 총 {len(md_files)}개 파일, {len(all_texts)}개 청크 저장.",
        flush=True,
    )


# ── 검색 ───────────────────────────────────────────────────────────────────────
def retrieve_docs(
    query: str,
    k: int | None = None,
    translated_query: str | None = None,
) -> list:
    """쿼리와 유사도 높은 상위 k개 문서 반환.

    translated_query가 주어지면 _translate_query_to_english() API 호출을 생략한다.
    (agent 모드에서 classification_node가 번역을 이미 수행한 경우 활용)
    """
    settings = get_settings()
    warm_vectorstore()
    vectorstore = get_vectorstore()
    top_k = k or settings.top_k

    primary_docs = vectorstore.similarity_search(query, k=top_k)

    # 번역 질의가 외부에서 이미 제공된 경우 API 호출 생략
    if translated_query is None:
        translated_query = _translate_query_to_english(query)

    if not translated_query or translated_query.strip() == query.strip():
        return primary_docs

    secondary_docs = vectorstore.similarity_search(translated_query, k=top_k)
    return _merge_retrieved_docs(primary_docs, secondary_docs, limit=top_k)


def _contains_korean(text: str) -> bool:
    return bool(re.search(r"[가-힣]", text or ""))


def _translate_query_to_english(query: str) -> str | None:
    """한국어 질문이면 검색용 영어 질의로 짧게 변환한다."""
    if not _contains_korean(query):
        return None

    api_key = get_settings().google_api_key or os.getenv("GOOGLE_API_KEY", "")
    if not api_key:
        return None

    try:
        from google import genai as google_genai

        client = google_genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=get_settings().primary_model,
            contents=(
                "Translate the Korean Basel III / banking regulation search query into concise English "
                "for retrieval. Preserve key finance terms such as RWA, Basel III, exposure class, "
                "standardised approach, PD, LGD, EAD. Output English only.\n\n"
                f"Query: {query}"
            ),
        )
        translated = (response.text or "").strip()
        return translated or None
    except Exception:
        return None


def _merge_retrieved_docs(primary_docs: list, secondary_docs: list, limit: int) -> list:
    """두 검색 결과를 교차 병합하고 중복을 제거한다."""
    merged: list = []
    seen_keys: set[tuple[str, str]] = set()

    max_len = max(len(primary_docs), len(secondary_docs))
    for idx in range(max_len):
        for docs in (primary_docs, secondary_docs):
            if idx >= len(docs):
                continue
            doc = docs[idx]
            metadata = dict(getattr(doc, "metadata", {}) or {})
            key = (
                str(metadata.get("source_path", "")),
                getattr(doc, "page_content", ""),
            )
            if key in seen_keys:
                continue
            seen_keys.add(key)
            merged.append(doc)
            if len(merged) >= limit:
                return merged

    return merged[:limit]


# ── 규정검색 모드 전용 프롬프트 ───────────────────────────────────────────────
_REGULATION_PROMPT_TEMPLATE = """\
You are a Basel III and Korean FSS (은행업감독업무시행세칙) regulatory expert.

YOUR ONLY ROLE: Retrieve and explain what the regulations explicitly state.

## [Strict Policy]

- Answer ONLY based on retrieved regulation documents below
- NEVER perform calculations or numerical estimates
- NEVER speculate or infer beyond what is explicitly written in the documents
- NEVER suggest "switching modes" in the body — add it only in 제한사항 if relevant
- If a clause is not found in the retrieved documents, state it clearly

## [Output Format — use EXACTLY these 4 sections]

### 결론
[Direct answer to what the regulation states — 2~3 lines max]

### 관련 조항
[Article/clause numbers and key text from the retrieved documents]
[If not found: "검색된 문서에서 직접 대응되는 조항을 확인하지 못했습니다."]

### 핵심 기준
[Thresholds, conditions, or criteria stated in the regulation]
[If not applicable: 해당 없음]

### 제한사항
[Scope boundaries, exceptions, or what the regulation does NOT cover]
[If the question involves calculation: "RWA 계산이 필요하다면 **계산 모드**를 이용해주세요."]

## [Critical Rules]

- NEVER fabricate article numbers or clause text
- NEVER copy retrieved text verbatim — summarize accurately
- Keep each section concise and factual

## Retrieved Documents

{context_blocks}

## User Question

{query}

## Answer (Korean Only)

"""

# ── 스트리밍 답변 생성 ─────────────────────────────────────────────────────────
async def stream_answer(query: str, context_docs: list, mode: str = "agent") -> AsyncGenerator[str, None]:
    """검색 컨텍스트 기반 Gemini 스트리밍 답변 생성기.

    mode="regulation" 일 때는 retrieval-first 규정검색 전용 프롬프트를 사용한다.
    그 외(mode="agent" 등)는 기존 reasoning-first 프롬프트를 사용한다.
    """
    from google import genai as google_genai

    settings = get_settings()
    api_key = settings.google_api_key or os.getenv("GOOGLE_API_KEY", "")
    genai_client = google_genai.Client(api_key=api_key)

    context_blocks = "\n\n---\n\n".join(
        f"[참조 {i + 1}]\n{doc.page_content}"
        for i, doc in enumerate(context_docs)
    )

    if mode == "regulation":
        prompt = _REGULATION_PROMPT_TEMPLATE.format(
            context_blocks=context_blocks or "관련 조문 검색 결과 없음",
            query=query,
        )
        async def _stream_regulation():
            try:
                stream = await genai_client.aio.models.generate_content_stream(
                    model=settings.primary_model,
                    contents=prompt,
                )
                async for chunk in stream:
                    if chunk.text:
                        yield chunk.text
            except Exception as e:
                if isinstance(e, genai_errors.ClientError) and e.code == 429:
                    yield f"\n\n> ⚠️ {settings.primary_model} 할당량 초과. {settings.fallback_model}로 전환합니다.\n\n"
                    try:
                        stream = await genai_client.aio.models.generate_content_stream(
                            model=settings.fallback_model,
                            contents=prompt,
                        )
                        async for chunk in stream:
                            if chunk.text:
                                yield chunk.text
                    except Exception as e2:
                        yield f"\n❌ 모델 전환 호출 실패: {e2}"
                else:
                    yield f"\n❌ 답변 생성 중 오류 발생: {e}"

        async for chunk in _stream_regulation():
            yield chunk
        return

    # ── agent/default 모드: 기존 reasoning-first 프롬프트 ─────────────────────
    prompt = f"""
You are an expert regulatory assistant specializing in banking regulation and Basel III capital framework.

Your purpose is to provide accurate explanations and calculation guidance related to:

- Basel III capital regulation
- Korean banking supervisory regulations (은행업감독업무시행세칙)
- Credit risk risk-weighted assets (RWA)
- Loan loss provisioning standards
- Regulatory capital calculation methods
- Exposure classification and regulatory treatment

You answer questions using the regulatory documents retrieved from the knowledge base.

---------------------------------------------------------------------

ROLE

You act as a regulatory analysis assistant for banking professionals.

Your responsibilities include:
- Explaining regulatory rules
- Interpreting supervisory regulation text
- Guiding RWA and provisioning calculations
- Identifying regulatory classification of exposures
- Providing structured explanations of formulas and variables

Your responses must be written in Korean using a professional regulatory tone.

---------------------------------------------------------------------

KNOWLEDGE SOURCE

Your answers must rely ONLY on the retrieved regulatory documents.

The knowledge base may include:

- Basel III framework
- 은행업감독업무시행세칙
- 위험가중자산 산출 규정
- 충당금 적립 기준
- 기타 금융 감독 규정 문서

If the answer cannot be found in the retrieved context, respond with:

"제공된 규정 문서에서 해당 근거를 찾을 수 없습니다."

Do NOT answer from general knowledge if the rule is not present in the provided context.

---------------------------------------------------------------------

ANSWERING POLICY

When answering a question:

1. First explain the regulatory rule or supervisory principle.
2. Then provide interpretation or application if needed.
3. Use structured formatting for clarity.
4. Define technical terms when they appear in formulas.
5. Maintain neutral and precise regulatory language.

Avoid speculation or assumptions.

---------------------------------------------------------------------

REGULATORY INTERPRETATION

When interpreting regulation:

- Follow the literal meaning of the regulatory text.
- Avoid creating interpretations not supported by the document.
- If multiple interpretations are possible, state them explicitly.

---------------------------------------------------------------------

CALCULATION POLICY

When the question involves calculations such as RWA or provisioning:

1. Identify the exposure type
   (corporate, bank, sovereign, retail, securitization, derivative, etc.)

2. Present the relevant formula.

3. Define all variables used in the formula.

4. Explain the calculation process step-by-step.

Example structure:

규정 설명  
관련 산식  
변수 정의  
계산 절차

If input data is missing, explain what additional information is required.

---------------------------------------------------------------------

CITATION RULE

Whenever possible, include the regulatory basis.

Example format:

근거 규정  
은행업감독업무시행세칙 [조항 또는 별표]

If the clause number is unclear, reference the closest identifiable section.

---------------------------------------------------------------------

SAFETY AND LIMITATIONS

You must NOT:

- Invent regulatory rules
- Provide unsupported interpretations
- Fabricate clause references
- Assume missing regulatory information

If the question falls outside regulatory content (e.g., investment advice, trading strategy), politely state that it is outside the system's scope.

---------------------------------------------------------------------

OUTPUT FORMAT

Structure responses using clear sections when appropriate.

Example:

규정 설명  
계산 방법  
결론  
근거 규정

Use concise professional language.

---------------------------------------------------------------------

GOAL

Your primary objective is to provide reliable regulatory explanations grounded in official banking supervisory rules and Basel III standards.

--------------------------------
## [Math / LaTeX Rules]

- Inline: $...$
- Block:
$$
\begin{{aligned}}
...
\end{{aligned}}
$$
    
--------------------------------
## Context (Retrieved Documents)

{context_blocks}

--------------------------------
## User Question

{query}

--------------------------------
## Final Answer (Korean Only)

"""

    async def _stream(model: str):
        return await genai_client.aio.models.generate_content_stream(
            model=model,
            contents=prompt,
        )

    def _is_quota_error(e: Exception) -> bool:
        return isinstance(e, genai_errors.ClientError) and e.code == 429

    try:
        stream = await _stream(settings.primary_model)
        async for chunk in stream:
            if chunk.text:
                yield chunk.text
    except Exception as e:
        if _is_quota_error(e):
            yield f"\n\n> ⚠️ {settings.primary_model} 할당량 초과. {settings.fallback_model}로 전환합니다.\n\n"
            try:
                stream = await _stream(settings.fallback_model)
                async for chunk in stream:
                    if chunk.text:
                        yield chunk.text
            except Exception as e2:
                yield f"\n❌ 모델 전환 호출 실패: {e2}"
        else:
            yield f"\n❌ 답변 생성 중 오류 발생: {e}"
