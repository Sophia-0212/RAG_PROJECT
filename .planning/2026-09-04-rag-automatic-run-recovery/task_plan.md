# Task Plan: RAG Automatic Run Recovery

## Goal
Turn the existing shared LangGraph checkpoint foundation into an end-to-end recoverable request system: every production query has a durable run record, stale executions can be safely claimed by another process, pending graph work resumes without replaying completed supersteps, final results and conversation memory are idempotent, and clients can retrieve a result after the original HTTP connection or Pod is lost.

## Scope and Semantics
- Preserve the current synchronous `POST /v1/query` fast path.
- Add a PostgreSQL run ledger/queue and a dedicated recovery worker; do not introduce Kafka, Celery, or another state system.
- Use one request-scoped `thread_id`, derived from tenant/conversation/request, so multiple turns cannot overwrite one another's recovery state. Keep the conversation association in the run ledger.
- First execution uses `invoke(inputs, config, durability="sync")`; a pending checkpoint resumes with `invoke(None, config, durability="sync")`.
- Delivery guarantee is at-least-once node execution with idempotent finalization. A failed node may run again from its beginning; exactly-once execution is not claimed.
- Graceful client cancellation and abrupt process failure are different: cancellation becomes `CANCELLED`; an expired execution lease becomes recoverable.
- SSE progress replay is out of scope for the first version. Recovered final results are available from a status/result endpoint.

## Next Step
Run the four crash-window Pod-kill drill, IAM revocation drill, and recovery-specific load/soak test in the target staging cluster before enabling full recovery traffic.

## Current Phase
Core implementation and local verification complete; target-cluster rollout evidence remains pending.

## Phases

### Phase 1: Recovery Contract and LangGraph Semantics
- [x] Add an ADR defining crash recovery, client retry, cancellation, ordering, and at-least-once guarantees.
- [x] Spike request-scoped `checkpoint_ns`, `invoke(None)`, `durability="sync"`, and safe per-attempt deadline refresh against the pinned LangGraph version.
- [x] Define the four crash-window outcomes: before first checkpoint, pending node, graph complete before finalization, and finalization before HTTP response.
- [x] Confirm old empty-namespace checkpoints remain readable but are not auto-recovered as new request runs.
- **Status:** complete

### Phase 2: Durable Run Ledger and Idempotent Conversation Turns
- [x] Add `rag_request_runs` with tenant/request identity, input hash/payload, thread/namespace, status, graph version, attempts, retry time, lease/fencing token, recovery expiry, result, and sanitized error category.
- [x] Add indexes for recoverable work and a partial uniqueness rule allowing only one unfinished run per conversation.
- [x] Add `rag_conversation_turns` keyed by tenant/conversation/request so a recovered completion cannot append the same turn twice.
- [x] Implement a PostgreSQL repository with transactional submit, claim, heartbeat, retry, fail, cancel, finalize, result-read, and stale-run selection operations.
- [x] Require every mutating transition to match the current fencing token so an expired worker cannot commit after takeover.
- [x] Extend schema migration and TTL cleanup for run/turn retention; keep SQLite local mode explicitly non-auto-recovering.
- **Status:** complete

### Phase 3: Recoverable Execution Core
- [x] Extract graph execution/finalization from `RAGService.query()` into one executor used by both API and recovery worker.
- [x] On first attempt, persist the run before invoking the graph and use its request-scoped thread.
- [x] On recovery, inspect the latest snapshot and verify request identity, request-scoped thread, graph/input version, and pending tasks before doing work.
- [x] If no checkpoint exists, replay the encrypted/minimal persisted input; if `snapshot.next` is non-empty, call `invoke(None)`; if the graph is complete, reconstruct and finalize without invoking nodes again.
- [x] Refresh only the per-attempt deadline on resume; never reset step, token, retrieval, generation, or rewrite budgets.
- [x] Classify retryable versus terminal failures, apply bounded exponential backoff/jitter, cap attempts, and expire old recoveries.
- [x] Finalize run result plus conversation turn/summary in one PostgreSQL transaction.
- **Status:** complete

### Phase 4: API Idempotency and Result Retrieval
- [x] Require a gateway-supplied stable `X-Request-ID`/idempotency key for production durable queries; keep development generation only as a convenience.
- [x] Treat `(tenant_id, request_id)` as the idempotency key and reject reuse with a different user, conversation, question, constraints, or payload hash.
- [x] Return the stored result for `SUCCEEDED`, `202 + Location + Retry-After` for an execution owned elsewhere, and stable terminal error contracts for failed/expired/cancelled runs.
- [x] Add an authenticated `GET /v1/requests/{request_id}` status/result endpoint scoped to the original tenant and user.
- [x] Decide and document synchronous retry behavior: the API may claim and resume an available run; otherwise it leaves recovery to the worker.
- [x] Define streaming disconnect behavior and ensure graceful generator closure marks cancellation rather than creating a false crash-recovery job.
- **Status:** complete

### Phase 5: Recovery Worker and Scheduling
- [x] Add `rag_service.recovery_worker` with bounded polling, `FOR UPDATE SKIP LOCKED` claiming, lease heartbeat/renewal, graceful SIGTERM drain, and capped concurrency.
- [x] Acquire the existing Redis conversation lease after the durable PostgreSQL run lease; PostgreSQL establishes job ownership, Redis preserves conversation ordering.
- [x] Block a newer turn while an older run in the same conversation is unfinished; expose a stable recovery-pending response instead of silently reordering turns.
- [x] Deploy two recovery-worker replicas using the existing image and model PVC, with independent resources, probes, PDB, and configurable recovery concurrency.
- [x] Ensure worker shutdown stops claiming new work and lets its lease expire or records retryable state for safe takeover.
- **Status:** complete

### Phase 6: Security, Versioning, and Side-Effect Boundaries
- [x] Store only the minimum recoverable payload, apply the same retention/data classification as checkpoints, prevent it from logs/metrics, and rely on approved database encryption at rest.
- [x] Add an injectable recovery identity resolver that refreshes principals/policy before delayed retrieval; production recovery fails closed and distinguishes denial from unavailability.
- [x] Persist graph/input schema/component versions and refuse incompatible resume with `INCOMPATIBLE_GRAPH_VERSION`.
- [x] Document the operational requirement to retain a compatible worker for at least the configured recovery window during rolling releases.
- [x] Document that read/model nodes may replay and incur duplicate cost; any future write Tool must use an external `execution_id`/idempotency contract and cannot rely on checkpointing for exactly-once effects.
- **Status:** complete

### Phase 7: Observability, Operations, and Deployment
- [x] Add low-cardinality run/recovery outcome metrics and recoverable backlog count/age gauges; keep high-cardinality identities out of labels.
- [x] Add allowlisted submit, claim, recovery and finalize audit events without question, payload, result, or raw identity content.
- [x] Extend readiness so query serving and recovery-worker health are distinguishable; alert on stale backlog age rather than raw table size alone.
- [x] Add run-ledger reconciliation and a runbook for stuck runs, Redis/PostgreSQL outage, version mismatch, cancellation, and prohibited unsafe manual edits.
- [x] Update Kubernetes manifests, CI, README, external contracts, deployment/incident/evidence docs, and all impacted `test/001-016` simulation material.
- **Status:** complete

### Phase 8: Verification and Rollout
- [ ] Unit-test all legal/illegal state transitions, fencing, payload mismatch, retry classification, budgets, and exactly-once conversation finalization.
- [x] Add deterministic graph tests proving ordinary input restarts from the graph entry while `invoke(None)` resumes only pending tasks.
- [ ] Add real PostgreSQL/Redis subprocess-kill tests covering every crash window and two independent runtime processes.
- [x] Verify completed nodes are not replayed, the failed node may replay once per attempt, a stale owner cannot finalize, and duplicate requests return one stored result.
- [ ] Test authorization revocation, Redis/DB outage, recovery expiry, max attempts, newer-turn blocking, rolling graph-version mismatch, and graceful cancellation.
- [ ] Run load/soak tests measuring `durability="sync"` latency cost, recovery throughput, pool use, model duplication, and normal-query interference.
- [ ] Stage rollout behind a feature flag: shadow ledger -> idempotent reads -> recovery worker disabled -> canary recovery -> full recovery.
- [ ] Perform a staging Pod-kill drill and save immutable evidence before claiming automatic recovery capability.
- **Status:** pending

## Acceptance Criteria
1. Killing the executing process after a completed superstep leaves a discoverable run whose lease expires and is claimed by another worker.
2. Recovery uses the exact tenant/conversation/request-derived thread and resumes pending work with `invoke(None)`; completed supersteps are not re-executed.
3. A crash before the first checkpoint replays the persisted input; a crash after graph completion finalizes from stored state without another model call.
4. One idempotency key produces one logical result and one conversation turn; a different payload with the same key is rejected.
5. Lease fencing prevents the old process from completing or overwriting a run after takeover.
6. Recovery never resets cumulative action/token budgets and cannot continue past max attempts or recovery expiry.
7. Delayed recovery reauthorizes the user and fails closed on denial/unavailability.
8. The original client can retrieve the recovered result using the same identity and request ID.
9. A newer turn cannot overtake an unfinished older turn in the same conversation.
10. Real PostgreSQL/Redis kill-and-resume tests, a staging Pod-kill drill, and load evidence pass before documentation says “automatic recovery”.

## Decisions Made
| Decision | Rationale |
| --- | --- |
| PostgreSQL run ledger doubles as the durable work queue | Reuses the current state platform and `SKIP LOCKED`; avoids adding Kafka/Celery for low-volume recovery work |
| Dedicated recovery worker, not startup scanning | Avoids thundering-herd startup, separates resource limits, and keeps API readiness independent of backlog processing |
| Request-scoped checkpoint thread + ledger conversation association | LangGraph 1.2.11 reserves non-empty top-level checkpoint namespaces for subgraphs; a request thread gives supported isolation while the ledger preserves grouping/deletion |
| `invoke(None)` for pending recovery | Pinned-version experiment proves ordinary dict input re-enters from START, while `None` executes only the pending node |
| `durability="sync"` for durable queries | Makes the checkpoint boundary explicit before the next superstep, accepting measurable latency overhead |
| PostgreSQL lease plus Redis conversation lease | Database lease provides durable ownership/fencing; Redis lease prevents cross-run conversation concurrency |
| Result polling endpoint | A recovered result cannot be returned through a dead HTTP connection |
| At-least-once execution, idempotent finalization | This is the defensible guarantee across process crashes; exactly-once node execution is not realistic |

## Risks and Required Spikes
| Risk | Planned control |
| --- | --- |
| Existing absolute 30-second deadline is expired at delayed resume | Spike safe per-attempt deadline refresh without resetting cumulative budgets |
| Question/identity payload is needed if crash occurs before first checkpoint | Persist minimum payload with strict retention, access control, and encryption-at-rest requirement |
| Recovery across graph deployments can corrupt semantics | Version pinning, compatibility checks, and old-worker overlap |
| Model/LLM node replay duplicates cost | At-least-once contract, metrics, bounded attempts, provider idempotency where supported |
| Separate checkpoint and finalization transactions create a crash gap | Reconcile completed snapshot into one idempotent run+turn transaction |
| Stale authorization on delayed resume | Recovery-specific identity refresh and fail-closed policy |

## Non-Goals for Version 1
- Exactly-once execution inside arbitrary graph nodes.
- Replaying every historical SSE progress event after reconnect.
- Automatically recovering legacy checkpoints that have no durable request-run record.
- Moving ONECRM/Approval write-action recovery into the RAG Service.
