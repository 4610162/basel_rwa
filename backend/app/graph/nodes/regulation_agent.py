"""
Regulation Agent Node

역할:
- 기존 RAG 검색 엔진(retrieve_docs)을 사용하여 관련 규정 조문 검색
- classification_node에서 추출된 regulation_path로 쿼리 보강
- 검색된 문서를 GraphState에 저장 (직렬화 형태)
"""
from __future__ import annotations

from app.graph.state import GraphState


def regulation_node(state: GraphState) -> dict:
    """
    LangGraph Node: 규정 조문 검색.
    기존 retrieve_docs() 함수를 그대로 재사용한다.
    """
    from app.core.rag_engine import retrieve_docs

    question = state.get("normalized_question") or state["user_question"]
    regulation_path = state.get("regulation_path", [])

    # regulation_path 힌트가 있으면 쿼리에 포함하여 검색 정확도 향상
    if regulation_path:
        enhanced_query = f"{question} {' '.join(regulation_path)}"
    else:
        enhanced_query = question

    try:
        docs = retrieve_docs(enhanced_query)
    except Exception as e:
        return {
            "retrieved_docs": [],
            "cited_rules": [],
            "applicable_tables": [],
            "exceptions": [],
            "error": f"규정 검색 오류: {e}",
        }

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
