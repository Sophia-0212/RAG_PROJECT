# RAG Enterprise Service

CRM domain RAG core built around LangGraph, Milvus hybrid retrieval, and a CrossEncoder reranker.
Graph 2 is the canonical workflow. Graph 1 and `agent/rag_agent.py` remain legacy comparison examples.

## Current scope

The repository provides engineering and evaluation baselines, governed ingestion, tenant-safe retrieval, structured
citations, bounded Graph 2 execution, durable local conversation state, a versioned HTTP API, redacted telemetry,
reliability controls, and a hardened single-instance deployment baseline. Shared multi-instance checkpoint storage
and target-environment production evidence remain explicit follow-up work.

## Environment

Python 3.11 is required. Create an isolated environment and install the pinned direct dependencies:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
cp .env.example .env
```

Fill only the credentials required by the runtime paths you use. Configuration is loaded lazily, so imports and
offline tests do not require API keys, a running Milvus instance, or downloaded model weights.

Important variables:

- `OPENAI_API_KEY`, `RAG_LLM_MODEL`, `RAG_LLM_BASE_URL`: chat model gateway.
- `MILVUS_URI`, `RAG_COLLECTION_NAME`: vector database target.
- `RAG_RETRIEVAL_TOP_K`, `RAG_RERANK_TOP_N`, `RAG_RRF_K`: retrieval controls.
- `RAG_FUSION_MODE`, `RAG_DENSE_WEIGHT`, `RAG_SPARSE_WEIGHT`: RRF or weighted hybrid fusion.
- `RAG_RERANK_TIMEOUT_SECONDS`, `RAG_CONTEXT_MAX_TOKENS`: rerank fallback and context limits.
- `RAG_MAX_*`, `RAG_REQUEST_TIMEOUT_SECONDS`: per-request graph budgets and deadline.
- `RAG_CHECKPOINT_PATH`, `RAG_CONVERSATION_TTL_SECONDS`: durable local state and expiry.
- `TAVILY_API_KEY`: optional web-search route.
- `LANGFUSE_*`: optional tracing stack.
- `RAG_GATEWAY_SHARED_SECRET`: production gateway bearer secret, at least 32 characters.
- `RAG_MODEL_CACHE_PATH`: absolute production host path containing the reviewed reranker cache.

## Local commands

Run the canonical interactive workflow:

```bash
.venv/bin/python main.py --tenant crm-demo --user alice --principal group:sales
```

Run the HTTP service (SQLite mode is intentionally limited to one worker):

```bash
.venv/bin/python -m rag_service.api_cli --host 127.0.0.1 --port 8000
```

Run all offline checks:

```bash
.venv/bin/python -m compileall -q agent documents evaluation graph graph2 llm_models rag_service tools utils main.py
.venv/bin/python -m unittest discover -s tests -v
```

Generate a measured load report against a running service:

```bash
.venv/bin/python -m evaluation.load_test \
  --tenant crm-demo --user load-runner --requests 100 --concurrency 8 \
  --output .rag-state/load-report.json
```

## Evaluation baseline

The versioned smoke set is `evaluation/datasets/crm_smoke_v1.jsonl`. It records questions, expected source IDs,
answer facts, routing expectations, refusal cases, and tags. `evaluation/metrics.py` contains deterministic
retrieval, ranking, citation, and ACL-leakage metrics.

An evaluation runner should write a JSON object containing the metrics referenced by
`evaluation/release_gate.json`. Apply the release gate with:

```bash
.venv/bin/python -m evaluation.cli path/to/metrics.json
```

The initial thresholds are explicit starting gates, not claimed production results. They must be recalibrated
from the versioned dataset, retrieval experiments, security tests, and load evidence as later modules land.

## Governed Markdown ingestion

The governed ingestion path assigns stable source/document/chunk IDs and creates a new version whenever content,
ACL, visibility, title, or effective time changes. Manifests and operation checkpoints make unchanged runs cheap and
allow interrupted writes to resume without replaying completed operations.

Run an incremental authoritative snapshot into the configured collection:

```bash
.venv/bin/python -m documents.ingest_markdown datas/md \
  --tenant crm-demo \
  --acl group:sales \
  --run-id crm-demo-20260904-001
```

Build a separate collection and switch an alias only after the full snapshot succeeds:

```bash
.venv/bin/python -m documents.ingest_markdown datas/md \
  --tenant crm-demo \
  --acl group:sales \
  --run-id crm-demo-release-20260904 \
  --collection-version 20260904 \
  --activate-alias rag_active
```

Runtime state is stored under `.rag-state/` and is intentionally ignored by Git. Reuse a `run-id` only to resume
the exact same plan. Alias rollback is guarded by the collection observed at activation time so a stale operator
cannot overwrite a newer release.

## Runtime boundaries

- `rag_service.settings`: typed environment configuration and validation.
- `rag_service.application.create_graph()`: canonical application factory.
- `rag_service.application.create_runtime()`: durable local graph/checkpoint/conversation composition.
- `graph2`: current production-direction workflow.
- `documents`: governed source contracts, change planning, checkpoints, Markdown parsing, and Milvus ingestion.
- `evaluation`: versioned datasets, metrics, and release gating.
- `tests`: deterministic offline tests; this directory is separate from the historical `test/recall_eval` worktree.

## Retrieval security and answer contract

Every Graph 2 retrieval request requires `request_id`, `tenant_id`, `user_id`, and caller principals. Milvus applies
tenant, active-status, effective-time, source/version constraints, and public-or-ACL filters before ANN search.
The service then repeats authorization in memory; legacy rows without governed fields fail closed.

Hybrid recall preserves its fused score. CrossEncoder output is stored separately as `rerank_score`; timeout or model
failure falls back to recall order and records a degradation reason. Parent chunks are resolved with the same security
filter and rechecked before context construction.

Generation uses a bounded context with stable `[S1]` labels. Graph state exposes `answer_result` with exact source,
document, version, and chunk IDs for citations. A request with no authorized evidence returns
`INSUFFICIENT_AUTHORIZED_EVIDENCE` without invoking the LLM. Current numeric fusion weights, score threshold, timeout,
and context size are configuration defaults and still require calibration against the versioned evaluation set.

`documents/write_milvus.py` is a legacy bulk loader. Its `create_collection()` call is now non-destructive, but new
automation should use `documents.ingest_markdown` so identity, ACL metadata, manifests, and checkpoints are present.

## Bounded workflow and conversations

Graph 2 tracks the immutable original query, rewritten-query history, candidate fingerprints, component versions,
steps, retrieval/generation/rewrite/web attempts, estimated tokens, and an absolute request deadline. Every retry path
either stays within those limits or enters the `terminate` node with a stable reason code such as `NO_PROGRESS`,
`GROUNDING_FAILED`, or `TOKEN_BUDGET_EXCEEDED`. A pronoun-only follow-up without conversation context requests
clarification instead of guessing.

The CLI uses a tenant-scoped hashed thread ID and SQLite checkpoints under `.rag-state/`. Conversation metadata binds
the external conversation ID to one tenant and user, stores a bounded rolling summary, and removes expired graph
threads during runtime startup. Checkpoint deserialization uses an explicit allowlist. SQLite is intended for local or
lightweight single-process operation; a multi-instance deployment must supply a shared production checkpointer.

Use `--conversation` to resume an existing local conversation after a process restart:

```bash
.venv/bin/python main.py --tenant crm-demo --user alice --conversation support-case-42
```

## HTTP and integration contracts

The OpenAPI document is available at `/openapi.json`. `POST /v1/query` returns a validated answer contract;
`POST /v1/query/stream` emits `progress`, `answer`, and `done` SSE events without exposing raw retrieved documents.
Conversation metadata can be read or deleted through `/v1/conversations/{conversation_id}`. Liveness and readiness
are separate at `/health/live` and `/health/ready`.

Development requests require `X-Tenant-ID` and `X-User-ID`; `X-Principal-ID` may be repeated or comma-separated.
`X-Request-ID` is validated and echoed, or generated when absent. The built-in trusted-header identity provider is
disabled outside development/test profiles, so production readiness requires an injected IAM verifier. See
`docs/external-contracts.md` for ownership and retry boundaries.

## Reliability and observability

`/metrics` exposes low-cardinality Prometheus counters, histograms, and in-flight gauges. Structured trace events use
an allowlist: they include hashed identity keys, request IDs, action latency, candidate IDs/scores, cited chunk IDs,
budgets, and component versions, but exclude question text, document content, prompts, credentials, and conversation
summaries. See `docs/operations.md` for the failure matrix and measurement workflow.

Per-tenant token buckets and a global concurrency semaphore reject overload before Graph execution. Read-only/model
nodes use bounded retry with jitter and dependency circuit breakers. Reranker timeout, error, or open circuit falls
back to recall order and marks the response degraded. These values are protective defaults, not production SLOs;
capacity and alert thresholds must come from versioned reports generated in the target environment.

## Deployment and evidence

The production image is pinned to a base-image digest and runs as UID/GID `10001` with one worker. It uses
`requirements.service.lock` and the official CPU-only PyTorch wheel source; ingestion-only parser dependencies stay
outside the query image. The remote-Milvus production profile also omits the adapter's unused `milvus-lite` extra.
The Compose baseline uses a read-only root filesystem, drops Linux capabilities, requires
runtime secrets, persists SQLite state, and mounts the reviewed Hugging Face model cache read-only. Validate it using
`docs/deployment-runbook.md`; use `docs/incident-runbook.md` during incidents.

`docs/evidence-index.md` maps each enterprise capability to implementation and test evidence and lists the live
environment work that is still required. The Langfuse Compose file is a local-development stack, not the production
RAG deployment.
