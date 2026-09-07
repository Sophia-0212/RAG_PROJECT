from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from typing import TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from evaluation.performance import LoadSample, summarize_load
from rag_service.checkpointing import create_checkpointer
from rag_service.conversation import create_conversation_store
from rag_service.coordination import create_coordination
from rag_service.settings import get_settings


class StateProbe(TypedDict):
    steps: int


def _build_probe_graph(checkpointer, step_count: int):
    builder = StateGraph(StateProbe)
    previous = START
    for index in range(step_count):
        name = f"state_write_{index + 1}"
        builder.add_node(name, lambda state: {"steps": state["steps"] + 1})
        builder.add_edge(previous, name)
        previous = name
    builder.add_edge(previous, END)
    return builder.compile(checkpointer=checkpointer)


def _probe_once(graph, conversations, coordinator, sequence: int) -> LoadSample:
    started = time.perf_counter()
    conversation_id = f"state-load-{uuid4()}"
    tenant_id = f"load-tenant-{sequence % 18}"
    thread_id = f"state-load-thread-{uuid4()}"
    try:
        with coordinator.slot(thread_id):
            conversations.claim(
                conversation_id,
                tenant_id=tenant_id,
                user_id="state-load-runner",
                ttl_seconds=3600,
            )
            result = graph.invoke(
                {"steps": 0},
                config={"configurable": {"thread_id": thread_id}},
            )
            conversations.append_turn(
                conversation_id,
                tenant_id=tenant_id,
                user_id="state-load-runner",
                question="state load probe",
                answer=f"completed {result['steps']} steps",
                ttl_seconds=3600,
                max_chars=256,
            )
        return LoadSample(status_code=200, latency_ms=(time.perf_counter() - started) * 1000)
    except Exception as exc:
        return LoadSample(
            status_code=0,
            latency_ms=(time.perf_counter() - started) * 1000,
            error_code=type(exc).__name__,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure the shared PostgreSQL/Redis RAG state path")
    parser.add_argument("--requests", type=int, default=540)
    parser.add_argument("--qps", type=float, default=9.0)
    parser.add_argument("--concurrency", type=int, default=36)
    parser.add_argument("--graph-steps", type=int, default=8)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if min(args.requests, args.qps, args.concurrency, args.graph_steps) <= 0:
        parser.error("requests, qps, concurrency, and graph-steps must be positive")

    settings = get_settings()
    if settings.state_backend != "postgres":
        parser.error("state load testing requires RAG_STATE_BACKEND=postgres")
    checkpoints = create_checkpointer(settings)
    conversations = create_conversation_store(settings, checkpoints)
    coordinator, _quota = create_coordination(settings)
    graph = _build_probe_graph(checkpoints.saver, args.graph_steps)
    started = time.perf_counter()
    try:
        with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
            futures = []
            for sequence in range(args.requests):
                target = started + sequence / args.qps
                delay = target - time.perf_counter()
                if delay > 0:
                    time.sleep(delay)
                futures.append(executor.submit(_probe_once, graph, conversations, coordinator, sequence))
            samples = [future.result() for future in futures]
    finally:
        conversations.close()
        coordinator.close()
        checkpoints.close()

    report = summarize_load(samples, elapsed_seconds=time.perf_counter() - started)
    report.update(
        {
            "schema_version": "rag-state-load-report-v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "configured_qps": args.qps,
            "configured_concurrency": args.concurrency,
            "graph_steps": args.graph_steps,
            "state_backend": settings.state_backend,
            "component_versions": {
                "langgraph": version("langgraph"),
                "langgraph-checkpoint-postgres": version("langgraph-checkpoint-postgres"),
                "psycopg": version("psycopg"),
                "redis": version("redis"),
            },
        }
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "samples"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
