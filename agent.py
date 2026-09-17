# -*- coding: utf-8 -*-
"""라우터 · 조회 · 생성 · 가드레일을 하나의 그래프로 잇는다.

route → answer → guard → (END | answer 재시도 | escalate)
"""
import operator
from typing import Annotated, List, Optional, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from config import GUARDRAIL_RETRY
from answer import answer_with_llm, answer_with_tools
from guardrail import guardrail
from router import app as router_app
from tools import escalate_to_agent

class AgentState(TypedDict, total=False):
    """오늘 만든 파이프라인 전체가 통과하는 State."""

    question: str
    history: Annotated[list, operator.add]   # 리듀서가 붙어 있어 턴마다 덮이지 않고 쌓인다
    route: str
    confidence: float
    action: str                 # HANDLE / ASK / ANSWER / ESCALATE / OUT_OF_SCOPE
    tools: List[str]
    results: dict
    answer: str
    guardrail_ok: Optional[bool]
    attempts: int


def with_history(state: AgentState) -> str:
    """앞 턴의 발화를 맥락으로 붙이되, 지금 답해야 할 문의를 명시적으로 구분한다.

    예전에는 전부 공백으로 이어 붙였는데, 그러면 모델이 어느 것이 현재 질문인지
    몰라 앞 턴 질문에 다시 답한다. 멀티턴 재생 실험에서 "발열내의 상의만 살 수
    있어요?" → "그럼 기본 티셔츠는 한 장만 살 수 있죠?" 대화가 3/3 회 앞 질문에
    재답변했고(기본 티셔츠도 구매 불가라고 잘못 안내), 아래 형식으로 바꾸자 0/3 이 됐다.
    """
    prior = state.get("history") or []
    if not prior:
        return state["question"]
    head = "\n".join(f"- {s}" for s in prior)
    return (f"[이전 대화에서 고객이 한 말]\n{head}\n\n"
            f"[지금 답해야 할 문의]\n{state['question']}")


def node_answer(state: AgentState) -> AgentState:
    """② 조회 + ③ 생성 — 안에서 도구 호출 그래프가 한 바퀴 돈다."""
    text, results = answer_with_tools(with_history(state), state["route"])
    if results.get("get_order_status", {}).get("is_external_channel"):
        return {"action": "OUT_OF_SCOPE", "tools": list(results), "results": results}
    if not results:                       # 조회할 식별자가 없어 모델이 되물은 경우
        return {"action": "ASK", "tools": [], "results": {}, "answer": text,
                "history": [state["question"]]}
    return {"tools": list(results), "results": results, "answer": text,
            "history": [state["question"]],
            "attempts": state.get("attempts", 0) + 1}


def node_guard(state: AgentState) -> AgentState:
    """④ 가드레일 — 출처 없는 숫자가 있으면 되돌려 보낸다."""
    ok = guardrail(state["answer"], state["results"])["ok"]
    return {"guardrail_ok": ok, "action": "ANSWER" if ok else "RETRY"}


def node_escalate(state: AgentState) -> AgentState:
    """OUT_OF_SCOPE 는 매뉴얼 7.1 을 그대로 읽고 답한다 — 타 오픈마켓 주문/제조사 A/S/
    택배사 사고마다 안내 문구가 다르므로 하나의 고정 문자열로는 부족하다(§7.1).
    도구 호출은 필요 없으므로 answer_with_llm 으로 한 번만 호출해 비용을 아낀다.
    단, node_answer 에서 이미 조회를 마치고 넘어온 경우(예: get_order_status 로
    is_external_channel 을 확인한 뒤) 그 결과를 버리면 오히려 더 애매한 답이 되므로
    state["results"] 가 있으면 그대로 함께 넘긴다.
    ESCALATE(확신도 미달·가드레일 위반)는 사람에게 넘긴다는 사실 자체가 중요하므로
    고정 문구를 그대로 쓴다."""
    if state["action"] == "OUT_OF_SCOPE":
        msg = answer_with_llm(state["question"], "OTHER", tool_results=state.get("results"))
    else:
        reason = {"ESCALATE": "분류확신도미달"}.get(state["action"], "가드레일위반")
        msg = escalate_to_agent(reason, {"q": state["question"]})["message"]
    return {"answer": msg, "guardrail_ok": state.get("guardrail_ok")}


def after_route(state: AgentState) -> str:
    return "answer" if state["action"] == "HANDLE" else "escalate"


def after_answer(state: AgentState) -> str:
    return END if state["action"] == "ASK" else ("escalate"
                                                 if state["action"] == "OUT_OF_SCOPE" else "guard")


def after_guard(state: AgentState) -> str:
    """통과하면 끝. 위반이면 한 번 더 생성해 보고, 그래도 안 되면 이관한다."""
    if state["guardrail_ok"]:
        return END
    return "answer" if state.get("attempts", 0) < 2 else "escalate"


def node_route(state):
    """① 분류 — 라우터 그래프를 그대로 부른다."""
    r = router_app.invoke({"question": with_history(state)})
    return {"route": r["route"], "confidence": r["confidence"], "action": r["action"]}


def build_agent(checkpointer=None):
    g = StateGraph(AgentState)
    g.add_node("route", node_route)
    g.add_node("answer", node_answer)
    g.add_node("guard", node_guard)
    g.add_node("escalate", node_escalate)
    g.add_edge(START, "route")
    g.add_conditional_edges("route", after_route, {"answer": "answer", "escalate": "escalate"})
    g.add_conditional_edges("answer", after_answer,
                            {"guard": "guard", "escalate": "escalate", END: END})
    g.add_conditional_edges("guard", after_guard,
                            {"answer": "answer", "escalate": "escalate", END: END})
    g.add_edge("escalate", END)
    return g.compile(checkpointer=checkpointer)


agent_app = build_agent()
chat_app = build_agent(checkpointer=InMemorySaver())     # 대화용(맥락 유지)


def customer_agent(question):
    """문의 한 줄을 파이프라인에 통과시킨다."""
    out = agent_app.invoke({"question": question})
    if out["action"] == "RETRY":
        out["action"] = "ESCALATE"
    return {"question": question, **out}
