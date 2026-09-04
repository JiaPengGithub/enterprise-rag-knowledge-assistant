from typing import TypedDict

from app.services.answering import answer_question


class QueryState(TypedDict, total=False):
    question: str
    user_id: str
    response: dict


def run_query_workflow(question: str, user_id: str) -> dict:
    graph = _build_graph()
    if graph:
        result = graph.invoke({"question": question, "user_id": user_id})
        return result["response"]
    return answer_question(question, user_id)


def _build_graph():
    try:
        from langgraph.graph import END, StateGraph
    except Exception:
        return None

    def answer_node(state: QueryState) -> QueryState:
        state["response"] = answer_question(state["question"], state["user_id"])
        return state

    graph = StateGraph(QueryState)
    graph.add_node("answer", answer_node)
    graph.set_entry_point("answer")
    graph.add_edge("answer", END)
    return graph.compile()
