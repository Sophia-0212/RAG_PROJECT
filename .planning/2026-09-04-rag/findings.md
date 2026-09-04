# Findings & Decisions

## Requirements
- Compare the actual `RAG_PROJECT` implementation with the 16 simulated target documents under `test/`.
- Identify the real gap to a credible enterprise-grade RAG core engine.
- Produce several large implementation modules and explain the intended execution order.
- Do not modify business code in this planning turn.
- Distinguish repository-owned responsibilities from external Dify, CRM, IAM, approval, and infrastructure systems.

## Research Findings
- A completed repository index exists at `.planning/2026-09-03-project-index/` and provides a starting navigation map; critical claims still require live-source verification.
- Current branch is `main`, tracking `origin/main`, with substantial staged and unstaged user changes that must be preserved.
- Staged changes touch the agent, parser, Milvus, both graph flows, retrieval/reranking, and add direct-answer/reranker/evaluation work.
- The prior evaluation scripts, result reports, and 12-document test corpus currently appear as unstaged deletions; they cannot be treated as an available enterprise test suite.
- The repository currently exposes source modules and local scripts but still has no visible standard dependency manifest or production service entrypoint.
- No applicable `AGENTS.md` was found in the repository or immediate parent tree.
- Current staged work improves CRM routing, direct-answer handling, CrossEncoder reranking, per-document relevance grading, Chinese sentence splitting, and a bounded immediate hallucination retry.
- Those staged changes improve retrieval quality but do not yet supply production API contracts, persistence, security context, global execution budgets, or operational controls.
- Target-document capabilities cluster into: ingestion/data governance; hybrid retrieval/reranking; bounded LangGraph reasoning; multi-turn state; evaluation/release gates; security/tenant ACL; observability/version lineage; performance/resilience; and service/deployment engineering.
- Dify enterprise customization, HITL approval execution, ONECRM domain writes, and CRM master-data architecture are adjacent systems, not responsibilities that should be implemented inside this RAG core repository.
- Simulated scale, SLO, experiment, and incident numbers are targets/examples only and cannot be claimed until reproduced by this real project.
- Configuration is module-global and partly hard-coded: model names/endpoints, collection name, search size, and fallback behavior are not typed, validated, or environment-profiled.
- `main.py` remains the PyCharm sample; there is no stable HTTP/gRPC service contract, health/readiness endpoint, request schema, streaming interface, or lifecycle-managed dependency initialization.
- Model, embedding, search, and logging objects are created at import time; this complicates tests, startup failure handling, dependency injection, and graceful degradation.
- Current Milvus schema supports text, basic source metadata, dense vectors, and BM25 sparse vectors, but lacks tenant/workspace, ACL, document/chunk/version IDs, content hash, status, effective time, parent links, ingestion run, and deletion/tombstone metadata.
- Ingestion always drops and recreates the production collection, scans only one flat Markdown directory, has no incremental upsert/delete path, no idempotency, no checkpoint/resume, no dead-letter handling, no alias-based zero-downtime release, and no source/index reconciliation.
- Parser preserves title ancestry and semantically splits blocks over 5,000 characters, but has no configurable token target/overlap, parent-child retrieval model, parser-quality validation, stable chunk ID, or multi-format ingestion contract.
- The new CRM analyzer dictionary/synonyms are still source-code TODO examples, not versioned domain assets with tests.
- Retrieval is real hybrid dense+sparse Milvus recall with RRF, followed by a CrossEncoder and optional LLM relevance filtering, so the project already has a credible retrieval-quality skeleton.
- Retrieval parameters are hard-coded and use generic RRF; there is no independently tunable dense/sparse weight, deduplication, per-query filter contract, score lineage, query plan, parent expansion, or context-budget builder.
- The retriever applies only `category=content`; no tenant, user, ACL, document status, effective-time, or policy-version filter is enforced before candidate retrieval.
- Reranker loads eagerly on CPU, returns only documents (dropping scores), and has no batching policy, calibration threshold, timeout, circuit breaker, fallback to fused rank, or model-version metadata.
- Generated answers do not expose structured citations, source/version IDs, refusal reason codes, or evidence sufficiency; Graph 1 only checks document relevance before generation.
- `agent/rag_agent.py` performs a real request and prints output at import time; its session history is an unbounded process-local dictionary with no tenant isolation, TTL, persistence, summary, or deletion policy.
- Graph 1 has process-memory checkpoints but an unbounded rewrite loop, a single random thread ID, an import-time CLI loop, and no global deadline/token/retrieval/generation budget.
- Graph 1 mutates a tool message in place to replace its content after filtering, which weakens trace lineage between original recall, rerank, filter, and final context.
- Graph 2 is the strongest existing foundation: it has CRM/direct/web routing, query rewriting, hybrid retrieval, reranking, per-document relevance grading, generation, grounding grading, usefulness grading, and conditional retries.
- Graph 2 state overwrites the original question during rewriting and lacks request/tenant/user context, standalone query history, constraints, citations, retrieval/rerank scores, budgets, failure reasons, and version lineage.
- Graph 2 is compiled without a durable checkpointer and has no multi-turn memory; a new random Langfuse session is created per CLI question.
- The immediate grounding retry is bounded, but there is no single global step/deadline/token budget. A `not useful -> transform -> retrieve -> generate` cycle can continue when relevant documents keep being returned, and Graph 1 remains fully unbounded.
- Generation count is stored as `hallucination_count` and is never reset after a targeted query rewrite, making retry semantics hard to reason about and potentially exhausting later branches prematurely.
- Web-search results are collapsed into one provenance-free `Document`, losing URL/title/source metadata and bypassing source trust, allowlist, freshness, and citation controls.
- Direct-answer routing bypasses answer/safety grading; all evaluators are same-model binary judgments without reason codes, thresholds, calibration, timeout fallback, or deterministic guardrails.
- Generation simply concatenates document text with no context deduplication, token packing, source labels, prompt-injection filtering, citation IDs, or claim-to-evidence mapping.
- Langfuse infrastructure is present, but application tracing currently consists mainly of callback handlers plus session tags; it does not emit the target document's retrieval candidates, rank changes, citation/version lineage, evaluator reason codes, budgets, or degradation reasons.
- The Langfuse compose file is a local-development stack with multiple `CHANGEME` defaults and mutable image tags; it is not a hardened deployment artifact for the RAG service itself.
- No FastAPI/Flask/gRPC service, Dockerfile, Kubernetes/Helm configuration, Prometheus/OpenTelemetry instrumentation, health/readiness checks, rate limits, or circuit-breaker implementation was found in live project code.
- `CLAUDE.md` is materially stale: it still describes the old domain/model/endpoints, old retrieval size, old paths, and older Graph 2 loop behavior. Actual source has diverged.
- There is no committed README/runbook/API specification, conventional dependency lock/manifest, CI pipeline, migration mechanism, or release/versioning convention visible in the repository.
- The live `test/` directory currently contains target Markdown documents but no executable unit/integration/evaluation suite, because the previous evaluation code and corpus are deleted in the worktree.
- The target RAG design expects stable IDs/version/effective-time/ACL metadata, incremental ingestion with atomic alias switching, parent expansion, weighted hybrid recall, score-preserving rerank, bounded context packing, durable graph state, structured citations, and finite remediation by reason code.
- The target evaluation design expects a versioned golden set with retrieval, groundedness, citation, refusal, security, latency, and cost metrics plus reproducible ablations and release gates.
- The target operational design expects per-stage latency measurements, global deadlines/tokens/attempt budgets, tenant quotas, timeouts, retry+jitter, circuit breakers, component fallbacks, freshness/deletion SLOs, and fail-closed ACL behavior.
- The target incident narratives reveal two separate scopes: stale-document/version propagation is a real RAG-engine responsibility; duplicate business side effects and approval resume idempotency belong to workflow/tool/CRM services and should only be integration contracts here.
- The exact target values (420 tokens, 1024 dimensions, HNSW M32/ef96, topK 40/60/8, 6-second deadline, 1,800 locked cases) should not be copied blindly. They must be selected through this repository's own evaluation and capacity evidence.
- Static parsing succeeds for all 38 live Python files, which proves syntax validity only; it does not validate imports, external dependencies, graph termination, retrieval correctness, or production behavior.
- A live search found no README, dependency manifest/lockfile, Dockerfile, Makefile, CI workflow, pytest configuration, conftest, or executable test module outside the virtual environment.

## Capability Classification
| Capability | Status | Evidence / Main Gap |
|---|---|---|
| Markdown parsing and basic chunking | Partial | Real implementation exists; lacks stable IDs, token policy, overlap, parent-child model, parser QA, and format adapters |
| Milvus dense + BM25 hybrid recall | Partial | Real schema/index/RRF exists; lacks tenant/version/status/ACL fields, tunable fusion, score lineage, and safe migrations |
| CrossEncoder reranking | Partial | Real top-N rerank exists; lacks scores, batching, thresholds, version metadata, timeout, and fallback |
| Self-RAG-inspired graph | Partial | Routing/rewrite/relevance/grounding/usefulness exist; state, reason codes, global budgets, termination, citations, and persistence are incomplete |
| Multi-turn conversation | Partial/weak | Graph 1 has process memory and agent has process-local history; no durable store, summary, TTL, isolation, or Graph 2 support |
| Enterprise ingestion/version/deletion | Absent | Collection rebuild is destructive; no incremental upsert, tombstone, alias rollout, DLQ, reconciliation, or freshness controls |
| Tenant authorization and data security | Absent | Retrieval filter only checks category; no identity context, ACL filter, policy version, negative tests, or fail-closed path |
| Evidence/citation answer contract | Absent | Answers are plain strings; no citation IDs, source versions, claim mapping, conflict/refusal schema, or provenance |
| Evaluation and release gates | Absent in live tree | Prior scripts/corpus are deleted; no unit/integration/security/load suite or CI gate remains available |
| Observability and version lineage | Partial/weak | Langfuse callback exists; no structured end-to-end trace fields, metrics, SLO dashboards, redaction, or replay contract |
| Reliability/performance/deployment | Absent | No timeouts, circuit breakers, component fallbacks, quotas, service container, health checks, load tests, or deployment manifests |
| Dify/HITL/ONECRM execution | External contract | Should be represented by versioned APIs/context and integration tests, not implemented as RAG internals |

## Risk Priority
- **P0 - blocks credible enterprise use:** reproducible engineering/test baseline; non-destructive versioned ingestion; tenant/ACL fail-closed filtering; citation/source-version contract; finite graph execution with global budgets.
- **P1 - required before production:** durable conversation state; service API and lifecycle management; structured observability; timeouts, retries, circuit breakers, degradation; security and load tests.
- **P2 - scale and operational maturity:** deployment hardening, automated rollout/rollback, capacity tuning, richer format adapters, online experimentation, and evidence packaging.

Excluding the external Dify/HITL/ONECRM responsibility, none of the 11 assessed enterprise capabilities is fully closed: 6 are partial/weak and 5 are absent. The project is therefore a credible algorithm prototype, not yet a production-ready enterprise RAG service.

## Modular Execution Roadmap

### Module 1: Engineering Baseline and Boundaries
- Scope: standard dependency manifest and lock, typed configuration, application factory/dependency injection, removal of import-time network/model execution, package layout, local commands, README, and explicit ownership boundaries.
- Output: a cleanly installable and importable project with Graph 2 designated as the canonical production path; Graph 1 retained only as a demo/comparison flow.
- Acceptance: a clean environment can install and run offline unit tests; importing modules makes no external request or database connection; missing/invalid configuration fails with a clear error.

### Module 2: Evaluation Baseline and Release Gates
- Scope: rebuild tests from the live code state, create a small versioned real golden set, cover retrieval, rerank, groundedness, citation, refusal, ACL/security, latency and cost; add deterministic fakes and CI gates.
- Output: reproducible baseline reports and a growing regression suite used by every later module.
- Acceptance: metrics are correctly normalized and reproducible; dataset/model/prompt/index versions are recorded; failed quality or security thresholds block a release.
- Non-goal: do not restore the user's deleted evaluation files or claim the simulated document's sample numbers.

### Module 3: Enterprise Ingestion and Index Governance
- Scope: source-adapter contract; stable source/document/chunk IDs; tenant, ACL, version, status, effective time, content hash, parent, ingestion-run and tombstone metadata; incremental upsert/delete; idempotency; retry/DLQ; reconciliation; alias-based index release and rollback.
- Output: non-destructive, traceable, resumable ingestion and index lifecycle.
- Acceptance: repeated ingestion creates no duplicates; updates and deletions affect the correct version; revoked/expired content becomes unretrievable; a failed run can resume; index rollout can be rolled back atomically.

### Module 4: Secure Retrieval, Rerank, Context and Citations
- Scope: request/security context and query constraints; Milvus pre-retrieval fail-closed ACL filters; tunable dense/sparse fusion; deduplication and score lineage; rerank timeout/fallback; parent expansion; token-budgeted context packing; structured citations with exact source/version IDs.
- Output: a retrieval pipeline whose evidence and authorization decisions remain inspectable end to end.
- Acceptance: unauthorized documents never enter candidates or context; every citation resolves to the exact indexed version; dense/sparse/rerank ablations are measurable; reranker failure follows a tested degradation path.

### Module 5: Bounded LangGraph Orchestration and Durable Conversation
- Scope: enrich state with request/user/tenant, immutable original query, standalone-query history, constraints, scores, citations, budgets, failure reasons and component versions; reason-coded graders; finite remediation table; global step/retrieval/generation/token/deadline budgets; no-progress detection; durable checkpoints, TTL and conversation summaries.
- Output: one explainable and recoverable Graph 2 workflow with deterministic termination semantics.
- Acceptance: every route terminates; process restart can resume; ambiguous follow-ups request clarification; repeated query/candidate states stop; unsupported answers refuse with a reason rather than fabricate.

### Module 6: RAG Service API and External Contracts
- Scope: versioned query/stream/conversation and health/readiness APIs; authentication context propagation; request IDs, cancellation, stable error taxonomy and response schema; Dify adapter and contract tests for IAM, ONECRM and approval/workflow systems.
- Output: a deployable RAG service boundary rather than CLI/import-time scripts.
- Acceptance: an OpenAPI contract is executable; tenant/user/conversation/request context propagates end to end; streaming and cancellation are graceful; Dify can consume the service through contract tests.
- Non-goal: do not implement IAM, CRM writes, or approval execution inside the RAG engine.

### Module 7: Observability, Reliability, Performance and Degradation
- Scope: structured Langfuse/trace spans, metrics and redaction; model/prompt/graph/index/embedding/reranker version lineage; stage latency/token/cost metrics; timeouts, retry with jitter, circuit breakers, quotas, concurrency control and fallback matrix; load/fault tests and evidence-based SLOs.
- Output: diagnosable behavior and explicitly tested degraded modes.
- Acceptance: a trace reconstructs query to candidates to context to answer; secrets and unauthorized text do not enter traces; each dependency failure produces its specified fallback; load tests generate capacity and alert thresholds.

### Module 8: Deployment, Security Hardening and Evidence Package
- Scope: service container and environment profiles, secrets handling, least privilege/non-root runtime, pinned images, SBOM/vulnerability checks, migrations, deployment/rollback runbooks, release/version conventions, architecture and benchmark evidence.
- Output: reproducible development and staged production deployment artifacts.
- Acceptance: development starts through a documented command; CI builds and scans the image; staged deployment and rollback are repeatable; production has no `CHANGEME` defaults; every enterprise claim links to a test, report, trace, or commit.

## Execution Sequence
1. Start Modules 1 and 2 together: first make the code testable, then lock a real baseline.
2. Complete Module 3 before retrieval tuning: retrieval security and freshness depend on correct metadata and index lifecycle.
3. Implement Module 4 on that governed index, continuously extending Module 2's tests.
4. Consolidate Module 5 after retrieval contracts stabilize, so graph state and reason codes carry real evidence.
5. Expose the stable workflow through Module 6.
6. Validate and tune production behavior through Module 7 using measured evidence rather than simulated constants.
7. Finish Module 8 once service, telemetry, failure modes and SLO evidence are stable.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Audit by capability and runtime flow rather than by directory alone | Enterprise gaps often cross ingestion, serving, security, evaluation, and operations boundaries |
| Do not adopt simulated metrics as requirements with asserted values | Real benchmarks, load tests, and incident evidence must generate project-specific numbers |
| Prioritize metadata and ACL before advanced answer tuning | Unauthorized or stale evidence is a correctness and security failure that generation quality cannot repair |
| Make evaluation a continuous workstream rather than a final phase | Each module needs regression evidence and release criteria at the time it is introduced |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| `C.UTF-8` locale warning during plan initialization | Harmless; continue with the created files |
| Evaluation assets indexed yesterday are now deleted in the live worktree | Treat live worktree as authoritative and do not restore user deletions |
| Initial environment probe used `venv/bin/python`, but the repository environment is `.venv/bin/python` | Corrected the path, inventoried `.venv` package versions, and will still add an explicit reproducible project manifest |

## Resources
- Target documents: `/Users/lixiaofei05/Desktop/workspace/RAG企业知识库项目/RAG_PROJECT/test/*.md`
- Repository: `/Users/lixiaofei05/Desktop/workspace/RAG企业知识库项目/RAG_PROJECT`
