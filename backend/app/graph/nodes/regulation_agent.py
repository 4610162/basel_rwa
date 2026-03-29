"""
Regulation Agent Node

역할:
- 기존 RAG 검색 엔진(retrieve_docs)을 사용하여 관련 규정 조문 검색
- classification_node에서 추출된 regulation_path로 쿼리 보강
- 검색된 문서를 GraphState에 저장 (직렬화 형태)
"""
from __future__ import annotations

import asyncio

from app.graph.state import GraphState


async def regulation_node(state: GraphState) -> dict:
    """
    LangGraph Node: 규정 조문 검색 (agent 모드 전용).
    retrieve_docs()는 blocking I/O(ChromaDB + 임베딩)이므로
    asyncio.to_thread()로 래핑하여 이벤트 루프 블로킹을 방지한다.

    reranker_enabled=True 시: top_k 넓게 검색 → cross-encoder reranker → top_n 선택.
    reranker_enabled=False 시: 기존 동작 유지.
    """
    import logging

    from app.core.config import get_settings
    from app.core.rag_engine import retrieve_docs

    logger = logging.getLogger(__name__)
    settings = get_settings()

    question = state.get("normalized_question") or state["user_question"]
    regulation_path = state.get("regulation_path", [])

    # regulation_path 힌트가 있으면 쿼리에 포함하여 검색 정확도 향상
    if regulation_path:
        enhanced_query = f"{question} {' '.join(regulation_path)}"
    else:
        enhanced_query = question

    # reranker 활성화 시 더 넓은 top_k로 후보 확보
    retriever_k = (
        settings.agent_retriever_top_k
        if settings.reranker_enabled
        else settings.top_k
    )

    # classification_node에서 이미 번역된 영어 질의를 재사용 → translate API 호출 생략
    english_query = state.get("english_query") or None

    try:
        docs = await asyncio.to_thread(
            retrieve_docs,
            enhanced_query,
            k=retriever_k,
            translated_query=english_query,
        )
    except Exception as e:
        return {
            "retrieved_docs": [],
            "cited_rules": [],
            "applicable_tables": [],
            "exceptions": [],
            "error": f"규정 검색 오류: {e}",
        }

    logger.info(
        f"[RegulationNode] retrieved={len(docs)} "
        f"reranker_enabled={settings.reranker_enabled}"
    )

    # Reranker: 후보 문서 재정렬 → 상위 top_n 선택 (agent 모드 설정 사용)
    if not settings.reranker_enabled:
        logger.info("[RegulationNode] reranker skipped | reason=disabled")
    elif len(docs) <= settings.agent_reranker_top_n:
        logger.info(
            f"[RegulationNode] reranker skipped | reason=insufficient_candidates "
            f"candidates={len(docs)} top_n={settings.agent_reranker_top_n}"
        )
    else:
        logger.info(
            f"[RegulationNode] reranker executing | candidates={len(docs)} "
            f"top_n={settings.agent_reranker_top_n}"
        )
        from app.core.reranker import rerank_docs
        docs = await rerank_docs(
            enhanced_query,
            docs,
            top_n=settings.agent_reranker_top_n,
        )

    logger.info(f"[RegulationNode] final_docs={len(docs)}")

    # Document 객체 → dict 직렬화 (GraphState 호환)
    retrieved_docs = [
        {"content": doc.page_content, "metadata": dict(doc.metadata)}
        for doc in docs
    ]

    # 검색된 문서에서 조문 번호 패턴 추출 (예: 제29조, 제37조 제1항)
    cited_rules = _extract_article_numbers(retrieved_docs)

    return {
        "retrieved_docs": retrieved_docs,
        "cited_rules": cited_rules,
        "applicable_tables": [],   # answer_agent에서 LLM이 식별
        "exceptions": [],          # answer_agent에서 LLM이 식별
    }


# ── 내부 헬퍼 ─────────────────────────────────────────────────────────────────

def _extract_article_numbers(docs: list[dict]) -> list[str]:
    """검색된 문서 텍스트에서 조문 번호를 추출한다."""
    import re

    pattern = re.compile(r"제\s*\d+\s*조(?:\s*제\s*\d+\s*항)?")
    seen: set[str] = set()
    results: list[str] = []

    for doc in docs:
        matches = pattern.findall(doc.get("content", ""))
        for m in matches:
            normalized = re.sub(r"\s+", "", m)
            if normalized not in seen:
                seen.add(normalized)
                results.append(normalized)

    return results[:10]  # 최대 10개
