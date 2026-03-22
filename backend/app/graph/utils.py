"""
LangGraph 전반에서 재사용하는 순수 헬퍼.
"""
from __future__ import annotations


def normalize_question_text(question: str) -> str:
    """불필요한 공백과 줄바꿈을 제거한 질문 문자열을 반환한다."""
    return " ".join(question.strip().split())


def format_conversation_history(history: list[dict]) -> str:
    """최근 대화 히스토리를 프롬프트용 문자열로 변환한다."""
    if not history:
        return "이전 대화 없음"

    lines: list[str] = []
    for item in history:
        role = "사용자" if item.get("role") == "user" else "어시스턴트"
        content = str(item.get("content", "")).strip()
        if content:
            lines.append(f"- {role}: {content}")

    return "\n".join(lines) if lines else "이전 대화 없음"
