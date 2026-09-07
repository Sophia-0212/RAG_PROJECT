# Findings and Architecture Decisions

## Current Evidence
- `RAGService.query()` always calls `graph.invoke(inputs, config)` and has no request-run repository, stale-run scan, or `invoke(None)` recovery path.
- `RAGService.stream()` similarly starts with normal input; closing the stream releases the Redis conversation lease but does not persist an explicit run outcome.
- `thread_id` is derived from tenant + conversation, so every turn currently shares one checkpoint namespace.
- `rag_conversations` stores owner, thread, summary, update time, and expiry only. It cannot identify unfinished requests or elect a recovery owner.
- Redis coordination serializes live access to a conversation but is intentionally ephemeral; it is not a durable work queue or run ledger.
- Current tests prove completed checkpoint persistence and cross-pool visibility, not recovery after an abrupt process death.

## Pinned LangGraph Experiment
Using the repository's installed version and a graph `START -> a -> b -> END` where `b` fails:

| Second call | Observed nodes | Meaning |
| --- | --- | --- |
| `invoke(original_input, same_thread)` | `a`, then `b` | Loads thread state but begins a new graph input/run from START |
| `invoke(None, same_thread)` | only `b` | Resumes the pending task from its checkpoint boundary |

The same experiment against Graph 2 failed at `direct_answer`:

- After failure: `snapshot.next == ('direct_answer',)`, `step_count == 1`.
- Same dict input reran `route_question` and `direct_answer`, ending at `step_count == 3`.
- `invoke(None)` ran only `direct_answer`, ending at `step_count == 2`.

Therefore automatic recovery must deliberately inspect the snapshot and call `invoke(None)`. Reusing a `thread_id` with ordinary input is not an adequate recovery algorithm.

## Architectural Interpretation
There are three separate capabilities:

1. Conversation memory: bounded summary and prior thread state inform a new user turn.
2. Checkpoint fault tolerance: persisted supersteps and pending tasks make a specific run technically resumable.
3. Operational recovery: a durable run ledger, ownership lease, scheduler, result store, and client contract ensure somebody actually resumes the run.

The repository currently has capabilities 1 and the storage foundation for 2. The planned work adds capability 3 and hardens 2.

## Important Correctness Boundaries
- Resume starts a failed node from the beginning, not from an arbitrary Python line.
- A process can die after an external call but before its node checkpoint, so node execution is at least once.
- Conversation Redis lease and request execution lease solve different problems and both are required.
- A recovered result needs durable storage because the original HTTP connection no longer exists.
- The current absolute graph deadline must not simply be reused after a delayed restart.
- Recovery must preserve request ordering within a conversation and must not resume with stale authorization.
- PostgreSQL is the production checkpoint backend; references to reading a SQLite checkpoint table apply only to local mode.

## Recommended File Impact
- New: `rag_service/run_store.py`, `rag_service/recovery.py`, `rag_service/recovery_worker.py`.
- Modify: `rag_service/service.py`, `api.py`, `api_models.py`, `application.py`, `conversation.py`, `migrations.py`, `settings.py`, `telemetry.py`.
- Deploy: add recovery-worker resources to `deploy/k8s/`, update Compose integration and CI.
- Tests: new run-store/recovery unit tests and subprocess-kill scenarios in `tests/integration/`.
- Docs: README, external contract, deployment, operations, incident, evidence index, and impacted simulation documents.

## Implemented Result
- LangGraph 1.2.11 does not support using an arbitrary non-empty top-level `checkpoint_ns` for this purpose; it treats that namespace as a subgraph path. The implementation therefore uses a tenant/conversation/request-derived `thread_id` and records the conversation association in PostgreSQL.
- `RAGService` persists the run before execution, uses `durability="sync"`, resumes pending work with `invoke(None)`, and finalizes a completed snapshot without invoking graph nodes again.
- PostgreSQL is the durable queue and ownership source. Redis remains the conversation-ordering and quota dependency; it is not used as a recovery ledger.
- Result, idempotent conversation turn, and summary update share one fenced PostgreSQL transaction.
- IAM 401/403 or identity mismatch is terminal denial. Timeout, invalid transport, or service failure is retryable unavailability. Neither path executes the graph.
- Retry exhaustion is `FAILED_TERMINAL/MAX_ATTEMPTS_EXCEEDED`; window exhaustion is `EXPIRED/RECOVERY_EXPIRED`.
- Local real-dependency verification passes 10 PostgreSQL/Redis integration cases. Production capability remains conditional on target-cluster fault and load evidence.
