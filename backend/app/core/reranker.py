"""
Reranker Service — ONNX 기반 cross-encoder 검색 결과 재정렬 모듈.

규정검색 모드 및 agent 모드에서 ChromaDB 1차 검색 결과를
ONNX cross-encoder relevance model로 재정렬하여 상위 top_n 문서만 반환한다.

설계 원칙:
- onnxruntime + transformers(tokenizer only)만 사용 — torch 불필요
- 모델/토크나이저는 프로세스 단위 singleton으로 캐시
- 모델 로드 또는 추론 실패 시 원본 순서로 fallback
- LangChain Document 및 {"content": str, "metadata": dict} 모두 지원
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def rerank_docs(query: str, docs: list[T], top_n: int) -> list[T]:
    """
    Cross-encoder 기반 관련도 점수로 docs를 재정렬하고 상위 top_n 반환.

    Args:
        query: 사용자 질문
        docs: 재정렬할 문서 리스트
        top_n: 최종 반환할 상위 문서 수

    Returns:
        재정렬된 상위 top_n 문서 리스트
    """
    if not docs:
        return docs

    if len(docs) <= top_n:
        logger.debug(
            f"[Reranker] candidates={len(docs)} <= top_n={top_n}, reranking skipped"
        )
        return docs

    logger.info(
        f"[Reranker] start | candidates={len(docs)} top_n={top_n} "
        f"query='{query[:80]}{'...' if len(query) > 80 else ''}'"
    )

    try:
        scores = await _score_docs_with_onnx(query, docs)
        sorted_indices = sorted(range(len(docs)), key=lambda i: scores[i], reverse=True)
        reranked = [docs[i] for i in sorted_indices]
        result = reranked[:top_n]

        for rank, (doc, orig_idx) in enumerate(zip(result, sorted_indices[:top_n]), start=1):
            meta = _get_metadata(doc)
            content_preview = _get_content(doc)[:80].replace("\n", " ")
            logger.info(
                f"[Reranker] selected rank={rank} score={scores[orig_idx]:.4f} "
                f"source={meta.get('source_file', '?')} "
                f"content='{content_preview}...'"
            )

        logger.info(f"[Reranker] done | selected={len(result)}/{len(docs)}")
        return result

    except Exception as exc:
        logger.warning(
            f"[Reranker] failed, falling back to original top_{top_n}. error={exc}"
        )
        return docs[:top_n]


async def _score_docs_with_onnx(query: str, docs: list[T]) -> list[float]:
    """ONNX 세션으로 query-document pair 점수를 계산한다."""
    import asyncio

    return await asyncio.to_thread(_compute_scores_sync, query, docs)


def _compute_scores_sync(query: str, docs: list[T]) -> list[float]:
    """동기 배치 추론 — asyncio.to_thread에서 호출된다."""
    import numpy as np

    from app.core.config import get_settings

    settings = get_settings()
    session, tokenizer = _get_reranker_components()

    pairs_a = [query] * len(docs)
    pairs_b = [_get_content(doc)[:2000] for doc in docs]

    all_scores: list[float] = []
    batch_size = settings.reranker_batch_size

    # ONNX 세션이 받는 입력 이름 확인 (input_ids, attention_mask, token_type_ids)
    input_names = {inp.name for inp in session.get_inputs()}

    for i in range(0, len(docs), batch_size):
        a_batch = pairs_a[i : i + batch_size]
        b_batch = pairs_b[i : i + batch_size]

        encoded = tokenizer(
            a_batch,
            b_batch,
            padding=True,
            truncation=True,
            max_length=settings.reranker_max_length,
            return_tensors="np",
        )

        feed = {
            "input_ids": encoded["input_ids"].astype(np.int64),
            "attention_mask": encoded["attention_mask"].astype(np.int64),
        }
        if "token_type_ids" in input_names and "token_type_ids" in encoded:
            feed["token_type_ids"] = encoded["token_type_ids"].astype(np.int64)

        logits = session.run(None, feed)[0]  # shape: [batch, 1] 또는 [batch, 2]

        if logits.ndim == 2 and logits.shape[-1] >= 2:
            batch_scores = logits[:, 1].tolist()
        else:
            batch_scores = logits.reshape(-1).tolist()

        all_scores.extend(batch_scores)

    return all_scores


@lru_cache(maxsize=1)
def _get_reranker_components():
    """ONNX 세션 + 토크나이저 singleton 로드."""
    import onnxruntime as ort
    from huggingface_hub import hf_hub_download
    from transformers import AutoTokenizer

    from app.core.config import get_settings

    settings = get_settings()
    logger.info(
        f"[Reranker] loading ONNX model "
        f"repo='{settings.reranker_model_name}' "
        f"file='{settings.reranker_onnx_filename}'"
    )

    onnx_path = hf_hub_download(
        repo_id=settings.reranker_model_name,
        filename=settings.reranker_onnx_filename,
    )
    session = ort.InferenceSession(
        onnx_path,
        providers=["CPUExecutionProvider"],
    )
    tokenizer = AutoTokenizer.from_pretrained(settings.reranker_model_name)

    logger.info("[Reranker] ONNX model loaded successfully")
    return session, tokenizer


def _get_content(doc) -> str:
    """LangChain Document 또는 직렬화된 dict 양쪽에서 텍스트 추출."""
    if hasattr(doc, "page_content"):
        return doc.page_content
    if isinstance(doc, dict):
        return doc.get("content", "")
    return str(doc)


def _get_metadata(doc) -> dict:
    """LangChain Document 또는 직렬화된 dict 양쪽에서 메타데이터 추출."""
    if hasattr(doc, "metadata"):
        return dict(doc.metadata or {})
    if isinstance(doc, dict):
        return doc.get("metadata", {})
    return {}
