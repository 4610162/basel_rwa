"""
LangGraph 워크플로 조립 — Basel III Agent Graph

워크플로:
    START
      → normalize_node
      → classification_node
      → [conditional] regulation_only       → regulation_node → answer_node → END
                       calculation_only     → calculation_node → answer_node → END
                       regulation_plus_calc → regulation_node → calculation_node → answer_node → END
                       clarification_needed → answer_node → END

※ reasoning은 answer_node 프롬프트 내부에 Step 1~5로 통합됨 (별도 LLM 호출 없음)
"""
from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, StateGraph

from app.graph.state import GraphState
from app.graph.utils import normalize_question_text
from app.graph.nodes.classification_agent import classification_node
from app.graph.nodes.regulation_agent import regulation_node
from app.graph.nodes.calculation_agent import calculation_node
from app.graph.nodes.answer_agent import answer_node


# ── normalize node (인라인 정의) ───────────────────────────────────────────────

def normalize_node(state: GraphState) -> dict:
    """입력 질문 정규화. 불필요한 공백·줄바꿈 제거."""
    return {"normalized_question": normalize_question_text(state.get("user_question", ""))}


# ── 라우팅 함수 ────────────────────────────────────────────────────────────────

def _route_after_classification(state: GraphState) -> str:
    """
    classification_node 이후 분기 결정.

    regulation_only           → regulation_agent
    calculation_only          → calculation_agent
    regulation_plus_calculation → regulation_agent (이후 calculation_agent로 연결)
    clarification_needed      → answer_agent
    """
    intent = state.get("intent", "regulation_only")
    if intent == "calculation_only":
        return "calculation_agent"
    if intent == "clarification_needed":
        return "answer_agent"
    # regulation_only | regulation_plus_calculation
    return "regulation_agent"


def _route_after_regulation(state: GraphState) -> str:
    """
    regulation_node 이후 분기 결정.

    regulation_plus_calculation → calculation_agent
    그 외                        → answer_agent
    """
    intent = state.get("intent", "regulation_only")
    if intent == "regulation_plus_calculation":
        return "calculation_agent"
    return "answer_agent"


def _route_after_calculation(state: GraphState) -> str:
    """calculation_node 이후 answer_agent로 이동한다."""
    return "answer_agent"


# ── 그래프 조립 ────────────────────────────────────────────────────────────────

def build_graph():
    """StateGraph를 조립하고 컴파일된 그래프를 반환한다."""
    workflow = StateGraph(GraphState)

    # 노드 등록
    workflow.add_node("normalize", normalize_node)
    workflow.add_node("classification_agent", classification_node)
    workflow.add_node("regulation_agent", regulation_node)
    workflow.add_node("calculation_agent", calculation_node)
    workflow.add_node("answer_agent", answer_node)

    # 진입점
    workflow.set_entry_point("normalize")

    # 고정 엣지
    workflow.add_edge("normalize", "classification_agent")
    workflow.add_edge("answer_agent", END)

    # 조건부 엣지: classification → 분기
    workflow.add_conditional_edges(
        "classification_agent",
        _route_after_classification,
        {
            "regulation_agent": "regulation_agent",
            "calculation_agent": "calculation_agent",
            "answer_agent": "answer_agent",
        },
    )

    # 조건부 엣지: regulation → 분기
    workflow.add_conditional_edges(
        "regulation_agent",
        _route_after_regulation,
        {
            "calculation_agent": "calculation_agent",
            "answer_agent": "answer_agent",
        },
    )

    workflow.add_conditional_edges(
        "calculation_agent",
        _route_after_calculation,
        {
            "answer_agent": "answer_agent",
        },
    )

    return workflow.compile()


@lru_cache(maxsize=1)
def get_graph():
    """컴파일된 그래프 singleton 반환."""
    return build_graph()


def build_pre_answer_graph():
    """
    answer_node를 제외하고 classify → regulate/calculate까지만 실행하는 그래프.
    /agent/stream 엔드포인트에서 Gemini 스트리밍 전 전처리용으로 사용.

    clarification_needed → END
    그 외 → regulation/calculation → END
    """
    workflow = StateGraph(GraphState)

    workflow.add_node("normalize", normalize_node)
    workflow.add_node("classification_agent", classification_node)
    workflow.add_node("regulation_agent", regulation_node)
    workflow.add_node("calculation_agent", calculation_node)

    workflow.set_entry_point("normalize")
    workflow.add_edge("normalize", "classification_agent")

    # answer_agent 자리에 END로 매핑
    workflow.add_conditional_edges(
        "classification_agent",
        _route_after_classification,
        {
            "regulation_agent": "regulation_agent",
            "calculation_agent": "calculation_agent",
            "answer_agent": END,
        },
    )

    workflow.add_conditional_edges(
        "regulation_agent",
        _route_after_regulation,
        {
            "calculation_agent": "calculation_agent",
            "answer_agent": END,
        },
    )

    workflow.add_conditional_edges(
        "calculation_agent",
        _route_after_calculation,
        {
            "answer_agent": END,
        },
    )

    return workflow.compile()


@lru_cache(maxsize=1)
def get_pre_answer_graph():
    """pre-answer 그래프 singleton 반환."""
    return build_pre_answer_graph()
