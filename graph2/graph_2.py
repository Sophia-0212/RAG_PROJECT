from __future__ import annotations

from collections.abc import Callable, Mapping
import time
from typing import Any

from langgraph.constants import END, START
from langgraph.graph import StateGraph

from graph2.direct_answer_node import direct_answer
from graph2.generate_node2 import generate
from graph2.grade_answer_chain import get_answer_grader_chain
from graph2.grade_documents_node import grade_documents
from graph2.grade_hallucinations_chain import get_hallucination_grader_chain
from graph2.graph_state2 import GraphState
from graph2.query_route_chain import get_question_router_chain
from graph2.retriever_node import retrieve
from graph2.transform_query_node import transform_query
from graph2.web_search_node import web_search
from rag_service.answer import AnswerResult
from rag_service.execution import (
    Action,
    ExecutionLimits,
    FailureReason,
    begin_action,
    budget_failure,
    initialize_execution,
    record_candidates,
    record_query,
    record_token_usage,
    terminal_reason,
)
from rag_service.resilience import DependencyGuard
from rag_service.telemetry import RAGTelemetry, hash_identifier
from utils.log_utils import log


MAX_HALLUCINATION_RETRIES = 2
Node = Callable[[dict[str, Any]], dict[str, Any]]


def grade_generation_v_documents_and_question(
    state,
    hallucination_grader=None,
    answer_grader=None,
):
    """Compatibility policy used by existing callers and focused unit tests."""
    grade = evaluate_generation(
        state,
        hallucination_grader=hallucination_grader,
        answer_grader=answer_grader,
    )["generation_grade"]
    if grade == "useful":
        return "useful"
    if grade == "not_useful":
        return "not useful"
    if int(state.get("hallucination_count", 0)) >= MAX_HALLUCINATION_RETRIES:
        return "not supported exhausted"
    return "not supported"


def evaluate_generation(state, hallucination_grader=None, answer_grader=None):
    log.info("---检查生成内容是否存在幻觉---")
    hallucination_grader = hallucination_grader or get_hallucination_grader_chain()
    grounding = hallucination_grader.invoke(
        {"documents": state.get("documents", []), "generation": state.get("generation", "")}
    )
    if grounding.binary_score != "yes":
        return {"generation_grade": "not_supported"}

    answer_grader = answer_grader or get_answer_grader_chain()
    usefulness = answer_grader.invoke(
        {"question": state["question"], "generation": state.get("generation", "")}
    )
    return {"generation_grade": "useful" if usefulness.binary_score == "yes" else "not_useful"}


def decide_to_generate(state):
    """Choose the next evidence action without permitting an unbounded cycle."""
    if state.get("failure_reason"):
        return "terminate"
    if state.get("documents"):
        return "generate" if budget_failure(state, action=Action.GENERATE) is None else "terminate"
    if state.get("retrieval_repeated"):
        return "terminate"
    policy_state = state
    if "query_transform_attempts" not in state and "transform_count" in state:
        policy_state = {**state, "query_transform_attempts": state["transform_count"]}
    if budget_failure(policy_state, action=Action.TRANSFORM_QUERY) is None:
        return "transform_query"
    if (
        state.get("evidence_source") != "web_search"
        and budget_failure(state, action=Action.WEB_SEARCH) is None
    ):
        return "web_search"
    return "terminate"


def route_question(state, router_chain=None):
    """Route a question to web search, vector retrieval, or direct generation."""
    router_chain = router_chain or get_question_router_chain()
    source = router_chain.invoke({"question": state["question"]})
    route = str(source.datasource)
    if route not in {"web_search", "vectorstore", "direct_answer"}:
        return "terminate"
    return route


def _run_action(
    state: dict[str, Any],
    action: Action,
    node: Node,
    *,
    guard: DependencyGuard | None = None,
    telemetry: RAGTelemetry | None = None,
) -> dict[str, Any]:
    allowed, bookkeeping = begin_action(state, action)
    if not allowed:
        return bookkeeping
    working_state = {**state, **bookkeeping}
    started = time.perf_counter()
    try:
        result = guard.call(lambda: node(working_state)) if guard else node(working_state)
    except Exception:
        if telemetry:
            telemetry.observe_action(
                action=action.value,
                outcome="error",
                elapsed_seconds=time.perf_counter() - started,
            )
        raise
    if telemetry:
        elapsed = time.perf_counter() - started
        candidates = result.get("candidates") or []
        telemetry.observe_action(action=action.value, outcome="success", elapsed_seconds=elapsed)
        context = state.get("request_context") or {}
        telemetry.trace(
            "graph_action_completed",
            {
                "request_id": context.get("request_id", ""),
                "tenant_hash": hash_identifier(str(context.get("tenant_id", ""))),
                "action": action.value,
                "outcome": "success",
                "elapsed_ms": round(elapsed * 1000, 3),
                "step_count": bookkeeping["step_count"],
                "candidate_ids": [candidate.chunk_id for candidate in candidates[:20]],
                "candidate_scores": [
                    candidate.rerank_score if candidate.rerank_score is not None else candidate.fused_score
                    for candidate in candidates[:20]
                ],
            },
        )
    return {**bookkeeping, **result}


def _run_retrieval(
    state: dict[str, Any],
    node: Node,
    *,
    guard: DependencyGuard | None = None,
    telemetry: RAGTelemetry | None = None,
) -> dict[str, Any]:
    result = _run_action(state, Action.RETRIEVE, node, guard=guard, telemetry=telemetry)
    if result.get("failure_reason"):
        return result
    merged = {**state, **result}
    return {
        **result,
        **record_candidates(state, merged.get("candidates", [])),
        "evidence_source": "vectorstore",
    }


def _run_transform(
    state: dict[str, Any],
    node: Node,
    *,
    guard: DependencyGuard | None = None,
    telemetry: RAGTelemetry | None = None,
) -> dict[str, Any]:
    result = _run_action(state, Action.TRANSFORM_QUERY, node, guard=guard, telemetry=telemetry)
    if result.get("failure_reason"):
        return result
    return {**result, **record_query(state, str(result.get("question", "")))}


def _run_generation(
    state: dict[str, Any],
    node: Node,
    *,
    action: Action = Action.GENERATE,
    guard: DependencyGuard | None = None,
    telemetry: RAGTelemetry | None = None,
) -> dict[str, Any]:
    result = _run_action(state, action, node, guard=guard, telemetry=telemetry)
    if result.get("failure_reason"):
        return result
    merged = {**state, **result}
    context_pack = merged.get("context_pack")
    context_tokens = int(getattr(context_pack, "token_count", 0))
    usage = record_token_usage(
        merged,
        str(merged.get("question", "")),
        str(merged.get("generation", "")),
        additional_tokens=context_tokens,
    )
    return {**result, **usage}


def _initialize_node(limits: ExecutionLimits, component_versions: Mapping[str, str]) -> Node:
    return lambda state: initialize_execution(
        state,
        limits,
        component_versions=component_versions,
    )


def _route_node(router_chain=None, guard=None, telemetry=None) -> Node:
    def run(state):
        allowed, bookkeeping = begin_action(state, Action.ROUTE)
        if not allowed:
            return bookkeeping
        started = time.perf_counter()
        operation = lambda: route_question({**state, **bookkeeping}, router_chain=router_chain)
        try:
            route = guard.call(operation) if guard else operation()
        except Exception:
            if telemetry:
                telemetry.observe_action(
                    action=Action.ROUTE.value,
                    outcome="error",
                    elapsed_seconds=time.perf_counter() - started,
                )
            raise
        if telemetry:
            telemetry.observe_action(
                action=Action.ROUTE.value,
                outcome="success",
                elapsed_seconds=time.perf_counter() - started,
            )
        return {
            **bookkeeping,
            "question_route": route,
            "route_supported": route != "terminate",
        }

    return run


def _generation_grader_node(hallucination_grader=None, answer_grader=None) -> Node:
    def run(state):
        return evaluate_generation(
            state,
            hallucination_grader=hallucination_grader,
            answer_grader=answer_grader,
        )

    return run


def _route_after_question(state):
    if state.get("failure_reason"):
        return "terminate"
    return state.get("question_route", "terminate")


def _route_after_retrieval(state):
    return "terminate" if state.get("failure_reason") else "grade_documents"


def _route_after_web_search(state):
    if state.get("failure_reason") or not state.get("documents"):
        return "terminate"
    return "generate" if budget_failure(state, action=Action.GENERATE) is None else "terminate"


def _route_after_transform(state):
    if state.get("failure_reason"):
        return "terminate"
    return "retrieve" if budget_failure(state, action=Action.RETRIEVE) is None else "terminate"


def _route_after_generation(state):
    return "terminate" if state.get("failure_reason") else "grade_generation"


def _route_after_generation_grade(state):
    if state.get("failure_reason"):
        return "terminate"
    grade = state.get("generation_grade")
    if grade == "useful":
        return "end"
    if grade == "not_supported" and budget_failure(state, action=Action.GENERATE) is None:
        return "generate"
    if (
        grade == "not_useful"
        and state.get("evidence_source") == "vectorstore"
        and budget_failure(state, action=Action.TRANSFORM_QUERY) is None
        and budget_failure(state, action=Action.RETRIEVE) is None
    ):
        return "transform_query"
    return "terminate"


def terminate(state):
    reason = terminal_reason(state)
    messages = {
        FailureReason.DEADLINE_EXCEEDED: "请求处理已超过时间限制，请稍后重试。",
        FailureReason.NO_PROGRESS: "多次检索未获得新的有效证据，请补充更具体的信息。",
        FailureReason.CLARIFICATION_REQUIRED: "当前问题缺少明确指代，请补充具体对象或业务场景。",
        FailureReason.INVALID_REQUEST_CONTEXT: "请求缺少有效的身份或租户上下文。",
        FailureReason.INSUFFICIENT_EVIDENCE: "当前授权范围内没有足够证据回答该问题。",
        FailureReason.GROUNDING_FAILED: "生成结果无法由当前证据可靠支持。",
        FailureReason.ANSWER_NOT_USEFUL: "当前证据不足以形成有效回答，请补充问题细节。",
    }
    answer = messages.get(reason, "请求已达到处理预算，未生成可验证的回答。")
    result = AnswerResult(
        answer=answer,
        refusal_reason=reason.value,
        degraded=bool(state.get("retrieval_degraded", False)),
    )
    return {
        "generation": answer,
        "answer_result": result.to_dict(),
        "failure_reason": reason.value,
    }


def build_graph(
    *,
    checkpointer=None,
    limits: ExecutionLimits | None = None,
    node_overrides: Mapping[str, Node] | None = None,
    router_chain=None,
    hallucination_grader=None,
    answer_grader=None,
    component_versions: Mapping[str, str] | None = None,
    dependency_guards: Mapping[str, DependencyGuard] | None = None,
    telemetry: RAGTelemetry | None = None,
):
    """Compile the canonical bounded Graph 2 workflow."""
    active_limits = limits or ExecutionLimits.from_settings()
    nodes = dict(node_overrides or {})
    retrieve_node = nodes.get("retrieve", retrieve)
    grade_documents_node = nodes.get("grade_documents", grade_documents)
    generate_node = nodes.get("generate", generate)
    transform_node = nodes.get("transform_query", transform_query)
    web_node = nodes.get("web_search", web_search)
    direct_node = nodes.get("direct_answer", direct_answer)
    generation_grader_node = nodes.get(
        "grade_generation",
        _generation_grader_node(hallucination_grader, answer_grader),
    )

    versions = dict(component_versions or {"graph": "graph2-bounded-v1"})
    guards = dict(dependency_guards or {})
    llm_guard = guards.get("llm")
    workflow = StateGraph(GraphState)
    workflow.add_node("initialize", _initialize_node(active_limits, versions))
    workflow.add_node("route_question", _route_node(router_chain, llm_guard, telemetry))
    workflow.add_node("web_search", lambda state: {
        **_run_action(
            state,
            Action.WEB_SEARCH,
            web_node,
            guard=guards.get("web_search"),
            telemetry=telemetry,
        ),
        "evidence_source": "web_search",
    })
    workflow.add_node(
        "retrieve",
        lambda state: _run_retrieval(
            state,
            retrieve_node,
            guard=guards.get("retrieval"),
            telemetry=telemetry,
        ),
    )
    workflow.add_node(
        "grade_documents",
        lambda state: _run_action(
            state,
            Action.GRADE_DOCUMENTS,
            grade_documents_node,
            guard=llm_guard,
            telemetry=telemetry,
        ),
    )
    workflow.add_node(
        "generate",
        lambda state: _run_generation(
            state,
            generate_node,
            guard=llm_guard,
            telemetry=telemetry,
        ),
    )
    workflow.add_node(
        "transform_query",
        lambda state: _run_transform(
            state,
            transform_node,
            guard=llm_guard,
            telemetry=telemetry,
        ),
    )
    workflow.add_node(
        "grade_generation",
        lambda state: _run_action(
            state,
            Action.GRADE_GENERATION,
            generation_grader_node,
            guard=llm_guard,
            telemetry=telemetry,
        ),
    )
    workflow.add_node(
        "direct_answer",
        lambda state: _run_generation(
            state,
            direct_node,
            action=Action.DIRECT_ANSWER,
            guard=llm_guard,
            telemetry=telemetry,
        ),
    )
    workflow.add_node("terminate", terminate)

    workflow.add_edge(START, "initialize")
    workflow.add_edge("initialize", "route_question")
    workflow.add_conditional_edges(
        "route_question",
        _route_after_question,
        {
            "web_search": "web_search",
            "vectorstore": "retrieve",
            "direct_answer": "direct_answer",
            "terminate": "terminate",
        },
    )
    workflow.add_conditional_edges(
        "web_search",
        _route_after_web_search,
        {"generate": "generate", "terminate": "terminate"},
    )
    workflow.add_conditional_edges(
        "retrieve",
        _route_after_retrieval,
        {"grade_documents": "grade_documents", "terminate": "terminate"},
    )
    workflow.add_conditional_edges(
        "grade_documents",
        decide_to_generate,
        {
            "generate": "generate",
            "transform_query": "transform_query",
            "web_search": "web_search",
            "terminate": "terminate",
        },
    )
    workflow.add_conditional_edges(
        "transform_query",
        _route_after_transform,
        {"retrieve": "retrieve", "terminate": "terminate"},
    )
    workflow.add_conditional_edges(
        "generate",
        _route_after_generation,
        {"grade_generation": "grade_generation", "terminate": "terminate"},
    )
    workflow.add_conditional_edges(
        "grade_generation",
        _route_after_generation_grade,
        {"generate": "generate", "transform_query": "transform_query", "terminate": "terminate", "end": END},
    )
    workflow.add_conditional_edges(
        "direct_answer",
        lambda state: "terminate" if state.get("failure_reason") else "end",
        {"terminate": "terminate", "end": END},
    )
    workflow.add_edge("terminate", END)
    return workflow.compile(checkpointer=checkpointer)


def run_cli(
    graph=None,
    *,
    tenant_id: str,
    user_id: str,
    principal_ids: tuple[str, ...] = (),
    conversation_id: str | None = None,
    conversation_store=None,
    settings=None,
) -> None:
    """Run the local interactive client with one stable conversation thread."""
    from pprint import pprint
    from uuid import uuid4

    from langfuse.langchain import CallbackHandler

    compiled_graph = graph or build_graph()
    conversation_id = conversation_id or str(uuid4())
    while True:
        question = input("用户：")
        if question.lower() in {"q", "exit", "quit"}:
            print("对话结束，拜拜！")
            break

        request_id = str(uuid4())
        record = None
        if conversation_store is not None:
            record = conversation_store.claim(
                conversation_id,
                tenant_id=tenant_id,
                user_id=user_id,
                ttl_seconds=settings.conversation_ttl_seconds,
            )
        handler = CallbackHandler()
        config = {
            "callbacks": [handler],
            "configurable": {"thread_id": record.thread_id if record else conversation_id},
            "metadata": {"langfuse_session_id": conversation_id, "langfuse_tags": ["graph2"]},
        }
        inputs = {
            "question": question,
            "conversation_summary": record.summary if record else "",
            "request_context": {
                "request_id": request_id,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "principal_ids": principal_ids,
            },
        }
        final_generation = None
        for output in compiled_graph.stream(inputs, config=config):
            for key, value in output.items():
                pprint(f"Node '{key}':")
                final_generation = value.get("generation", final_generation)
            pprint("\n---\n")
        if final_generation is not None:
            pprint(final_generation)
            if conversation_store is not None:
                conversation_store.append_turn(
                    conversation_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    question=question,
                    answer=str(final_generation),
                    ttl_seconds=settings.conversation_ttl_seconds,
                    max_chars=settings.conversation_summary_max_chars,
                )


if __name__ == "__main__":
    from rag_service.cli import main

    main()
